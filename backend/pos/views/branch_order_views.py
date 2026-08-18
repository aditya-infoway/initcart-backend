# pos/views/branch_order_views.py

from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db.models import Q
from django.db import transaction
from decimal import Decimal
from ecommerce.models.order import Order, OrderItem
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.order_serializers import (
    VendorOrderSerializer, VendorOrderListSerializer,
    VendorOrderStatusUpdateSerializer
)
import logging
import traceback

# ✅ Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee

logger = logging.getLogger(__name__)


def update_order_status(order):
    """
    Update overall order status based on all items' status
    Triggers commission ONLY when status changes to 'delivered'
    """
    items = order.items.all()
    
    if not items.exists():
        return
    
    statuses = set(items.values_list('item_status', flat=True))
    
    status_priority = {
        'cancelled': 0,
        'refunded': 0,
        'failed': 0,
        'pending': 1,
        'confirmed': 2,
        'processing': 3,
        'shipped': 4,
        'delivered': 5
    }
    
    # Calculate new status based on all items
    if len(statuses) == 1:
        new_status = statuses.pop()
    else:
        # Remove cancelled/refunded if not all items are in terminal states
        terminal_statuses = ['cancelled', 'refunded', 'failed']
        for ts in terminal_statuses:
            if ts in statuses and len(statuses) > 1:
                statuses.remove(ts)
        
        if statuses:
            new_status = max(statuses, key=lambda s: status_priority.get(s, 0))
        else:
            new_status = 'cancelled'
    
    old_status = order.order_status
    
    if old_status == new_status:
        return
    
    # Update order status
    order.order_status = new_status
    
    # For COD orders, mark payment as completed when delivered
    if new_status == 'delivered' and order.payment_method == 'cod':
        order.payment_status = 'completed'
    
    # Save the order - this triggers the signal that processes commission
    order.save()
    
    # Update delivery info if needed
    if new_status == 'delivered':
        from ecommerce.models.order import VendorDeliveryInfo
        VendorDeliveryInfo.objects.filter(order=order).update(delivery_status='delivered')


def handle_stock_on_status_change(order_item, old_status, new_status):
    """
    Handle stock quantity changes based on order item status
    - When order is DELIVERED: Decrease stock (stock actually leaves inventory)
    - When order is CANCELLED/RETURNED: Increase stock (return to inventory)
    """
    if not order_item.product_stock:
        return
    
    # CASE 1: Order is being DELIVERED - DECREASE stock
    if new_status == 'delivered' and old_status != 'delivered':
        if order_item.product_stock.stock_quantity >= order_item.quantity:
            order_item.product_stock.stock_quantity -= order_item.quantity
            order_item.product_stock.save()
    
    # CASE 2: Order is being CANCELLED/RETURNED - INCREASE stock
    elif new_status in ['cancelled', 'refunded', 'failed']:
        # Only increase if it was previously delivered (stock was deducted)
        if old_status == 'delivered':
            order_item.product_stock.stock_quantity += order_item.quantity
            order_item.product_stock.save()


class BranchOrderListAPIView(APIView):
    """
    API for branch to list their orders
    Branch ka apna vendor hota hai, uske through orders filter hote hain
    """
    
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]
    
    def get(self, request):
        try:
            user = request.user
            is_superadmin = user.role == 'superadmin'
            is_employee = user.role == 'employee'

            branch = user.get_effective_branch()
            if not branch:
                return Response({
                    'success': False,
                    'message': 'No branch linked to this user'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Employee ko bhi branch_id override allow
            branch_id_param = request.query_params.get('branch_id')
            if branch_id_param:
                if is_superadmin or is_employee:
                    from pos.models.branch import Branch
                    try:
                        branch = Branch.objects.get(id=branch_id_param)
                    except Branch.DoesNotExist:
                        return Response({'error': 'Branch not found'}, status=404)

            # Get vendor from branch user
            try:
                vendor = Vendor.objects.get(user=branch.user) if branch.user else None
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found for this branch'
                }, status=status.HTTP_404_NOT_FOUND)
            
            if not vendor:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)

            # Get filter parameters
            status_filter = request.query_params.get('status', 'all')
            search = request.query_params.get('search', '')
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            # Get orders that have items from this vendor
            orders = Order.objects.filter(
                items__vendor=vendor
            ).distinct().order_by('-created_at')
            
            # Apply status filter
            if status_filter != 'all':
                status_mapping = {
                    'pending': 'pending',
                    'confirmed': 'confirmed',
                    'packaging': 'processing',
                    'out_for_delivery': 'shipped',
                    'delivered': 'delivered',
                    'cancelled': 'cancelled',
                    'returned': 'refunded',
                    'failed_to_deliver': 'failed'
                }
                db_status = status_mapping.get(status_filter, status_filter)
                orders = orders.filter(
                    items__vendor=vendor,
                    items__item_status=db_status
                ).distinct()
            
            # Apply date filters
            if date_from:
                orders = orders.filter(created_at__gte=date_from)
            if date_to:
                orders = orders.filter(created_at__lte=date_to)
            
            # Apply search
            if search:
                orders = orders.filter(
                    Q(order_number__icontains=search) |
                    Q(billing_name__icontains=search) |
                    Q(billing_phone__icontains=search) |
                    Q(items__product_name__icontains=search)
                ).distinct()
            
            # Pagination
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
            start = (page - 1) * page_size
            end = start + page_size
            
            total = orders.count()
            paginated_orders = orders[start:end]
            
            serializer = VendorOrderListSerializer(
                paginated_orders, 
                many=True, 
                context={'request': request}
            )
            
            return Response({
                'success': True,
                'data': {
                    'orders': serializer.data,
                    'pagination': {
                        'total': total,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
                    }
                }
            })
            
        except Exception as e:
            logger.error(f"Error in BranchOrderListAPIView: {str(e)}")
            traceback.print_exc()
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BranchOrderStatsAPIView(APIView):
    """
    API for branch to get order statistics
    """
    
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]
    
    def get(self, request):
        try:
            user = request.user
            is_superadmin = user.role == 'superadmin'
            is_employee = user.role == 'employee'

            branch = user.get_effective_branch()
            if not branch:
                return Response({
                    'success': False,
                    'message': 'No branch linked to this user'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Employee ko bhi branch_id override allow
            branch_id_param = request.query_params.get('branch_id')
            if branch_id_param:
                if is_superadmin or is_employee:
                    from pos.models.branch import Branch
                    try:
                        branch = Branch.objects.get(id=branch_id_param)
                    except Branch.DoesNotExist:
                        return Response({'error': 'Branch not found'}, status=404)

            # Get vendor from branch user
            try:
                vendor = Vendor.objects.get(user=branch.user) if branch.user else None
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found for this branch'
                }, status=status.HTTP_404_NOT_FOUND)
            
            if not vendor:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get all order items for this vendor
            order_items = OrderItem.objects.filter(vendor=vendor)
            
            # Calculate statistics
            stats = {
                'total': order_items.values('order').distinct().count(),
                'pending': order_items.filter(item_status='pending').count(),
                'confirmed': order_items.filter(item_status='confirmed').count(),
                'packaging': order_items.filter(item_status='processing').count(),
                'out_for_delivery': order_items.filter(item_status='shipped').count(),
                'delivered': order_items.filter(item_status='delivered').count(),
                'cancelled': order_items.filter(item_status='cancelled').count(),
                'returned': order_items.filter(item_status='refunded').count(),
                'failed_to_deliver': order_items.filter(item_status='failed').count()
            }
            
            return Response({
                'success': True,
                'data': stats
            })
            
        except Exception as e:
            logger.error(f"Error in BranchOrderStatsAPIView: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BranchOrderDetailAPIView(APIView):
    """
    API for branch to view order details
    """
    
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]
    
    def get(self, request, order_id):
        try:
            user = request.user
            is_superadmin = user.role == 'superadmin'
            is_employee = user.role == 'employee'

            branch = user.get_effective_branch()
            if not branch:
                return Response({
                    'success': False,
                    'message': 'No branch linked to this user'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Employee ko bhi branch_id override allow
            branch_id_param = request.query_params.get('branch_id')
            if branch_id_param:
                if is_superadmin or is_employee:
                    from pos.models.branch import Branch
                    try:
                        branch = Branch.objects.get(id=branch_id_param)
                    except Branch.DoesNotExist:
                        return Response({'error': 'Branch not found'}, status=404)

            # Get vendor from branch user
            try:
                vendor = Vendor.objects.get(user=branch.user) if branch.user else None
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found for this branch'
                }, status=status.HTTP_404_NOT_FOUND)
            
            if not vendor:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get order that has items from this vendor
            order = Order.objects.filter(
                id=order_id,
                items__vendor=vendor
            ).prefetch_related(
                "items",
                "items__product_stock"
            ).distinct().first()
            
            if not order:
                return Response({
                    'success': False,
                    'message': 'Order not found or you do not have permission'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = VendorOrderSerializer(order, context={'request': request})
            
            return Response({
                'success': True,
                'data': serializer.data
            })
            
        except Exception as e:
            logger.error(f"Error in BranchOrderDetailAPIView: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BranchOrderStatusUpdateAPIView(APIView):
    """
    API for branch to update order item status
    Commission is automatically triggered via the post_save signal
    """
    
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]
    
    def post(self, request):
        try:
            user = request.user
            is_superadmin = user.role == 'superadmin'
            is_employee = user.role == 'employee'

            branch = user.get_effective_branch()
            if not branch:
                return Response({
                    'success': False,
                    'message': 'No branch linked to this user'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Employee ko bhi branch_id override allow
            branch_id_param = request.query_params.get('branch_id')
            if branch_id_param:
                if is_superadmin or is_employee:
                    from pos.models.branch import Branch
                    try:
                        branch = Branch.objects.get(id=branch_id_param)
                    except Branch.DoesNotExist:
                        return Response({'error': 'Branch not found'}, status=404)

            # Get vendor from branch user
            try:
                vendor = Vendor.objects.get(user=branch.user) if branch.user else None
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found for this branch'
                }, status=status.HTTP_404_NOT_FOUND)
            
            if not vendor:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = VendorOrderStatusUpdateSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Case 1: Update single item
            if serializer.validated_data.get('order_item_id'):
                order_item = OrderItem.objects.get(
                    id=serializer.validated_data['order_item_id'],
                    vendor=vendor
                )
                old_status = order_item.item_status
                new_status = serializer.validated_data['item_status']
                
                order_item.item_status = new_status
                order_item.save()
                
                # Handle stock management
                handle_stock_on_status_change(order_item, old_status, new_status)
                
                # Update overall order status - THIS TRIGGERS COMMISSION
                update_order_status(order_item.order)
                
                return Response({
                    'success': True,
                    'message': f'Item status updated to {new_status}'
                })
            
            # Case 2: Update all items in order
            elif serializer.validated_data.get('order_id'):
                order_id = serializer.validated_data['order_id']
                new_status = serializer.validated_data['item_status']
                
                # Get all order items for this vendor in the order
                order_items = OrderItem.objects.filter(
                    order_id=order_id,
                    vendor=vendor
                )
                
                order_obj = None
                updated_count = 0
                
                for order_item in order_items:
                    old_status = order_item.item_status
                    
                    order_item.item_status = new_status
                    order_item.save()
                    
                    # Handle stock management
                    handle_stock_on_status_change(order_item, old_status, new_status)
                    updated_count += 1
                    order_obj = order_item.order
                
                # Update overall order status - THIS TRIGGERS COMMISSION
                if order_obj:
                    update_order_status(order_obj)
                
                return Response({
                    'success': True,
                    'message': f'Updated {updated_count} items to {new_status}'
                })
                
        except OrderItem.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Order item not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in BranchOrderStatusUpdateAPIView: {str(e)}")
            traceback.print_exc()
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
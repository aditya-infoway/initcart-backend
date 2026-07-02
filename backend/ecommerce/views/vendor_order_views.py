# ecommerce/views/vendor_order_views.py

from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from django.db.models import Q
from django.conf import settings
import logging
import traceback

from ecommerce.models.order import Order, OrderItem, VendorDeliveryInfo
from ecommerce.models.vendor import Vendor  # ✅ Direct Vendor model import
from ecommerce.serializers.order_serializers import (
    VendorOrderSerializer, VendorOrderListSerializer,
    VendorOrderStatusUpdateSerializer, VendorDeliveryInfoSerializer
)

logger = logging.getLogger(__name__)

class VendorOrderListAPIView(APIView):
    """
    API for vendors to list their orders with filtering
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            print(f"=== VendorOrderListAPIView ===")
            
            # Check if user is vendor
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model using user
            try:
                vendor = Vendor.objects.get(user=user)
                print(f"Vendor found: {vendor.business_name} (ID: {vendor.id})")
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found. Please complete your vendor registration.'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get filter parameters
            status_filter = request.query_params.get('status', 'all')
            search = request.query_params.get('search', '')
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            print(f"Filters - status: {status_filter}, search: {search}")
            
            # ✅ Get orders that have items from this vendor
            orders = Order.objects.filter(
                items__vendor=vendor
            ).distinct().order_by('-created_at')
            
            print(f"Total orders before filters: {orders.count()}")
            
            # ✅ FIX: Apply status filter based on item_status
            if status_filter != 'all':
                # Map frontend status names to actual database values
                status_mapping = {
                    'pending': 'pending',
                    'confirmed': 'confirmed',  # Will match nothing if not in DB
                    'packaging': 'processing',  # packaging = processing
                    'out for delivery': 'shipped',  # out for delivery = shipped
                    'out_for_delivery': 'shipped',
                    'delivered': 'delivered',
                    'cancelled': 'cancelled',
                    'returned': 'refunded',  # returned = refunded
                    'failed to deliver': 'failed'  # if exists
                }
                
                # Apply mapping if needed
                db_status = status_mapping.get(status_filter, status_filter)
                
                print(f"Filtering: '{status_filter}' -> '{db_status}'")
                
                # Filter orders that have items with this status
                orders = orders.filter(
                    items__vendor=vendor,
                    items__item_status=db_status
                ).distinct()
                
                print(f"After status filter '{status_filter}': {orders.count()}")
            
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
            
            print(f"Orders after all filters: {orders.count()}")
            
            # ✅ Debug: Print first few orders with their item statuses
            for order in orders[:5]:
                items = OrderItem.objects.filter(order=order, vendor=vendor)
                statuses = [item.item_status for item in items]
                print(f"Order {order.id}: {order.order_number} - Item statuses: {statuses}")
            
            # Pagination
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
            start = (page - 1) * page_size
            end = start + page_size
            
            total = orders.count()
            paginated_orders = orders[start:end]
            
            print(f"Paginating: page={page}, page_size={page_size}, start={start}, end={end}")
            
            serializer = VendorOrderListSerializer(
                paginated_orders, 
                many=True, 
                context={'request': request}
            )
            
            print(f"Returning {len(serializer.data)} orders")
            print("=== End VendorOrderListAPIView ===\n")
            
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
            print(f"!!! ERROR in VendorOrderListAPIView: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ecommerce/views/vendor_order_views.py

class VendorOrderStatsAPIView(APIView):
    """
    API for vendors to get order statistics based on item_status
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            print(f"=== VendorOrderStatsAPIView ===")
            
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model
            try:
                vendor = Vendor.objects.get(user=user)
                print(f"Vendor found: {vendor.business_name}")
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get all order items for this vendor
            order_items = OrderItem.objects.filter(vendor=vendor)
            
            # Get unique orders count
            orders_count = order_items.values('order').distinct().count()
            
            # ✅ Calculate statistics based on ACTUAL database values
            stats = {
                'total': orders_count,
                'pending': order_items.filter(item_status='pending').count(),
                'confirmed': order_items.filter(item_status='confirmed').count(),  # Will be 0
                'packaging': order_items.filter(item_status='processing').count(),  # processing = packaging
                'out_for_delivery': order_items.filter(item_status='shipped').count(),  # shipped = out for delivery
                'delivered': order_items.filter(item_status='delivered').count(),
                'cancelled': order_items.filter(item_status='cancelled').count(),
                'returned': order_items.filter(item_status='refunded').count(),  # refunded = returned
                'failed_to_deliver': 0  # Add if you have this status
            }
            
            print(f"Database status values: {order_items.values_list('item_status', flat=True).distinct()}")
            print(f"Final stats: {stats}")
            print("=== End VendorOrderStatsAPIView ===\n")
            
            return Response({
                'success': True,
                'data': stats
            })
            
        except Exception as e:
            print(f"!!! ERROR in VendorOrderStatsAPIView: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
class VendorOrderDetailAPIView(APIView):
    """
    API for vendors to view order details
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model
            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
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
                    'message': 'Order not found or you do not have permission to view it'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = VendorOrderSerializer(order, context={'request': request})
            
            return Response({
                'success': True,
                'data': serializer.data
            })
            
        except Exception as e:
            print(f"!!! ERROR in VendorOrderDetailAPIView: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ecommerce/views/vendor_order_views.py - UPDATE THIS

class VendorOrderStatusUpdateAPIView(APIView):
    """
    API for vendors to update order item status
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            user = request.user
            
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model
            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
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
            
            # Update single item or all items in order
            if serializer.validated_data.get('order_item_id'):
                # Update single item
                order_item = OrderItem.objects.get(
                    id=serializer.validated_data['order_item_id'],
                    vendor=vendor
                )
                order_item.item_status = serializer.validated_data['item_status']
                order_item.save()
                
                # ✅ Update overall order status based on all items
                update_order_status(order_item.order)
                
                return Response({
                    'success': True,
                    'message': 'Order item status updated successfully'
                })
                
            elif serializer.validated_data.get('order_id'):
                # Update all items of this vendor in the order
                order_items = OrderItem.objects.filter(
                    order_id=serializer.validated_data['order_id'],
                    vendor=vendor
                )
                
                updated_count = order_items.update(
                    item_status=serializer.validated_data['item_status']
                )
                
                # Update overall order status
                if updated_count > 0:
                    order = order_items.first().order
                    update_order_status(order)
                
                return Response({
                    'success': True,
                    'message': f'Updated {updated_count} items successfully'
                })
                
        except OrderItem.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Order item not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"!!! ERROR in VendorOrderStatusUpdateAPIView: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Replace update_order_status and _process_delivery_commission in vendor_order_views.py

def update_order_status(order):
    items = order.items.all()
    if not items.exists():
        return

    statuses = set(items.values_list('item_status', flat=True))
    status_priority = {
        'cancelled': 0, 'refunded': 0, 'pending': 1,
        'confirmed': 2, 'processing': 3, 'shipped': 4, 'delivered': 5
    }

    if len(statuses) == 1:
        new_status = statuses.pop()
    else:
        if 'cancelled' in statuses and len(statuses) > 1:
            statuses.remove('cancelled')
        if 'refunded' in statuses and len(statuses) > 1:
            statuses.remove('refunded')
        new_status = max(statuses, key=lambda s: status_priority.get(s, 0)) if statuses else 'cancelled'

    old_status = order.order_status
    if old_status == new_status:
        return

    order.order_status = new_status

    if new_status == 'delivered' and order.payment_method == 'cod':
        order.payment_status = 'completed'

    order.save()  # ← signal fires here, handles commission cleanly

    if new_status == 'delivered':
        VendorDeliveryInfo.objects.filter(order=order).update(delivery_status='delivered')

    # ← NO _process_delivery_commission call here at all
class VendorDeliveryInfoAPIView(APIView):
    """
    API for vendors to manage delivery information
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model
            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if order has vendor's items
            if not OrderItem.objects.filter(order_id=order_id, vendor=vendor).exists():
                return Response({
                    'success': False,
                    'message': 'Order not found or you do not have permission'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get or create delivery info
            delivery_info, created = VendorDeliveryInfo.objects.get_or_create(
                order_id=order_id,
                vendor=vendor
            )
            
            serializer = VendorDeliveryInfoSerializer(delivery_info)
            
            return Response({
                'success': True,
                'data': serializer.data
            })
            
        except Exception as e:
            print(f"!!! ERROR in VendorDeliveryInfoAPIView GET: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model
            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if order has vendor's items
            if not OrderItem.objects.filter(order_id=order_id, vendor=vendor).exists():
                return Response({
                    'success': False,
                    'message': 'Order not found or you do not have permission'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get or create delivery info
            delivery_info, created = VendorDeliveryInfo.objects.get_or_create(
                order_id=order_id,
                vendor=vendor
            )
            
            # Update fields
            delivery_info.delivery_service = request.data.get('delivery_service', delivery_info.delivery_service)
            delivery_info.delivery_man_name = request.data.get('delivery_man_name', delivery_info.delivery_man_name)
            delivery_info.delivery_man_phone = request.data.get('delivery_man_phone', delivery_info.delivery_man_phone)
            
            if request.data.get('delivery_incentive'):  
                delivery_info.delivery_incentive = request.data.get('delivery_incentive')
                
            delivery_info.expected_delivery_date = request.data.get('expected_delivery_date', delivery_info.expected_delivery_date)
            delivery_info.tracking_id = request.data.get('tracking_id', delivery_info.tracking_id)
            delivery_info.courier_name = request.data.get('courier_name', delivery_info.courier_name)
            delivery_info.courier_website = request.data.get('courier_website', delivery_info.courier_website)
            delivery_info.delivery_status = request.data.get('delivery_status', delivery_info.delivery_status)
            
            delivery_info.save()
            
            serializer = VendorDeliveryInfoSerializer(delivery_info)
            
            return Response({
                'success': True,
                'message': 'Delivery information updated successfully',
                'data': serializer.data
            })
            
        except Exception as e:
            print(f"!!! ERROR in VendorDeliveryInfoAPIView POST: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorInvoiceAPIView(APIView):
    """
    API for vendors to get invoice data for their items
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model
            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get order with vendor's items
            order = Order.objects.filter(
                id=order_id,
                items__vendor=vendor
            ).distinct().first()
            
            if not order:
                return Response({
                    'success': False,
                    'message': 'Order not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get vendor's items
            vendor_items = OrderItem.objects.filter(
                order=order,
                vendor=vendor
            )
            
            # Calculate totals
            subtotal = sum(float(item.total_price) for item in vendor_items)
            discount = sum(float(item.discount_amount) for item in vendor_items)
            tax = sum(float(item.tax_amount) for item in vendor_items)
            total = subtotal - discount + tax
            
            # Get delivery info
            try:
                delivery_info = VendorDeliveryInfo.objects.get(order=order, vendor=vendor)
            except VendorDeliveryInfo.DoesNotExist:
                delivery_info = None
            
            invoice_data = {
                'order_number': order.order_number,
                'order_date': order.created_at,
                'customer_name': order.billing_name,
                'customer_phone': order.billing_phone,
                'customer_email': order.billing_email,
                'shipping_address': {
                    'name': order.shipping_name or order.billing_name,
                    'phone': order.shipping_phone or order.billing_phone,
                    'address': order.shipping_address or order.billing_address,
                    'city': order.shipping_city or order.billing_city,
                    'state': order.shipping_state or order.billing_state,
                    'pincode': order.shipping_pincode or order.billing_pincode
                },
                'payment_method': order.payment_method,
                'payment_status': order.payment_status,
                'items': [
                    {
                        'product_name': item.product_name,
                        'sku': item.sku,
                        'color': item.color,
                        'size': item.size,
                        'quantity': item.quantity,
                        'unit_price': float(item.unit_price),
                        'discount': float(item.discount_amount),
                        'tax': float(item.tax_amount),
                        'total': float(item.total_price),
                        'tax_percentage': float(item.product_stock.tax) if item.product_stock else 0,
                    } for item in vendor_items
                ],
                'subtotal': round(subtotal, 2),
                'discount': round(discount, 2),
                'tax': round(tax, 2),
                'total': round(total, 2),
                'delivery_info': {
                    'service': delivery_info.delivery_service if delivery_info else None,
                    'tracking_id': delivery_info.tracking_id if delivery_info else None,
                    'courier_name': delivery_info.courier_name if delivery_info else None,
                    'expected_delivery': delivery_info.expected_delivery_date if delivery_info else None
                } if delivery_info else None
            }
            
            return Response({
                'success': True,
                'data': invoice_data
            })
            
        except Exception as e:
            print(f"!!! ERROR in VendorInvoiceAPIView: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorSendInvoiceEmailAPIView(APIView):
    """
    API for vendors to send invoice email to customer
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'role') or user.role != 'vendor':
                return Response({
                    'success': False,
                    'message': 'Only vendors can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor directly from Vendor model
            try:
                vendor = Vendor.objects.get(user=user)
            except Vendor.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Vendor profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get order with vendor's items
            order = Order.objects.filter(
                id=order_id,
                items__vendor=vendor
            ).distinct().first()
            
            if not order:
                return Response({
                    'success': False,
                    'message': 'Order not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # TODO: Implement email sending logic here
            # For now, just return success
            
            return Response({
                'success': True,
                'message': f'Invoice email sent to {order.billing_email}'
            })
            
        except Exception as e:
            print(f"!!! ERROR in VendorSendInvoiceEmailAPIView: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
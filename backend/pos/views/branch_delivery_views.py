# pos/views/branch_delivery_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status
from django.shortcuts import get_object_or_404
from ecommerce.models.order import Order, OrderItem, VendorDeliveryInfo
from ecommerce.models.vendor import Vendor
import logging

logger = logging.getLogger(__name__)


class BranchDeliveryInfoAPIView(APIView):
    """
    API for branch to get/update delivery information
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def get(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'branch'):
                return Response({
                    'success': False,
                    'message': 'Only branch users can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
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
            
            return Response({
                'success': True,
                'data': {
                    'id': delivery_info.id,
                    'delivery_service': delivery_info.delivery_service,
                    'delivery_man_name': delivery_info.delivery_man_name,
                    'delivery_man_phone': delivery_info.delivery_man_phone,
                    'delivery_incentive': float(delivery_info.delivery_incentive) if delivery_info.delivery_incentive else None,
                    'expected_delivery_date': delivery_info.expected_delivery_date,
                    'tracking_id': delivery_info.tracking_id,
                    'courier_name': delivery_info.courier_name,
                    'courier_website': delivery_info.courier_website,
                    'delivery_status': delivery_info.delivery_status,
                    'created_at': delivery_info.created_at,
                    'updated_at': delivery_info.updated_at
                }
            })
            
        except Exception as e:
            logger.error(f"Error in BranchDeliveryInfoAPIView GET: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'branch'):
                return Response({
                    'success': False,
                    'message': 'Only branch users can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
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
            
            return Response({
                'success': True,
                'message': 'Delivery information updated successfully',
                'data': {
                    'id': delivery_info.id,
                    'delivery_service': delivery_info.delivery_service,
                    'delivery_man_name': delivery_info.delivery_man_name,
                    'delivery_man_phone': delivery_info.delivery_man_phone,
                    'delivery_incentive': float(delivery_info.delivery_incentive) if delivery_info.delivery_incentive else None,
                    'expected_delivery_date': delivery_info.expected_delivery_date,
                    'tracking_id': delivery_info.tracking_id,
                    'courier_name': delivery_info.courier_name,
                    'courier_website': delivery_info.courier_website,
                    'delivery_status': delivery_info.delivery_status,
                    'updated_at': delivery_info.updated_at
                }
            })
            
        except Exception as e:
            logger.error(f"Error in BranchDeliveryInfoAPIView POST: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BranchInvoiceAPIView(APIView):
    """
    API for branch to get invoice data
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    
    def get(self, request, order_id):
        try:
            user = request.user
            
            if not hasattr(user, 'branch'):
                return Response({
                    'success': False,
                    'message': 'Only branch users can access this endpoint'
                }, status=status.HTTP_403_FORBIDDEN)
            
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
                delivery_service = delivery_info.delivery_service
                tracking_id = delivery_info.tracking_id
                courier_name = delivery_info.courier_name
            except VendorDeliveryInfo.DoesNotExist:
                delivery_service = None
                tracking_id = None
                courier_name = None
            
            invoice_data = {
                'order_number': order.order_number,
                'order_date': order.created_at,
                'customer_name': order.billing_name,
                'customer_phone': order.billing_phone,
                'customer_email': order.billing_email,
                'store_name': vendor.business_name,
                'shipping_address': {
                    'name': order.shipping_name or order.billing_name,
                    'phone': order.shipping_phone or order.billing_phone,
                    'address': order.shipping_address or order.billing_address,
                    'city': order.shipping_city or order.billing_city,
                    'state': order.shipping_state or order.billing_state,
                    'pincode': order.shipping_pincode or order.billing_pincode
                },
                'billing_address': {
                    'name': order.billing_name,
                    'phone': order.billing_phone,
                    'address': order.billing_address,
                    'city': order.billing_city,
                    'state': order.billing_state,
                    'pincode': order.billing_pincode
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
                    'service': delivery_service,
                    'tracking_id': tracking_id,
                    'courier_name': courier_name
                } if delivery_service else None
            }
            
            return Response({
                'success': True,
                'data': invoice_data
            })
            
        except Exception as e:
            logger.error(f"Error in BranchInvoiceAPIView: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
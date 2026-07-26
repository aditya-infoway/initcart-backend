# ecommerce/views/order_views.py 
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from ecommerce.models.order import Order , VendorDeliveryInfo
from ecommerce.serializers.order_serializers import OrderSerializer


class OrderDetailAPIView(APIView):
    authentication_classes = [TokenAuthentication, JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get order details by order number"""
        order_number = request.query_params.get('order_number') or request.query_params.get('search')
        
        if not order_number:
            return Response({
                'success': False,
                'message': 'Order number is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Customer can only see their own orders
            order = Order.objects.get(
                customer=request.user,
                order_number__iexact=order_number
            )
            
            # Get serializer data
            serializer = OrderSerializer(order)
            data = serializer.data
            
            # Add delivery tracking information
            vendor_deliveries = VendorDeliveryInfo.objects.filter(order=order)  #  Now this will work
            
            if vendor_deliveries.exists():
                # For customer view, combine all vendor deliveries or show first one
                delivery_info = []
                for delivery in vendor_deliveries:
                    delivery_info.append({
                        'vendor': delivery.vendor.business_name,
                        'delivery_service': delivery.delivery_service,
                        'delivery_status': delivery.delivery_status,
                        'expected_delivery_date': delivery.expected_delivery_date,
                        'tracking_id': delivery.tracking_id,
                        'courier_name': delivery.courier_name,
                        'delivery_man_name': delivery.delivery_man_name,
                        'delivery_man_phone': delivery.delivery_man_phone,
                        'updated_at': delivery.updated_at
                    })
                
                # Add to response
                data['delivery_tracking'] = delivery_info
                
                # For simple view, just add first/primary delivery info
                primary_delivery = vendor_deliveries.first()
                data['tracking'] = {
                    'delivery_status': primary_delivery.delivery_status,
                    'expected_delivery_date': primary_delivery.expected_delivery_date,
                    'tracking_id': primary_delivery.tracking_id,
                    'courier_name': primary_delivery.courier_name,
                    'delivery_service': primary_delivery.delivery_service
                }
            else:
                data['delivery_tracking'] = []
                data['tracking'] = None
            
            return Response({
                'success': True,
                'data': data
            })
            
        except Order.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Yeh error ab aayega nahi because import fix ho gaya
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
class OrderListAPIView(APIView):
    authentication_classes = [TokenAuthentication, JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        #  Allow customers and both user types
        if not request.user.is_customer():
            return Response({
                'success': False,
                'message': 'Access denied. Only customers can view orders.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            orders = Order.objects.filter(
                customer=request.user
            ).prefetch_related(
                'items__product',
                'items__product_stock', 
                'items__vendor'
            ).select_related(
                'customer'
            ).order_by('-created_at')
            
            serializer = OrderSerializer(orders, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
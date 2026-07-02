from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, Sum, F
from django.utils import timezone
from datetime import timedelta
from django_filters.rest_framework import DjangoFilterBackend

from ecommerce.models.order import Order, OrderItem
from ecommerce.serializers.order_serializers import OrderSerializer, AdminRecentOrderSerializer
from ecommerce.models.vendor import Vendor
from users.models import User
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.pagination import PageNumberPagination

class AdminOrderPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 10000


class SuperAdminOrderViewSet(viewsets.ModelViewSet):
    """
    Super Admin Orders Management

    """
    queryset = Order.objects.all()  
    pagination_class = AdminOrderPagination
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['order_status', 'payment_status', 'payment_method']
    search_fields = ['order_number', 'customer__email', 'customer__username', 'billing_name', 'billing_phone']
    ordering_fields = ['created_at', 'final_amount', 'order_number']
    ordering = ['-created_at']
    
    # Add this line - Use order_number instead of default id
    lookup_field = 'order_number'
    lookup_url_kwarg = 'order_number' 
    def get_queryset(self):

        if not self.request.user.is_superuser:
            return Order.objects.none()

        queryset = (
            Order.objects
            .select_related("customer")
            .prefetch_related("items__vendor")
            .order_by("-created_at")
        )

        vendor_id = self.request.query_params.get('vendor_id')
        if vendor_id:
            queryset = queryset.filter(items__vendor_id=vendor_id).distinct()

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)

        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        customer_id = self.request.query_params.get('customer_id')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        return queryset
        
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):

        if not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)

        today = timezone.now().date()

        order_stats = Order.objects.aggregate(
            total_orders=Count("id"),
            today_orders=Count("id", filter=Q(created_at__date=today)),
            today_revenue=Sum("final_amount", filter=Q(created_at__date=today))
        )

        total_orders = order_stats["total_orders"] or 0
        today_count = order_stats["today_orders"] or 0
        today_revenue = order_stats["today_revenue"] or 0

        total_customers = User.objects.filter(role="customer").count()
        total_vendors = Vendor.objects.count()

        status_counts = (
            Order.objects
            .values("order_status")
            .annotate(count=Count("id"))
        )

        status_dict = {item["order_status"]: item["count"] for item in status_counts}

        payment_counts = (
            Order.objects
            .values("payment_status")
            .annotate(count=Count("id"))
        )

        payment_dict = {item["payment_status"]: item["count"] for item in payment_counts}

        return Response({
            "success": True,
            "data": {
                "total_orders": total_orders,
                "total_customers": total_customers,
                "total_vendors": total_vendors,
                "today_orders": today_count,
                "today_revenue": float(today_revenue),
                "status_counts": status_dict,
                "payment_status_counts": payment_dict
            }
        })
        
    @action(detail=False, methods=['get'])
    def vendor_orders_summary(self, request):

        if not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)

        summary = OrderItem.objects.values(
            "vendor__id",
            "vendor__business_name"
        ).annotate(
            total_orders=Count("order", distinct=True),
            total_items_sold=Sum("quantity"),
            total_revenue=Sum(F("quantity") * F("price")),
            pending_orders=Count("order", filter=Q(order__order_status="pending"), distinct=True),
            processing_orders=Count("order", filter=Q(order__order_status="processing"), distinct=True),
            delivered_orders=Count("order", filter=Q(order__order_status="delivered"), distinct=True),
        ).order_by("-total_orders")

        return Response({
            "success": True,
            "data": list(summary)
        })
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status (Super Admin can update any order)"""
        if not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)
        
        order = self.get_object()
        new_status = request.data.get('order_status')
        notes = request.data.get('notes', '')
        
        if new_status not in dict(Order.ORDER_STATUS).keys():
            return Response({
                'success': False,
                'message': 'Invalid order status'
            }, status=400)
        
        # Update order status
        old_status = order.order_status
        order.order_status = new_status
        if notes:
            order.notes = f"{order.notes or ''}\nStatus changed from {old_status} to {new_status} by Super Admin: {notes}"
        order.save()
        
        # Update all order items status
        order.items.all().update(item_status=new_status)
        
        return Response({
            'success': True,
            'message': f'Order status updated to {new_status}',
            'order_status': order.order_status
        })
    
    @action(detail=True, methods=['post'])
    def update_payment_status(self, request, pk=None):
        """Update payment status"""
        if not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)
        
        order = self.get_object()
        new_status = request.data.get('payment_status')
        
        if new_status not in dict(Order.PAYMENT_STATUS).keys():
            return Response({
                'success': False,
                'message': 'Invalid payment status'
            }, status=400)
        
        order.payment_status = new_status
        order.save()
        
        return Response({
            'success': True,
            'message': f'Payment status updated to {new_status}',
            'payment_status': order.payment_status
        })
    
    @action(detail=False, methods=['get'])
    def export_orders(self, request):
        """Export orders to CSV or Excel"""
        if not request.user.is_superuser:
            return Response({'error': 'Permission denied'}, status=403)
        
        # This would typically generate and return a file
        # For now, return the data in export format
        orders = self.get_queryset()
        serializer = OrderSerializer(orders[:1000], many=True)

        return Response({
            "success": True,
            "data": serializer.data,
            "count": orders.count(),
            'export_format': 'json'  # Could be CSV, Excel etc.
        })
# ecommerce/views/refund_views.py  (FULL FILE — replace your existing one)
from django.db.models import Count, Sum, Q
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from ecommerce.models.refund import OrderRefund
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.refund_serializers import RefundListSerializer, ProcessRefundSerializer
from ecommerce.utils.refund_helpers import process_refund
from ecommerce.permissions import IsSuperAdmin
from pos.utils.pagination import StandardReportPagination


# ============== HELPERS ==============

def build_refund_stats(qs):
    """Stats over the WHOLE queryset (ignores page + status filter) so cards/tabs stay stable."""
    agg = qs.order_by().aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        processed=Count('id', filter=Q(status='processed')),
        failed=Count('id', filter=Q(status='failed')),
        total_amount=Sum('refund_amount'),
        pending_amount=Sum('refund_amount', filter=Q(status='pending')),
        processed_amount=Sum('refund_amount', filter=Q(status='processed')),
        failed_amount=Sum('refund_amount', filter=Q(status='failed')),
    )
    return {k: float(v or 0) if k.endswith('_amount') else (v or 0) for k, v in agg.items()}


def paginated_response(request, qs, serializer_class, stats):
    paginator = StandardReportPagination()
    page = paginator.paginate_queryset(qs, request)
    data = serializer_class(page, many=True).data
    response = paginator.get_paginated_response(data)
    response.data['stats'] = stats
    return response


def apply_status_filter(qs, request):
    status_filter = request.query_params.get('status')
    if status_filter and status_filter != 'all':
        qs = qs.filter(status__in=status_filter.split(','))
    return qs


# ============== SUPERADMIN SIDE ==============

class AdminRefundListAPIView(APIView):
    """List online refunds — ?status=pending|processed|failed|all &page= &page_size="""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        base_qs = OrderRefund.objects.select_related(
            'return_request', 'return_request__customer',
            'order', 'order_item', 'order_item__vendor'
        ).order_by('-id')

        stats = build_refund_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        return paginated_response(request, qs, RefundListSerializer, stats)


class AdminRefundProcessAPIView(APIView):
    """Triggers the actual Razorpay refund call for one refund record."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            refund = OrderRefund.objects.select_related(
                'order', 'order_item', 'return_request'
            ).get(pk=pk)
        except OrderRefund.DoesNotExist:
            return Response({'success': False, 'message': 'Refund record not found'},
                            status=status.HTTP_404_NOT_FOUND)

        serializer = ProcessRefundSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        if refund.status == 'processed':
            return Response({'success': False, 'message': 'This refund has already been processed'},
                            status=status.HTTP_400_BAD_REQUEST)

        success, message = process_refund(refund)
        refund.refresh_from_db()

        return Response({
            'success': success,
            'message': message,
            'data': RefundListSerializer(refund).data,
        }, status=status.HTTP_200_OK if success else status.HTTP_502_BAD_GATEWAY)


# ============== VENDOR SIDE (read-only) ==============

class VendorRefundListAPIView(APIView):
    """Vendor can see which of their orders have been refunded to the customer."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                            status=status.HTTP_404_NOT_FOUND)

        base_qs = OrderRefund.objects.filter(order_item__vendor=vendor).select_related(
            'return_request', 'return_request__customer', 'order', 'order_item'
        ).order_by('-id')

        stats = build_refund_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        return paginated_response(request, qs, RefundListSerializer, stats)
# ecommerce/views/refund_views.py
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from ecommerce.models.refund import OrderRefund
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.refund_serializers import RefundListSerializer, ProcessRefundSerializer
from ecommerce.utils.refund_helpers import process_refund
from ecommerce.permissions import IsSuperAdmin


# ============== SUPERADMIN SIDE ==============

class AdminRefundListAPIView(APIView):
    """List all online refunds — filter with ?status=pending|processed|failed|all"""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        qs = OrderRefund.objects.select_related(
            'return_request', 'return_request__customer',
            'order', 'order_item', 'order_item__vendor'
        ).all()

        status_filter = request.query_params.get('status')
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)

        return Response({'success': True, 'data': RefundListSerializer(qs, many=True).data})


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

        qs = OrderRefund.objects.filter(order_item__vendor=vendor).select_related(
            'return_request', 'return_request__customer', 'order', 'order_item'
        )
        return Response({'success': True, 'data': RefundListSerializer(qs, many=True).data})
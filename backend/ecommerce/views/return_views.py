# ecommerce/views/return_views.py  (FULL FILE — replace your existing one)
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from ecommerce.models.return_request import ReturnRequest
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.return_serializers import (
    ReturnRequestListSerializer,
    CreateReturnRequestSerializer,
    VendorReturnActionSerializer,
    AdminReturnActionSerializer,
)
from ecommerce.permissions import IsSuperAdmin
from rest_framework.parsers import MultiPartParser, FormParser
from pos.utils.pagination import StandardReportPagination


# ============== HELPERS ==============

RETURN_STATUSES = [
    'requested', 'vendor_approved', 'vendor_rejected',
    're_requested', 'admin_approved', 'admin_rejected',
]


def build_return_stats(qs):
    """Counts over the WHOLE queryset (ignores page + status filter)."""
    agg = {'total': Count('id')}
    for s in RETURN_STATUSES:
        agg[s] = Count('id', filter=Q(status=s))
    result = qs.order_by().aggregate(**agg)
    return {k: v or 0 for k, v in result.items()}


def apply_status_filter(qs, request):
    """?status=all | requested | vendor_approved,admin_approved (comma separated allowed)"""
    status_filter = request.query_params.get('status')
    if status_filter and status_filter != 'all':
        qs = qs.filter(status__in=status_filter.split(','))
    return qs


def paginated_response(request, qs, stats):
    paginator = StandardReportPagination()
    page = paginator.paginate_queryset(qs, request)
    data = ReturnRequestListSerializer(page, many=True, context={'request': request}).data
    response = paginator.get_paginated_response(data)
    response.data['stats'] = stats
    return response


# ============== CUSTOMER SIDE ==============

class CustomerCreateReturnAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = CreateReturnRequestSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)
        return_req = serializer.save()
        return Response({
            'success': True,
            'message': 'Return request submitted successfully',
            'data': ReturnRequestListSerializer(return_req, context={'request': request}).data
        }, status=201)


class CustomerReturnListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        base_qs = ReturnRequest.objects.filter(customer=request.user).prefetch_related('return_images').order_by('-id')
        stats = build_return_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        return paginated_response(request, qs, stats)


class CustomerRequestAgainAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            rr = ReturnRequest.objects.get(id=pk, customer=request.user, status='vendor_rejected')
        except ReturnRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Return request not found or not eligible'}, status=404)
        rr.status = 're_requested'
        rr.re_requested_at = timezone.now()
        rr.save()
        return Response({'success': True, 'message': 'Request sent to admin for review',
                         'data': ReturnRequestListSerializer(rr, context={'request': request}).data})


# ============== VENDOR SIDE ==============

class VendorReturnListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({'success': False, 'message': 'Vendor profile not found'}, status=404)

        base_qs = ReturnRequest.objects.filter(vendor=vendor).prefetch_related('return_images').order_by('-id')
        stats = build_return_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        return paginated_response(request, qs, stats)


class VendorReturnActionAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({'success': False, 'message': 'Vendor profile not found'}, status=404)

        try:
            rr = ReturnRequest.objects.get(id=pk, vendor=vendor, status='requested')
        except ReturnRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Return request not found or already actioned'}, status=404)

        serializer = VendorReturnActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        rr.vendor_remarks = serializer.validated_data.get('remarks', '')
        rr.vendor_responded_at = timezone.now()
        rr.status = 'vendor_approved' if serializer.validated_data['action'] == 'approve' else 'vendor_rejected'
        rr.save()

        # online (Razorpay) order ka return accept hote hi refund record auto-create
        if rr.status == 'vendor_approved':
            from ecommerce.utils.refund_helpers import create_refund_if_online
            create_refund_if_online(rr)

        return Response({'success': True, 'message': f'Return {rr.status}',
                         'data': ReturnRequestListSerializer(rr, context={'request': request}).data})


# ============== SUPERADMIN SIDE ==============

class AdminReturnListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        base_qs = ReturnRequest.objects.select_related(
            'vendor', 'order', 'order_item', 'customer'
        ).prefetch_related('return_images').order_by('-id')
        stats = build_return_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        return paginated_response(request, qs, stats)


class AdminReturnActionAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            rr = ReturnRequest.objects.get(id=pk, status='re_requested')
        except ReturnRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Return request not found or not eligible for admin action'}, status=404)

        serializer = AdminReturnActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        rr.admin_remarks = serializer.validated_data.get('remarks', '')
        rr.admin_responded_at = timezone.now()
        rr.status = 'admin_approved' if serializer.validated_data['action'] == 'approve' else 'admin_rejected'
        rr.save()

        # superadmin approve kare toh bhi refund record auto-create
        if rr.status == 'admin_approved':
            from ecommerce.utils.refund_helpers import create_refund_if_online
            create_refund_if_online(rr)

        return Response({'success': True, 'message': f'Return {rr.status}',
                         'data': ReturnRequestListSerializer(rr, context={'request': request}).data})
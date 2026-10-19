# ecommerce/views/return_views.py  (FULL FILE — replace your existing one)
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from ecommerce.models.return_request import ReturnRequest
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.return_serializers import (
    ReturnRequestListSerializer,
    CreateReturnRequestSerializer,
    VendorReturnActionSerializer,
    AdminReturnActionSerializer,
)
from ecommerce.utils.refund_helpers import create_refund_for_return
from ecommerce.permissions import IsSuperAdmin
from pos.utils.pagination import StandardReportPagination


# ============== HELPERS ==============

RETURN_STATUSES = [
    'requested', 'vendor_approved', 'vendor_rejected',
    're_requested', 'admin_approved', 'admin_rejected',
]

# select_related on reverse one-to-ones ('refund', 'bank_detail') so the list serializer
# doesn't fire 2 extra queries per row.
RETURN_RELATED = ('order', 'order_item', 'vendor', 'customer', 'refund', 'bank_detail')


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


def apply_payment_filter(qs, request):
    """?payment_method=cod | razorpay  (anything else = all)"""
    pm = (request.query_params.get('payment_method') or '').lower()
    if pm in ('cod', 'razorpay'):
        qs = qs.filter(order__payment_method=pm)
    return qs


def apply_search_filter(qs, request, fields):
    """?search=xyz → icontains on ANY of the given fields (OR). No-op if blank."""
    q = (request.query_params.get('search') or '').strip()
    if not q:
        return qs
    cond = Q()
    for f in fields:
        cond |= Q(**{f"{f}__icontains": q})
    return qs.filter(cond)


def paginated_response(request, qs, stats):
    paginator = StandardReportPagination()
    page = paginator.paginate_queryset(qs, request)
    data = ReturnRequestListSerializer(page, many=True, context={'request': request}).data
    response = paginator.get_paginated_response(data)
    response.data['stats'] = stats
    return response


def _vendor_for(request):
    return Vendor.objects.filter(user=request.user).first()


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
        base_qs = ReturnRequest.objects.filter(customer=request.user) \
            .select_related(*RETURN_RELATED).prefetch_related('return_images').order_by('-id')
        stats = build_return_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        qs = apply_search_filter(qs, request, [
            'return_id', 'order__order_number',
            'order_item__product_name', 'order_item__sku',
            'vendor__business_name',
        ])
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
    """
    ?status=all|requested|... &payment_method=cod|razorpay &page= &page_size= &search=
    Response: {success, data, pagination, stats}
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        vendor = _vendor_for(request)
        if vendor is None:
            return Response({'success': False, 'message': 'Vendor profile not found'}, status=404)

        base_qs = ReturnRequest.objects.filter(vendor=vendor) \
            .select_related(*RETURN_RELATED).prefetch_related('return_images').order_by('-id')
        base_qs = apply_payment_filter(base_qs, request)
        stats = build_return_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        qs = apply_search_filter(qs, request, [
            'return_id', 'order__order_number',
            'order_item__product_name', 'order_item__sku',
            'customer__username',
        ])
        return paginated_response(request, qs, stats)


class VendorReturnActionAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        vendor = _vendor_for(request)
        if vendor is None:
            return Response({'success': False, 'message': 'Vendor profile not found'}, status=404)

        try:
            rr = ReturnRequest.objects.get(id=pk, vendor=vendor, status='requested')
        except ReturnRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Return request not found or already actioned'}, status=404)

        serializer = VendorReturnActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        with transaction.atomic():
            rr.vendor_remarks = serializer.validated_data.get('remarks', '')
            rr.vendor_responded_at = timezone.now()
            rr.status = 'vendor_approved' if serializer.validated_data['action'] == 'approve' else 'vendor_rejected'
            rr.save()

            # online → refund row (admin triggers Razorpay); COD → refund row (admin pays to customer's bank)
            if rr.status == 'vendor_approved':
                create_refund_for_return(rr)

        return Response({'success': True, 'message': f'Return {rr.status}',
                         'data': ReturnRequestListSerializer(rr, context={'request': request}).data})


# ============== SUPERADMIN SIDE ==============

class AdminReturnListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        base_qs = ReturnRequest.objects.select_related(*RETURN_RELATED) \
            .prefetch_related('return_images').order_by('-id')
        base_qs = apply_payment_filter(base_qs, request)
        stats = build_return_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        qs = apply_search_filter(qs, request, [
            'return_id', 'order__order_number',
            'order_item__product_name', 'order_item__sku',
            'vendor__business_name', 'customer__username',
        ])
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

        with transaction.atomic():
            rr.admin_remarks = serializer.validated_data.get('remarks', '')
            rr.admin_responded_at = timezone.now()
            rr.status = 'admin_approved' if serializer.validated_data['action'] == 'approve' else 'admin_rejected'
            rr.save()

            if rr.status == 'admin_approved':
                create_refund_for_return(rr)

        return Response({'success': True, 'message': f'Return {rr.status}',
                         'data': ReturnRequestListSerializer(rr, context={'request': request}).data})
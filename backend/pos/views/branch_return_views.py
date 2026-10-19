# pos/views/branch_return_views.py
# Branch panel ke liye return/refund views. Koi naya model nahi — wahi
# ecommerce.ReturnRequest / ecommerce.OrderRefund jo vendor panel use karta hai.
# Farak sirf itna hai ki vendor branch.user se resolve hota hai.
# COD-aware: payment_method filter (returns) + type filter (refunds).

from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ecommerce.models.return_request import ReturnRequest
from ecommerce.models.refund import OrderRefund
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.return_serializers import (
    ReturnRequestListSerializer,
    VendorReturnActionSerializer,
)
from ecommerce.serializers.refund_serializers import VendorRefundListSerializer
from ecommerce.utils.refund_helpers import create_refund_for_return
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee
from pos.utils.pagination import StandardReportPagination


# ============== HELPERS ==============

RETURN_STATUSES = [
    'requested', 'vendor_approved', 'vendor_rejected',
    're_requested', 'admin_approved', 'admin_rejected',
]

RETURN_RELATED = ('order', 'order_item', 'vendor', 'customer', 'refund', 'bank_detail')


def _resolve_vendor_for_branch_user(request):
    """
    Same resolution pattern as BranchOrderListAPIView — superadmin/employee ko
    ?branch_id= se override allow, warna user.get_effective_branch().
    Vendor = Vendor.objects.get(user=branch.user). Returns (vendor, error_response).
    """
    user = request.user
    is_superadmin = user.role == 'superadmin'
    is_employee = user.role == 'employee'

    branch = user.get_effective_branch()
    if not branch:
        return None, Response(
            {'success': False, 'message': 'No branch linked to this user'},
            status=status.HTTP_400_BAD_REQUEST
        )

    branch_id_param = request.query_params.get('branch_id')
    if branch_id_param and (is_superadmin or is_employee):
        from pos.models.branch import Branch
        try:
            branch = Branch.objects.get(id=branch_id_param)
        except Branch.DoesNotExist:
            return None, Response({'success': False, 'message': 'Branch not found'}, status=404)

    vendor = Vendor.objects.filter(user=branch.user).first() if branch.user else None
    if not vendor:
        return None, Response(
            {'success': False, 'message': 'Vendor profile not found for this branch'},
            status=status.HTTP_404_NOT_FOUND
        )

    return vendor, None


def build_return_stats(qs):
    """Counts over the WHOLE queryset (ignores page + status filter + search)."""
    agg = {'total': Count('id')}
    for s in RETURN_STATUSES:
        agg[s] = Count('id', filter=Q(status=s))
    result = qs.order_by().aggregate(**agg)
    return {k: v or 0 for k, v in result.items()}


def build_refund_stats(qs):
    """Counts + amounts over the WHOLE queryset."""
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


def apply_status_filter(qs, request):
    status_filter = request.query_params.get('status')
    if status_filter and status_filter != 'all':
        qs = qs.filter(status__in=status_filter.split(','))
    return qs


def apply_payment_filter(qs, request):
    """?payment_method=cod | razorpay"""
    pm = (request.query_params.get('payment_method') or '').lower()
    if pm in ('cod', 'razorpay'):
        qs = qs.filter(order__payment_method=pm)
    return qs


def apply_type_filter(qs, request):
    """?type=online | cod (anything else = all)"""
    t = (request.query_params.get('type') or '').lower()
    if t in ('online', 'cod'):
        qs = qs.filter(refund_type=t)
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


def paginated_response(request, qs, serializer_class, stats):
    paginator = StandardReportPagination()
    page = paginator.paginate_queryset(qs, request)
    data = serializer_class(page, many=True, context={'request': request}).data
    response = paginator.get_paginated_response(data)
    response.data['stats'] = stats
    return response


# ============== RETURN VIEWS ==============

class BranchReturnListAPIView(APIView):
    """
    GET /branch/returns/ — is branch (vendor) ke saare return requests.
    ?status=all|requested|... &payment_method=cod|razorpay &page= &page_size= &search=
    """
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        vendor, err = _resolve_vendor_for_branch_user(request)
        if err:
            return err

        base_qs = ReturnRequest.objects.filter(vendor=vendor) \
            .select_related(*RETURN_RELATED).prefetch_related('return_images') \
            .order_by('-requested_at')
        base_qs = apply_payment_filter(base_qs, request)

        stats = build_return_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        qs = apply_search_filter(qs, request, [
            'return_id', 'order__order_number',
            'order_item__product_name', 'order_item__sku',
            'customer__username',
        ])
        return paginated_response(request, qs, ReturnRequestListSerializer, stats)


class BranchReturnActionAPIView(APIView):
    """POST /branch/returns/<id>/action/ — approve/reject, bilkul VendorReturnActionAPIView jaisa."""
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]

    def post(self, request, pk):
        vendor, err = _resolve_vendor_for_branch_user(request)
        if err:
            return err

        try:
            rr = ReturnRequest.objects.get(id=pk, vendor=vendor, status='requested')
        except ReturnRequest.DoesNotExist:
            return Response(
                {'success': False, 'message': 'Return request not found or already actioned'},
                status=404
            )

        serializer = VendorReturnActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        with transaction.atomic():
            rr.vendor_remarks = serializer.validated_data.get('remarks', '')
            rr.vendor_responded_at = timezone.now()
            rr.status = 'vendor_approved' if serializer.validated_data['action'] == 'approve' else 'vendor_rejected'
            rr.save()

            # online → refund row for Razorpay; COD → refund row for manual bank payout by superadmin
            if rr.status == 'vendor_approved':
                create_refund_for_return(rr)

        return Response({
            'success': True,
            'message': f'Return {rr.status}',
            'data': ReturnRequestListSerializer(rr, context={'request': request}).data
        })


# ============== REFUND VIEWS ==============

class BranchRefundListAPIView(APIView):
    """
    GET /branch/refunds/ — is branch (vendor) ke returned/refunded orders, read-only (online + COD).
    ?status=all|pending|processed|failed &type=online|cod &page= &page_size= &search=
    """
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        vendor, err = _resolve_vendor_for_branch_user(request)
        if err:
            return err

        base_qs = OrderRefund.objects.filter(order_item__vendor=vendor).select_related(
            'return_request', 'return_request__customer', 'order', 'order_item'
        ).order_by('-created_at')
        base_qs = apply_type_filter(base_qs, request)

        stats = build_refund_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        qs = apply_search_filter(qs, request, [
            'refund_id', 'return_request__return_id',
            'order__order_number', 'order_item__product_name',
            'return_request__customer__username',
        ])
        return paginated_response(request, qs, VendorRefundListSerializer, stats)
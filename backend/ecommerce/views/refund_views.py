# ecommerce/views/refund_views.py  (FULL FILE — replace your existing one)
import logging
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum, Q, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status, permissions, serializers
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework.response import Response

from ecommerce.models.order import OrderItem
from ecommerce.models.refund import (
    OrderRefund, RefundBankAccount, CODRefundPayment, ReturnBankDetail,
)
from ecommerce.models.return_request import ReturnRequest
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.refund_serializers import (
    RefundListSerializer, VendorRefundListSerializer, ProcessRefundSerializer,
    CODRefundDetailSerializer, RefundBankAccountSerializer, CODRefundPaySerializer,
    file_url,
)
from ecommerce.serializers.return_serializers import validate_bank_details_payload
from ecommerce.utils.refund_helpers import process_refund, finalize_refund_success
from ecommerce.permissions import IsSuperAdmin
from pos.utils.pagination import StandardReportPagination

logger = logging.getLogger(__name__)


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
    data = serializer_class(page, many=True, context={'request': request}).data
    response = paginator.get_paginated_response(data)
    response.data['stats'] = stats
    return response


def apply_status_filter(qs, request):
    status_filter = request.query_params.get('status')
    if status_filter and status_filter != 'all':
        qs = qs.filter(status__in=status_filter.split(','))
    return qs


def apply_type_filter(qs, request, default):
    """?type=online | cod | all  (default differs per endpoint)"""
    t = (request.query_params.get('type') or default).lower()
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


def parse_date(value):
    value = (value or '').strip()
    if not value:
        return None
    return date.fromisoformat(value)  # raises ValueError


REFUND_SELECT = (
    'return_request', 'return_request__customer', 'return_request__bank_detail',
    'order', 'order_item', 'order_item__vendor',
    'cod_payment', 'cod_payment__bank_account',
)


# ============== SUPERADMIN SIDE — REFUND LIST / ONLINE PROCESS ==============

class AdminRefundListAPIView(APIView):
    """
    List refunds — ?type=online(default)|cod|all &status=pending|processed|failed|all
                   &page= &page_size= &search=
    """
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        base_qs = OrderRefund.objects.select_related(*REFUND_SELECT).order_by('-id')
        base_qs = apply_type_filter(base_qs, request, default='online')

        stats = build_refund_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        qs = apply_search_filter(qs, request, [
            'refund_id', 'return_request__return_id',
            'order__order_number', 'order_item__product_name',
            'order_item__vendor__business_name',
            'return_request__customer__username',
            'cod_payment__voucher_no', 'cod_payment__bank_account__account_name',
        ])
        return paginated_response(request, qs, RefundListSerializer, stats)


class AdminRefundProcessAPIView(APIView):
    """Triggers the actual Razorpay refund call for one ONLINE refund record."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            refund = OrderRefund.objects.select_related(
                'order', 'order_item', 'return_request'
            ).get(pk=pk)
        except OrderRefund.DoesNotExist:
            return Response({'success': False, 'message': 'Refund record not found'},
                            status=status.HTTP_404_NOT_FOUND)

        if refund.refund_type == 'cod':
            return Response({'success': False,
                             'message': 'COD refunds are paid manually from the COD Refunds page'},
                            status=status.HTTP_400_BAD_REQUEST)

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
            'data': RefundListSerializer(refund, context={'request': request}).data,
        }, status=status.HTTP_200_OK if success else status.HTTP_502_BAD_GATEWAY)


# ============== SUPERADMIN SIDE — COD REFUNDS ==============

class AdminCODRefundPayableListAPIView(APIView):
    """Dropdown source for the 'Pay COD Refund' form: COD refunds not yet paid. ?search="""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        qs = OrderRefund.objects.filter(refund_type='cod').exclude(status='processed') \
            .select_related('return_request', 'return_request__customer',
                            'return_request__bank_detail', 'order', 'order_item')
        qs = apply_search_filter(qs, request, [
            'refund_id', 'order__order_number', 'order_item__product_name',
            'return_request__customer__username',
        ])
        qs = qs.order_by('-id')[:100]

        data = [{
            'id': r.id,
            'refund_id': r.refund_id,
            'order_number': r.order.order_number,
            'customer_name': r.return_request.customer.username,
            'product_name': r.order_item.product_name,
            'refund_amount': float(r.refund_amount),
            'has_bank_details': hasattr(r.return_request, 'bank_detail'),
        } for r in qs]
        return Response({'success': True, 'data': data})


class AdminCODRefundDetailAPIView(APIView):
    """Full details (customer, product, customer's bank details) for one COD refund."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request, pk):
        try:
            refund = OrderRefund.objects.select_related(
                'return_request', 'return_request__customer', 'order',
                'order_item', 'order_item__vendor', 'order_item__product',
            ).get(pk=pk, refund_type='cod')
        except OrderRefund.DoesNotExist:
            return Response({'success': False, 'message': 'COD refund not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({
            'success': True,
            'data': CODRefundDetailSerializer(refund, context={'request': request}).data,
        })


class AdminCODRefundPayAPIView(APIView):
    """
    Records the manual COD refund payout:
      bank_account_id, amount, payment_mode, proof (jpg/png/pdf ≤ 1MB),
      reference_no (optional), narration
    Atomic + row-locked, so a double-click / double-submit can never pay twice.
    On success: refund -> processed, ledger entry created (via CODRefundPayment),
    returned_quantity / item_status updated and MLM commission reversed
    (same finalize_refund_success() used by online refunds).
    """
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        payment = None
        try:
            with transaction.atomic():
                try:
                    refund = OrderRefund.objects.select_for_update().get(pk=pk, refund_type='cod')
                except OrderRefund.DoesNotExist:
                    return Response({'success': False, 'message': 'COD refund not found'},
                                    status=status.HTTP_404_NOT_FOUND)

                if refund.status == 'processed':
                    return Response({'success': False, 'message': 'This refund has already been paid'},
                                    status=status.HTTP_400_BAD_REQUEST)

                if not ReturnBankDetail.objects.filter(return_request_id=refund.return_request_id).exists():
                    return Response({
                        'success': False,
                        'message': "Customer has not provided bank details for this return yet.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                serializer = CODRefundPaySerializer(data=request.data, context={'refund': refund})
                if not serializer.is_valid():
                    return Response({'success': False, 'errors': serializer.errors},
                                    status=status.HTTP_400_BAD_REQUEST)
                v = serializer.validated_data

                # lock the item row so concurrent refunds of the same item can't race
                OrderItem.objects.select_for_update().get(pk=refund.order_item_id)
                bank_account = RefundBankAccount.objects.select_for_update().get(pk=v['bank_account'].pk)
                if not bank_account.is_active:
                    return Response({'success': False, 'errors': {'bank_account_id': ['Selected bank account is inactive.']}},
                                    status=status.HTTP_400_BAD_REQUEST)

                payment = CODRefundPayment.objects.create(
                    refund=refund,
                    bank_account=bank_account,
                    amount=v['amount'],
                    payment_mode=v['payment_mode'],
                    reference_no=(v.get('reference_no') or '').strip(),
                    proof=v['proof'],
                    narration=(v.get('narration') or '').strip(),
                    paid_by=request.user,
                )

                refund.status = 'processed'
                refund.paid_amount = v['amount']
                refund.processed_at = timezone.now()
                refund.failure_reason = None
                refund.save()

                finalize_refund_success(refund)

        except Exception as e:
            logger.exception("COD refund payout failed for refund pk=%s", pk)
            # remove the orphan uploaded file (DB rows were rolled back)
            try:
                if payment is not None and payment.proof:
                    payment.proof.storage.delete(payment.proof.name)
            except Exception:
                pass
            return Response({'success': False, 'message': f'Refund could not be recorded: {e}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        refund = OrderRefund.objects.select_related(
            'return_request', 'return_request__customer', 'order',
            'order_item', 'order_item__vendor', 'order_item__product',
        ).get(pk=pk)
        return Response({
            'success': True,
            'message': f'COD refund of ₹{payment.amount} recorded ({payment.voucher_no})',
            'data': CODRefundDetailSerializer(refund, context={'request': request}).data,
        }, status=status.HTTP_200_OK)


# ============== SUPERADMIN SIDE — REFUND BANK ACCOUNTS + LEDGER ==============

def _accounts_qs():
    return RefundBankAccount.objects.annotate(
        _paid=Coalesce(Sum('payments__amount'), Decimal('0.00'),
                       output_field=DecimalField(max_digits=16, decimal_places=2)),
        _count=Count('payments'),
    )


class AdminRefundBankAccountListCreateAPIView(APIView):
    """
    GET  ?search= &active=1 &all=1 (no pagination, for dropdowns) &page= &page_size=
    POST create a new refund bank account
    """
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        base_qs = _accounts_qs().order_by('-id')
        if (request.query_params.get('active') or '') in ('1', 'true', 'True'):
            base_qs = base_qs.filter(is_active=True)

        if (request.query_params.get('all') or '') in ('1', 'true', 'True'):
            return Response({'success': True,
                             'data': RefundBankAccountSerializer(base_qs, many=True).data})

        agg = RefundBankAccount.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            inactive=Count('id', filter=Q(is_active=False)),
        )
        total_paid = CODRefundPayment.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        stats = {**agg, 'total_paid': float(total_paid)}

        qs = apply_search_filter(base_qs, request, ['account_name', 'bank_name', 'account_number'])
        return paginated_response(request, qs, RefundBankAccountSerializer, stats)

    def post(self, request):
        serializer = RefundBankAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(created_by=request.user)
        return Response({'success': True, 'message': 'Bank account created',
                         'data': RefundBankAccountSerializer(obj).data},
                        status=status.HTTP_201_CREATED)


class AdminRefundBankAccountDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def _get(self, pk):
        try:
            return _accounts_qs().get(pk=pk)
        except RefundBankAccount.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({'success': False, 'message': 'Bank account not found'}, status=404)
        return Response({'success': True, 'data': RefundBankAccountSerializer(obj).data})

    def patch(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({'success': False, 'message': 'Bank account not found'}, status=404)
        serializer = RefundBankAccountSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)
        serializer.save()
        obj = self._get(pk)
        return Response({'success': True, 'message': 'Bank account updated',
                         'data': RefundBankAccountSerializer(obj).data})

    def delete(self, request, pk):
        try:
            obj = RefundBankAccount.objects.get(pk=pk)
        except RefundBankAccount.DoesNotExist:
            return Response({'success': False, 'message': 'Bank account not found'}, status=404)
        if obj.payments.exists():
            return Response({
                'success': False,
                'message': 'Payments exist for this account — deactivate it instead of deleting.',
            }, status=400)
        obj.delete()
        return Response({'success': True, 'message': 'Bank account deleted'})


class AdminRefundBankLedgerAPIView(APIView):
    """
    Ledger of one refund bank account: every COD refund paid from it (money OUT),
    with order no. / customer / product, running balance.
    ?date_from=YYYY-MM-DD &date_to=YYYY-MM-DD &search=
    balance = opening_balance − cumulative payouts.
    """
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request, pk):
        try:
            account = RefundBankAccount.objects.get(pk=pk)
        except RefundBankAccount.DoesNotExist:
            return Response({'success': False, 'message': 'Bank account not found'}, status=404)

        try:
            date_from = parse_date(request.query_params.get('date_from'))
            date_to = parse_date(request.query_params.get('date_to'))
        except ValueError:
            return Response({'success': False, 'message': 'Invalid date. Use YYYY-MM-DD.'}, status=400)

        base = CODRefundPayment.objects.filter(bank_account=account)

        opening = Decimal(str(account.opening_balance))
        if date_from:
            before = base.filter(paid_at__date__lt=date_from).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            opening -= Decimal(str(before))

        qs = base
        if date_from:
            qs = qs.filter(paid_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(paid_at__date__lte=date_to)
        qs = qs.select_related(
            'refund', 'refund__order', 'refund__order_item',
            'refund__return_request', 'refund__return_request__customer',
        ).order_by('paid_at', 'id')

        rows, running, total_out = [], opening, Decimal('0')
        for p in qs:
            running -= p.amount
            total_out += p.amount
            rows.append({
                'id': p.id,
                'date': p.paid_at.date().isoformat(),
                'paid_at': p.paid_at.isoformat(),
                'voucher_no': p.voucher_no,
                'refund_id': p.refund.refund_id,
                'order_number': p.refund.order.order_number,
                'customer_name': p.refund.return_request.customer.username,
                'product_name': p.refund.order_item.product_name,
                'payment_mode': p.get_payment_mode_display(),
                'reference_no': p.reference_no,
                'narration': p.narration,
                'amount_out': float(p.amount),
                'balance': float(running),
                'proof': file_url(request, p.proof),
            })

        # search AFTER running balance is computed, so balances stay true
        q = (request.query_params.get('search') or '').strip().lower()
        if q:
            rows = [r for r in rows if any(
                q in (str(r[k]) or '').lower()
                for k in ('voucher_no', 'refund_id', 'order_number', 'customer_name',
                          'product_name', 'reference_no', 'narration')
            )]

        return Response({
            'success': True,
            'account': {
                'id': account.id,
                'account_name': account.account_name,
                'bank_name': account.bank_name,
                'account_number': account.account_number,
                'ifsc_code': account.ifsc_code,
                'is_active': account.is_active,
            },
            'opening_balance': float(opening),
            'total_paid': float(total_out),
            'closing_balance': float(running),
            'count': len(rows),
            'ledger': rows,
        })


# ============== CUSTOMER SIDE — add/update bank details for a COD return ==============

class CustomerReturnBankDetailsAPIView(APIView):
    """
    PUT/POST public/returns/<pk>/bank-details/
    Lets the customer add or correct bank details until the refund is paid
    (also used for older COD returns that were created before this feature).
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def put(self, request, pk):
        try:
            rr = ReturnRequest.objects.select_related('order').get(id=pk, customer=request.user)
        except ReturnRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Return request not found'}, status=404)

        if rr.order.payment_method != 'cod':
            return Response({'success': False, 'message': 'Bank details are only needed for COD orders'},
                            status=400)

        if OrderRefund.objects.filter(return_request=rr, status='processed').exists():
            return Response({'success': False, 'message': 'Refund already paid — details cannot be changed'},
                            status=400)

        try:
            cleaned = validate_bank_details_payload(request.data)
        except serializers.ValidationError as e:
            return Response({'success': False, 'errors': e.detail}, status=400)

        ReturnBankDetail.objects.update_or_create(return_request=rr, defaults=cleaned)
        return Response({'success': True, 'message': 'Bank details saved'})

    post = put


# ============== VENDOR SIDE (read-only) ==============

class VendorRefundListAPIView(APIView):
    """
    Vendor: refunds of their own items (online + COD).
    ?type=all|online|cod &status=all|pending|processed|failed &page= &page_size= &search=
    Response: {success, data, pagination, stats}
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        vendor = Vendor.objects.filter(user=request.user).first()
        if vendor is None:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                            status=status.HTTP_404_NOT_FOUND)

        base_qs = OrderRefund.objects.filter(order_item__vendor=vendor).select_related(
            'return_request', 'return_request__customer', 'order', 'order_item',
        ).order_by('-id')
        base_qs = apply_type_filter(base_qs, request, default='all')

        stats = build_refund_stats(base_qs)
        qs = apply_status_filter(base_qs, request)
        qs = apply_search_filter(qs, request, [
            'refund_id', 'return_request__return_id',
            'order__order_number', 'order_item__product_name',
            'return_request__customer__username',
        ])
        return paginated_response(request, qs, VendorRefundListSerializer, stats)
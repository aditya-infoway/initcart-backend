# ecommerce/views/payment_request_views.py
import traceback
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from decimal import Decimal
from pos.utils.pagination import StandardReportPagination

from ecommerce.models.vendor import Vendor
from ecommerce.models.payment_request import VendorPaymentRequest, VendorCODRecovery
from ecommerce.serializers.payment_request_serializers import (
    PaymentRequestListSerializer, PaymentRequestDetailSerializer,
    CreatePaymentRequestSerializer, ApprovePaymentRequestSerializer,
)
from ecommerce.utils.payment_helpers import (
    get_vendor_eligible_online_orders, get_vendor_cod_platform_charge, get_order_summaries,
    get_vendor_order_report,get_all_vendors_order_report,
)
from ecommerce.permissions import IsSuperAdmin


def _get_vendor(user):
    try:
        return Vendor.objects.get(user=user)
    except Vendor.DoesNotExist:
        return None


# ============== VENDOR SIDE ==============

class VendorPaymentRequestFormDataAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        vendor = _get_vendor(request.user)
        if not vendor:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                             status=status.HTTP_404_NOT_FOUND)

        try:
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')

            print(f"[FORM-DATA] Received date_from={date_from} date_to={date_to}")  # debug

            eligible_orders = []
            cod_charge = Decimal('0.00')

            if date_from and date_to:
                eligible_orders = get_vendor_eligible_online_orders(vendor, date_from, date_to)
                cod_charge, _ = get_vendor_cod_platform_charge(vendor, date_from, date_to)
            else:
                print("[FORM-DATA] ⚠️ date_from/date_to missing — returning empty orders + zero COD charge")

            past_requests = VendorPaymentRequest.objects.filter(vendor=vendor)
            received_amount = sum(
                (r.approved_amount for r in past_requests.filter(status='paid')), start=0
            )
            pending_amount = sum(
                (r.release_payment_amount for r in past_requests.filter(status='pending')), start=0
            ) + sum(
                (r.approved_amount for r in past_requests.filter(status='approved')), start=0
            )

            all_time_eligible = get_vendor_eligible_online_orders(vendor)
            total_amount = sum((o['net_amount'] for o in all_time_eligible), start=0)

            return Response({
                'success': True,
                'data': {
                    'vendor_name': vendor.business_name,
                    'company_name': 'InitCart',
                    'orders': [
                        {
                            'order_id': o['order_id'],
                            'order_number': o['order_number'],
                            'created_at': o['created_at'],
                            'billing_name': o['billing_name'],
                            'vendor_total': float(o['vendor_total']),
                            'platform_charge': float(o['platform_charge']),
                            'net_amount': float(o['net_amount']),
                        } for o in eligible_orders
                    ],
                    'cod_platform_charge_pending': float(cod_charge),
                    'stats': {
                        'total_amount': float(total_amount),
                        'pending_amount': float(pending_amount),
                        'received_amount': float(received_amount),
                    }
                }
            })
        except Exception as e:
            traceback.print_exc()
            return Response({'success': False, 'message': f'Error: {str(e)}'},
                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorPaymentRequestCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        vendor = _get_vendor(request.user)
        if not vendor:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                             status=status.HTTP_404_NOT_FOUND)

        serializer = CreatePaymentRequestSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors},
                             status=status.HTTP_400_BAD_REQUEST)

        payment_request = serializer.save()
        return Response({
            'success': True,
            'message': 'Payment request submitted successfully',
            'data': PaymentRequestListSerializer(payment_request).data
        }, status=status.HTTP_201_CREATED)


class VendorPaymentRequestListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        vendor = _get_vendor(request.user)
        if not vendor:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                             status=status.HTTP_404_NOT_FOUND)

        qs = VendorPaymentRequest.objects.filter(vendor=vendor)
        return Response({'success': True, 'data': PaymentRequestListSerializer(qs, many=True).data})


# ============== SUPERADMIN SIDE ==============

class AdminPaymentRequestListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        qs = VendorPaymentRequest.objects.select_related('vendor').all()
        status_filter = request.query_params.get('status')
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)
        return Response({'success': True, 'data': PaymentRequestListSerializer(qs, many=True).data})


class AdminPaymentRequestDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request, pk):
        try:
            pr = VendorPaymentRequest.objects.select_related('vendor').get(pk=pk)
        except VendorPaymentRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Payment request not found'},
                             status=status.HTTP_404_NOT_FOUND)
        return Response({'success': True, 'data': PaymentRequestDetailSerializer(pr).data})


class AdminPaymentRequestApproveAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            pr = VendorPaymentRequest.objects.get(pk=pk)
        except VendorPaymentRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Payment request not found'},
                             status=status.HTTP_404_NOT_FOUND)

        serializer = ApprovePaymentRequestSerializer(
            data=request.data, context={'payment_request': pr}
        )
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors},
                             status=status.HTTP_400_BAD_REQUEST)

        approved_ids = serializer.validated_data['approved_order_ids']
        remarks = serializer.validated_data.get('remarks', '')

        # Track which orders were requested but NOT approved (for logging / vendor visibility)
        all_requested_ids = set(pr.orders.values_list('id', flat=True))
        not_approved_ids = all_requested_ids - set(approved_ids)

        summaries = get_order_summaries(pr.vendor, approved_ids)
        approved_order_amount = sum((s['vendor_total'] for s in summaries), start=0)
        approved_online_charge = sum((s['platform_charge'] for s in summaries), start=0)
        approved_amount = approved_order_amount - approved_online_charge - pr.cod_platform_charge

        from ecommerce.models.order import Order
        pr.approved_orders.set(Order.objects.filter(id__in=approved_ids))
        pr.approved_order_amount = approved_order_amount
        pr.approved_online_charge = approved_online_charge
        pr.approved_amount = approved_amount
        pr.status = 'approved'
        pr.admin_remarks = remarks
        pr.approved_at = timezone.now()
        pr.save()

        print(f"[APPROVE] Request {pr.payment_request_id}: approved {len(approved_ids)} of {len(all_requested_ids)} orders")
        if not_approved_ids:
            print(f"[APPROVE] Orders NOT approved (will become re-selectable): {sorted(not_approved_ids)}")

        return Response({
            'success': True,
            'message': f'Payment request approved ({len(approved_ids)} of {len(all_requested_ids)} orders)',
            'data': PaymentRequestDetailSerializer(pr).data,
            'not_approved_order_ids': sorted(not_approved_ids),   # ✅ frontend ko bhi pata chal sakta hai
        })

class VendorPaymentRequestDetailAPIView(APIView):
    """
    Vendor's own view of a single payment request — shows every order that
    was originally requested, and which of those got approved/rejected.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        vendor = _get_vendor(request.user)
        if not vendor:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                             status=status.HTTP_404_NOT_FOUND)

        try:
            pr = VendorPaymentRequest.objects.get(pk=pk, vendor=vendor)
        except VendorPaymentRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Payment request not found'},
                             status=status.HTTP_404_NOT_FOUND)

        return Response({'success': True, 'data': PaymentRequestDetailSerializer(pr).data})
class AdminPaymentRequestRejectAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            pr = VendorPaymentRequest.objects.get(pk=pk)
        except VendorPaymentRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Payment request not found'},
                             status=status.HTTP_404_NOT_FOUND)

        if pr.status not in ['pending']:
            return Response({'success': False, 'message': 'Only pending requests can be rejected'},
                             status=status.HTTP_400_BAD_REQUEST)

        pr.status = 'rejected'
        pr.admin_remarks = request.data.get('remarks', '')
        pr.save()

        # Free up the COD platform charge that was locked for this request
        VendorCODRecovery.objects.filter(payment_request=pr).delete()

        return Response({'success': True, 'message': 'Payment request rejected'})


class AdminPaymentRequestMarkPaidAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            pr = VendorPaymentRequest.objects.get(pk=pk)
        except VendorPaymentRequest.DoesNotExist:
            return Response({'success': False, 'message': 'Payment request not found'},
                             status=status.HTTP_404_NOT_FOUND)

        if pr.status != 'approved':
            return Response({'success': False, 'message': 'Only approved requests can be marked as paid'},
                             status=status.HTTP_400_BAD_REQUEST)

        pr.status = 'paid'
        pr.paid_at = timezone.now()
        pr.save()

        return Response({
            'success': True,
            'message': 'Payment marked as paid',
            'data': PaymentRequestListSerializer(pr).data
        })
        
        
class VendorOrderReportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardReportPagination

    def get(self, request):
        vendor = _get_vendor(request.user)
        if not vendor:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                             status=status.HTTP_404_NOT_FOUND)
        try:
            date_from = request.query_params.get('date_from') or None
            date_to = request.query_params.get('date_to') or None
            search = request.query_params.get('search') or None

            report_rows = get_vendor_order_report(vendor, date_from, date_to, search)

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(report_rows, request, view=self)

            start_index = (paginator.page.number - 1) * paginator.get_page_size(request)
            data = []
            for i, row in enumerate(page, start=start_index + 1):
                data.append({
                    'sr_no': i, 'order_id': row['order_id'], 'order_number': row['order_number'],
                    'order_time': row['order_time'], 'order_status': row['order_status'],
                    'customer_name': row['customer_name'], 'customer_phone': row['customer_phone'],
                    'customer_city': row['customer_city'], 'customer_email': row['customer_email'],
                    'payment_mode': row['payment_mode'], 'order_amount': float(row['order_amount']),
                    'platform_charge': float(row['platform_charge']),
                    'received_amount': float(row['received_amount']),
                    'order_age_days': row['order_age_days'],
                })
            return paginator.get_paginated_response(data)
        except Exception as e:
            traceback.print_exc()
            return Response({'success': False, 'message': f'Error: {str(e)}'},
                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminAllVendorsOrderReportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardReportPagination

    def get(self, request):
        try:
            date_from = request.query_params.get('date_from') or None
            date_to = request.query_params.get('date_to') or None
            search = request.query_params.get('search') or None

            report_rows = get_all_vendors_order_report(date_from, date_to, search)

            paginator = self.pagination_class()
            page = paginator.paginate_queryset(report_rows, request, view=self)

            start_index = (paginator.page.number - 1) * paginator.get_page_size(request)
            data = []
            for i, row in enumerate(page, start=start_index + 1):
                data.append({
                    'sr_no': i, 'order_id': row['order_id'], 'order_number': row['order_number'],
                    'order_time': row['order_time'], 'order_status': row['order_status'],
                    'customer_name': row['customer_name'], 'customer_phone': row['customer_phone'],
                    'customer_city': row['customer_city'], 'customer_email': row['customer_email'],
                    'payment_mode': row['payment_mode'], 'order_amount': float(row['order_amount']),
                    'platform_charge': float(row['platform_charge']),
                    'received_amount': float(row['received_amount']),
                    'order_age_days': row['order_age_days'],
                    'vendor_id': row['vendor_id'], 'vendor_name': row['vendor_name'],
                    'vendor_email': row['vendor_email'],
                })
            return paginator.get_paginated_response(data)
        except Exception as e:
            traceback.print_exc()
            return Response({'success': False, 'message': f'Error: {str(e)}'},
                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)   
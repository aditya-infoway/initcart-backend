# pos/views/branch_return_views.py
# NEW FILE — Branch panel ke liye return/refund views.
# Yeh koi naya model use nahi karte — wahi ecommerce.ReturnRequest /
# ecommerce.OrderRefund jo vendor panel use karta hai. Farak sirf itna
# hai ki vendor branch.user se resolve hota hai (BranchOrderListAPIView
# jaisa hi pattern), aur permission class branch-panel wali hai.

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils import timezone

from ecommerce.models.return_request import ReturnRequest
from ecommerce.models.refund import OrderRefund
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.return_serializers import (
    ReturnRequestListSerializer,
    VendorReturnActionSerializer,
)
from ecommerce.serializers.refund_serializers import RefundListSerializer

from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


def _resolve_vendor_for_branch_user(request):
    """
    ✅ Same resolution pattern jo BranchOrderListAPIView use karta hai —
    superadmin/employee ko ?branch_id= se override allow, warna
    user.get_effective_branch(). Vendor = Vendor.objects.get(user=branch.user).
    Returns (vendor, error_response). error_response None hai to sab theek hai.
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
            return None, Response({'error': 'Branch not found'}, status=404)

    try:
        vendor = Vendor.objects.get(user=branch.user) if branch.user else None
    except Vendor.DoesNotExist:
        vendor = None

    if not vendor:
        return None, Response(
            {'success': False, 'message': 'Vendor profile not found for this branch'},
            status=status.HTTP_404_NOT_FOUND
        )

    return vendor, None


class BranchReturnListAPIView(APIView):
    """
    GET /branch/returns/  — is branch (vendor) ke saare return requests.
    Same data jo VendorReturnListAPIView deta, bas branch-panel se aa raha.
    """
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        vendor, err = _resolve_vendor_for_branch_user(request)
        if err:
            return err

        qs = ReturnRequest.objects.filter(vendor=vendor).select_related(
            'order', 'order_item', 'customer'
        ).prefetch_related('return_images').order_by('-requested_at')

        status_filter = request.query_params.get('status')
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)

        return Response({
            'success': True,
            'data': ReturnRequestListSerializer(qs, many=True, context={'request': request}).data
        })


class BranchReturnActionAPIView(APIView):
    """
    POST /branch/returns/<id>/action/  — approve/reject, bilkul
    VendorReturnActionAPIView jaisa (refund auto-create bhi wahi trigger
    hota hai, sirf yahan branch ke access-check ke saath).
    """
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

        rr.vendor_remarks = serializer.validated_data.get('remarks', '')
        rr.vendor_responded_at = timezone.now()
        rr.status = 'vendor_approved' if serializer.validated_data['action'] == 'approve' else 'vendor_rejected'
        rr.save()

        # ✅ Approve hote hi online (razorpay) order ka refund record
        # auto-create hota hai — commission reversal bhi isi se chain hota hai
        if rr.status == 'vendor_approved':
            from ecommerce.utils.refund_helpers import create_refund_if_online
            create_refund_if_online(rr)

        return Response({
            'success': True,
            'message': f'Return {rr.status}',
            'data': ReturnRequestListSerializer(rr, context={'request': request}).data
        })


class BranchRefundListAPIView(APIView):
    """
    GET /branch/refunds/  — is branch (vendor) ke returned/refunded orders,
    read-only (jaisa VendorRefundListAPIView).
    """
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Orders"
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        vendor, err = _resolve_vendor_for_branch_user(request)
        if err:
            return err

        qs = OrderRefund.objects.filter(order_item__vendor=vendor).select_related(
            'return_request', 'return_request__customer', 'order', 'order_item'
        ).order_by('-created_at')

        return Response({
            'success': True,
            'data': RefundListSerializer(qs, many=True).data
        })
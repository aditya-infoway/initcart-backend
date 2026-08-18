# pos/views/bankpayment_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import datetime

from pos.models.bankpayment import BankPayment
from pos.models.settings import setting
from pos.serializers.bankpayment_serializers import BankPaymentSerializer
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class BankPaymentCreateView(APIView):
    """Create and list bank payments (BP, PBP, SRBP, STBP, STRBP)"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Bank-payment"  # ✅ ADD: Frontend route

    def get_branch(self, user):
        # ✅ CHANGE: getattr(user, "branch", None) → get_effective_branch()
        return user.get_effective_branch()

    def generate_voucher_number(self, branch):
        """
        Generate voucher number for ALL Bank Payments (BP and PBP share same sequence)
        Uses BP prefix from settings
        """
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BP", "BP") if settings_obj else "BP"
        
        # Get the last voucher number from ALL bank payments (both BP and PBP)
        last_voucher = BankPayment.objects.filter(
            branch=branch
        ).order_by("-id").first()
        
        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                parts = last_voucher.voucher_no.split("/")
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0
        
        # Calculate financial year
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year
        
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        
        # Generate next voucher number
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{prefix}/{fy}/{next_no}"
        
        return voucher_no

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'  # ✅ ADD

        # ✅ CHANGE: Branch selection logic → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ FIX: Employee ko bhi branch_id override allow karo
        branch_id_param = request.GET.get('branch_id')
        if branch_id_param:
            if is_superadmin or is_employee:  # ✅ Employee allow
                from pos.models.branch import Branch
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)

        payments = BankPayment.objects.filter(branch=branch).order_by("-date", "-created_at")
        paginator = StandardResultsSetPagination()
        paginated_payments = paginator.paginate_queryset(payments, request)
        serializer = BankPaymentSerializer(paginated_payments, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # ✅ CHANGE: get_branch() → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        payment_type = request.data.get("type")

        # Detect automatically
        if request.data.get("sales_return"):
            payment_type = "SRBP"
        elif request.data.get("purchase"):
            payment_type = "PBP"
        else:
            payment_type = payment_type or "BP"
        
        # Generate voucher number (same sequence for BP and PBP)
        voucher_no = self.generate_voucher_number(branch)
        
        data = {
            "bank_account": request.data.get("bank_account"),
            "op_account": request.data.get("op_account"),
            "voucher_no": voucher_no,
            "date": request.data.get("date"),
            "amount": request.data.get("amount"),
            "mode": request.data.get("mode", "UPI"),
            "cheque_no": request.data.get("cheque_no"),
            "cheque_date": request.data.get("cheque_date"),
            "cheque_clear_date": request.data.get("cheque_clear_date"),
            "narration": request.data.get("narration", ""),
            "type": payment_type,
        }
        
            # ✅ ENSURE request is in context
        serializer = BankPaymentSerializer(
            data=data,
            context={
                "branch": branch,
                "request": request   # ✅ MUST HAVE THIS
            }
        )
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    payment = serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
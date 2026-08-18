# pos/views/cashpayment_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import datetime

from pos.models.cashpayment import CashPayment
from pos.models.settings import setting
from pos.serializers.cashpayment_serializers import CashPaymentSerializer
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class CashPaymentCreateView(APIView):
    """Create and list cash payments (CP, PCP, SRCP, STCP, STRCP)"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Cash-Payment"  # ✅ ADD: Frontend route

    def get_branch(self, user):
        # ✅ CHANGE: getattr(user, "branch", None) → get_effective_branch()
        return user.get_effective_branch()

    def generate_voucher_number(self, branch):
        """
        Generate voucher number for ALL Cash Payments (CP and PCP share same sequence)
        Uses CP prefix from settings
        """
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CP", "CP") if settings_obj else "CP"
        
        # Get the last voucher number from ALL cash payments (both CP and PCP)
        last_voucher = CashPayment.objects.filter(
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

        payments = CashPayment.objects.filter(branch=branch).order_by("-date", "-created_at")
        paginator = StandardResultsSetPagination()
        paginated_payments = paginator.paginate_queryset(payments, request)
        serializer = CashPaymentSerializer(paginated_payments, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        # ✅ CHANGE: get_branch() → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        payment_type = request.data.get("type", "CP")
        
        # Generate voucher number (same sequence for CP and PCP)
        voucher_no = self.generate_voucher_number(branch)
        
        data = {
            "cash_account": request.data.get("cash_account"),
            "op_account": request.data.get("op_account"),
            "voucher_no": voucher_no,
            "date": request.data.get("date"),
            "amount": request.data.get("amount"),
            "mode": request.data.get("mode", "Cash"),
            "narration": request.data.get("narration", ""),
            "type": payment_type,
        }
        
        print(f"Creating Cash Payment - Type: {payment_type}, Voucher: {voucher_no}")
        print(f"Data: {data}")
        
        serializer = CashPaymentSerializer(data=data, context={"branch": branch, "request": request})
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    payment = serializer.save()
                print(f"Created Cash Payment: ID={payment.id}, Type={payment.type}, Voucher={payment.voucher_no}")
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                print(f"Validation Error: {e.messages}")
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        # Print validation errors for debugging
        print("Validation errors:", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    
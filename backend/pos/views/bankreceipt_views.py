# pos/views/bankreceipt_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import datetime

from pos.models.bankreceipt import BankReceipt  
from pos.models.settings import setting
from pos.serializers.bankreceipt_serializers import BankReceiptSerializer
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class BankReceiptCreateView(APIView):
    """Create and list bank receipts (BR, SBR, PRBR, STBR, STRBR, B2BSBR)"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Bank-receipt"  # ✅ ADD: Frontend route

    def get_branch(self, user):
        # ✅ CHANGE: getattr(user, "branch", None) → get_effective_branch()
        return user.get_effective_branch()

    def generate_voucher_number(self, branch, receipt_type='BR'):
        from datetime import datetime
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BR", "BR") if settings_obj else "BR"
        
        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"
        
        # Branch + FY pattern dono filter
        last_voucher = BankReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern
        ).order_by("-id").first()
        
        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0
        
        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"
        
        # Branch-wise uniqueness check
        while BankReceipt.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"
        
        print(f"🎫 BR Voucher: {voucher_no} - Branch: {branch.branch_name}")
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

        receipts = BankReceipt.objects.filter(branch=branch).order_by("-date", "-created_at")
        paginator = StandardResultsSetPagination()
        paginated_receipts = paginator.paginate_queryset(receipts, request)
        serializer = BankReceiptSerializer(paginated_receipts, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # ✅ CHANGE: get_branch() → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        receipt_type = request.data.get("type", "BR")
        
        # Generate voucher number (same sequence for BR and SBR)
        voucher_no = self.generate_voucher_number(branch, receipt_type)
        
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
            "type": receipt_type,
            "sales_entry": request.data.get("sales_entry"),
        }
        
        serializer = BankReceiptSerializer(data=data, context={"branch": branch, "request": request })
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    receipt = serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    
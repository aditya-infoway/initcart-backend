# pos/views/cashreceipt_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import datetime

from pos.models.cashreceipt import CashReceipt
from pos.models.settings import setting
from pos.serializers.cashreceipt_serializers import CashReceiptSerializer
from pos.utils.pagination import StandardResultsSetPagination

class CashReceiptCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        return getattr(user, "branch", None)

    def generate_voucher_number(self, branch, receipt_type='CR'):
        from datetime import datetime
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CR", "CR") if settings_obj else "CR"
        
        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"
        
        # ✅ Branch + FY pattern dono filter
        last_voucher = CashReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern  #  KEY FIX
        ).order_by("-id").first()
        
        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0
        
        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"
        
        # ✅ Branch-wise uniqueness check
        while CashReceipt.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"
        
        print(f" CR Voucher: {voucher_no} - Branch: {branch.branch_name}")
        return voucher_no

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            from pos.models.branch import Branch
            branch_id_param = request.GET.get('branch_id')
            if branch_id_param:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
            else:
                try:
                    branch = Branch.objects.get(user=user)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=400)
        else:
            branch = self.get_branch(user)
            if not branch:
                return Response({"detail": "User does not have a branch assigned."}, status=400)

        receipts = CashReceipt.objects.filter(branch=branch).order_by("-date", "-created_at")
        paginator = StandardResultsSetPagination()
        paginated_receipts = paginator.paginate_queryset(receipts, request)
        serializer = CashReceiptSerializer(paginated_receipts, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response(
                {"detail": "User does not have a branch assigned."},
                status=status.HTTP_400_BAD_REQUEST
            )

        receipt_type = request.data.get("type", "CR")
        
        # Generate voucher number (same sequence for CR and SCR)
        voucher_no = self.generate_voucher_number(branch, receipt_type)
        
        data = {
            "cash_account": request.data.get("cash_account"),
            "op_account": request.data.get("op_account"),
            "voucher_no": voucher_no,
            "date": request.data.get("date"),
            "amount": request.data.get("amount"),
            "narration": request.data.get("narration", ""),
            "type": receipt_type,
            "sales_entry": request.data.get("sales_entry"),
        }
        
        serializer = CashReceiptSerializer(data=data, context={"branch": branch})
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    receipt = serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
     
     
     
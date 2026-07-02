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

class BankPaymentCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        return getattr(user, "branch", None)

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

        payments = BankPayment.objects.filter(branch=branch).order_by("-date", "-created_at")
        paginator = StandardResultsSetPagination()
        
        paginated_payments = paginator.paginate_queryset(payments, request)
        serializer = BankPaymentSerializer(paginated_payments, many=True)
        
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response(
                {"detail": "User does not have a branch assigned."},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment_type = request.data.get("type")

        #  detect automatically
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
        
        serializer = BankPaymentSerializer(data=data, context={"branch": branch})
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    payment = serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    
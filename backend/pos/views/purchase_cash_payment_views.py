# pos/views/purchase_cash_payment_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from pos.models.cashpayment import CashPayment
from pos.models.purchaseentry import PurchaseMaster
from pos.serializers.cashpayment_serializers import CashPaymentSerializer

class PurchaseCashPaymentListView(APIView):
    """
    View to list cash payments that are linked to purchases (type='PCP')
    """
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        return getattr(user, "branch", None)

    def get(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response({"detail": "User does not have a branch assigned."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        # Get payments with type PCP (Purchase Cash Payment)
        payments = CashPayment.objects.filter(
            branch=branch, 
            type="PCP"  # PCP = Purchase Cash Payment
        ).order_by("-created_at")
        
        print(f"Found {payments.count()} purchase cash payments for branch {branch.id}")
        
        serializer = CashPaymentSerializer(payments, many=True)
        return Response(serializer.data)


class PurchaseCashPaymentCreateView(APIView):
    """
    Create cash payment against a purchase
    """
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        return getattr(user, "branch", None)

    def post(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response({"detail": "User does not have a branch assigned."},
                            status=status.HTTP_400_BAD_REQUEST)

        purchase_id = request.data.get("purchase_id")
        cash_account_id = request.data.get("cash_account")
        amount = request.data.get("amount")
        
        if not purchase_id:
            return Response({"error": "purchase_id is required"}, status=400)
        
        try:
            purchase = PurchaseMaster.objects.get(id=purchase_id, branch=branch)
        except PurchaseMaster.DoesNotExist:
            return Response({"error": "Purchase not found"}, status=404)
        
        # Check if payment already exists for this purchase
        existing = CashPayment.objects.filter(
            branch=branch,
            narration__icontains=f"Purchase {purchase.billNo}",
            type="PCP"
        ).first()
        
        if existing:
            return Response({
                "warning": "Payment already exists",
                "payment": CashPaymentSerializer(existing).data
            }, status=status.HTTP_200_OK)
        
        # Prepare data for cash payment
        payment_data = {
            "cash_account": cash_account_id,
            "op_account": purchase.partyName.id,
            "voucher_no": f"PCP/{purchase.billNo}",
            "date": request.data.get("date", purchase.date),
            "amount": amount or purchase.grand_total,
            "mode": "Cash",
            "narration": f"Payment against Purchase {purchase.billNo}",
            "type": "PCP"  # Important: PCP for Purchase Cash Payment
        }
        
        serializer = CashPaymentSerializer(data=payment_data, context={"branch": branch})
        
        if serializer.is_valid():
            try:
                payment = serializer.save()
                return Response({
                    "success": True,
                    "payment": CashPaymentSerializer(payment).data
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
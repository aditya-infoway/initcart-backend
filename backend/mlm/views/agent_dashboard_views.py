from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum

from mlm.models.agent import Agent
from mlm.models.agent_wallet import AgentWallet
from mlm.models.mlm_transaction import MLMTransaction
from ecommerce.models.order import Order
from users.models import User


class AgentDashboardAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:
            agent = Agent.objects.get(user=request.user)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=400)

        wallet = AgentWallet.objects.filter(user=request.user).first()

        wallet_balance = wallet.balance if wallet else 0

        total_earnings = MLMTransaction.objects.filter(
            user=request.user
        ).aggregate(total=Sum("amount"))["total"] or 0

        total_sales = Order.objects.filter(
            referral_agent=agent
        ).aggregate(total=Sum("final_amount"))["total"] or 0

        total_orders = Order.objects.filter(
            referral_agent=agent
        ).count()

        downline_count = User.objects.filter(
            referred_by=request.user
        ).count()

        return Response({

            "agent_name": agent.full_name,
            "wallet_balance": wallet_balance,
            "total_earnings": total_earnings,
            "total_sales": total_sales,
            "total_orders": total_orders,
            "downline_size": downline_count,
            "is_active_agent": agent.is_active_agent

        })
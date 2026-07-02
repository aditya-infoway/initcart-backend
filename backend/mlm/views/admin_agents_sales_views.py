from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.db.models import Sum

from ecommerce.models.order import Order
from mlm.models.agent import Agent


class AdminAgentSalesAPIView(APIView):

    permission_classes = [IsAdminUser]

    def get(self, request, agent_id):

        try:
            agent = Agent.objects.get(id=agent_id)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        orders = Order.objects.filter(
            referral_agent=agent
        ).order_by("-created_at")

        total_sales = orders.aggregate(
            total=Sum("final_amount")
        )["total"] or 0

        data = []

        for order in orders:

            data.append({

                "order_number": order.order_number,
                "customer": order.customer.email,
                "amount": order.final_amount,
                "status": order.order_status,
                "payment_status": order.payment_status,
                "date": order.created_at

            })

        return Response({

            "agent": agent.full_name,
            "total_sales": total_sales,
            "orders": data

        })
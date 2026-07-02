from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum
from django.db.models.functions import TruncMonth

from ecommerce.models.order import Order
from mlm.models.agent import Agent


class AgentMonthlySalesAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        agent = Agent.objects.get(user=request.user)

        sales = (
            Order.objects
            .filter(referral_agent=agent)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total_sales=Sum("final_amount"))
            .order_by("month")
        )

        data = []

        for s in sales:

            data.append({

                "month": s["month"].strftime("%Y-%m"),
                "sales": s["total_sales"]

            })

        return Response(data)
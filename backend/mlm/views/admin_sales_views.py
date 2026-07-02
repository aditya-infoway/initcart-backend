from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django.db.models import Sum

from ecommerce.models.order import Order


class AdminMLMSalesAPIView(APIView):

    permission_classes = [IsAdminUser]

    def get(self, request):

        orders = Order.objects.filter(
            referral_agent__isnull=False
        ).order_by("-created_at")

        total_sales = orders.aggregate(
            total=Sum("final_amount")
        )["total"] or 0

        data = []

        for order in orders:

            data.append({

                "order_number": order.order_number,
                "customer": order.customer.email,
                "agent": order.referral_agent.full_name,
                "agent_id": order.referral_agent.id,
                "amount": order.final_amount,
                "status": order.order_status,
                "payment_status": order.payment_status,
                "date": order.created_at

            })

        return Response({

            "total_sales": total_sales,
            "orders": data

        })
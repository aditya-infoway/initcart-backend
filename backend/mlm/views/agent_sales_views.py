# mlm/views/agent_sales_views.py

from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, Q
from datetime import datetime

from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from ecommerce.models.order import Order
from pos.models.salesentry import SalesMaster
from pos.models.branch import Branch

def get_pos_payment_status(sale):
    from decimal import Decimal
    from django.db.models import Sum as DjangoSum
    from pos.models.cashreceipt import CashReceipt as CR
    from pos.models.bankreceipt import BankReceipt as BR

    if sale.payment_terms.lower() in ['cash', 'bank']:
        return "paid"

    total_received = CR.objects.filter(
        sales_entry=sale
    ).aggregate(total=DjangoSum('amount'))['total'] or Decimal('0')

    total_received += BR.objects.filter(
        sales_entry=sale
    ).aggregate(total=DjangoSum('amount'))['total'] or Decimal('0')

    return "paid" if total_received >= sale.grand_total else "credit"
class AgentSalesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            agent = Agent.objects.get(user=request.user)
        except Agent.DoesNotExist:
            return Response({"error": "You are not an agent"}, status=400)

        settings = MLMSettings.objects.first()
        min_required = float(settings.minimum_sale_amount) if settings else 0
        threshold = Decimal(str(min_required))

        # ── WEBSITE ORDERS ──────────────────────────────────────────────
        website_orders = Order.objects.filter(
            Q(referral_agent=agent) | Q(customer=request.user)
        ).distinct().order_by("-created_at")

        # ── POS SALES ────────────────────────────────────────────────────
        branches = Branch.objects.filter(user=request.user)
        branch_ids = branches.values_list('id', flat=True)

        pos_sales = SalesMaster.objects.filter(
            Q(referral_agent=request.user) |
            Q(branch__in=branch_ids)
        ).distinct().order_by("-date", "-created_at")

        # ── MERGE ──────────────────────────────────────────────────────
        merged_orders = []

        # Website orders
        for order in website_orders:
            merged_orders.append({
                "order_number": order.order_number,
                "customer": order.customer.email if order.customer else "Unknown",
                "amount": float(order.final_amount),
                "status": order.order_status,
                "payment_status": order.payment_status,
                "date": order.created_at.isoformat(),
                "source": "website",
                "type": "website_order",
                "is_referral": order.referral_agent_id == agent.id,
                "is_own": order.customer_id == request.user.id,
                "commission_processed": order.mlm_commission_processed,
                "order_id": order.id,
            })

        # POS sales
        for sale in pos_sales:
            is_referral = sale.referral_agent_id == request.user.id if sale.referral_agent_id else False
            
            is_own = False
            customer_name = "Walk-in"
            if sale.customer:
                customer_name = sale.customer.account_name

            total_amount = sale.items.aggregate(
                total=Sum('net_amount')
            )['total'] or sale.grand_total

            merged_orders.append({
                "order_number": sale.bill_no,
                "customer": customer_name,
                "amount": float(total_amount),
                "status": "delivered" if not sale.is_cancelled else "cancelled",
                "payment_status": get_pos_payment_status(sale),
                "date": sale.created_at.isoformat(),
                "source": "pos",
                "type": "pos_sale",
                "is_referral": is_referral,
                "is_own": is_own,
                "commission_processed": sale.mlm_commission_processed,
                "order_id": sale.id,
            })

        # Sort by date (newest first)
        merged_orders.sort(key=lambda x: x["date"], reverse=True)

        # ── Calculate total sales ──────────────────────────────────────
        all_orders_asc = sorted(merged_orders, key=lambda x: x["date"])
        running_total = Decimal("0")
        crossed_order_id = None
        threshold_decimal = Decimal(str(min_required))

        for order_data in all_orders_asc:
            amount = Decimal(str(order_data["amount"]))
            if running_total < threshold_decimal:
                running_total += amount
                if running_total >= threshold_decimal:
                    crossed_order_id = order_data["order_number"]

        # ── Response ────────────────────────────────────────────────────
        total_orders = len(merged_orders)
        delivered_sales = sum(
            o["amount"] for o in merged_orders
            if o["status"].lower() in ["delivered", "confirmed", "completed", "paid"]
        )

        data = []
        for order_data in merged_orders:
            order_number = order_data["order_number"]

            if crossed_order_id is None:
                commission_eligible = False
                reason = "minimum_not_reached"
            elif order_number == crossed_order_id:
                commission_eligible = False
                reason = "threshold_crossing_order"
            elif agent.minimum_achieved_at:
                try:
                    order_date = datetime.fromisoformat(order_data["date"])
                    if order_date > agent.minimum_achieved_at:
                        commission_eligible = True
                        reason = "eligible"
                    else:
                        commission_eligible = False
                        reason = "placed_before_activation"
                except:
                    commission_eligible = False
                    reason = "date_error"
            else:
                commission_eligible = False
                reason = "not_active"

            data.append({
                "order_number": order_number,
                "customer": order_data["customer"],
                "amount": order_data["amount"],
                "status": order_data["status"],
                "payment_status": order_data["payment_status"],
                "date": order_data["date"],
                "source": order_data["source"],
                "type": order_data["type"],
                "is_referral": order_data["is_referral"],
                "is_own": order_data["is_own"],
                "commission_eligible": commission_eligible,
                "commission_reason": reason,
                "commission_processed": order_data["commission_processed"],
            })

        return Response({
            "agent": agent.full_name,
            "is_active": agent.is_active_agent,
            "total_sales": float(running_total),
            "delivered_sales": float(delivered_sales),
            "total_orders": total_orders,
            "minimum_required": min_required,
            "remaining_for_activation": max(0, min_required - float(running_total)),
            "minimum_achieved_at": agent.minimum_achieved_at.isoformat() if agent.minimum_achieved_at else None,
            "orders": data,
        })
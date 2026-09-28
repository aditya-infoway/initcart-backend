# mlm/views/agent_sales_views.py
from decimal import Decimal
from datetime import datetime
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, Q

from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from ecommerce.models.order import OrderItem
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
    """
    ✅ REWRITE: sales ab PER-ITEM dikhti hain (order-level nahi) — kyunki
    commission bhi ab item-level pe distribute hota hai (multi-vendor
    orders mein alag-alag items alag time pe deliver/refund hote hain).

    ✅ total_sales ab agent.total_sales (DB field) se aata hai — yehi
    field commission engine (is_agent_active, update_agent_sales,
    commission_reversal) use karta hai, isliye yeh page hamesha wahi
    number dikhayega jo actual commission-eligibility decide karta hai.
    Pehle yahan ek alag "running_total" loop se recompute hota tha jo
    kabhi kabhi DB field se mismatch ho jata tha (aur ek bug ki wajah se
    threshold cross hone ke baad freeze bhi ho jata tha) — ab woh poori
    tarah hata diya, sirf cross-check ke liye computed_running_total
    diya hai jo refunded/cancelled rows ko chhod ke non-refunded items
    ka simple sum hai.

    ✅ Refunded item apni row mein status='refunded' ke saath dikhta hai
    aur running-total(delivered_sales/computed_running_total) mein uska
    amount count NAHI hota — list mein dikhta hai taaki agent ko pata
    chale kaunsa product refund hua, lekin sales count se apne aap bahar
    hai.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            agent = Agent.objects.get(user=request.user)
        except Agent.DoesNotExist:
            return Response({"error": "You are not an agent"}, status=400)

        settings = MLMSettings.objects.first()
        min_required = float(settings.minimum_sale_amount) if settings else 0
        threshold_decimal = Decimal(str(min_required))

        # ── WEBSITE ORDER ITEMS (per-item) ──────────────────────────────
        item_qs = (
            OrderItem.objects
            .filter(Q(order__referral_agent=agent) | Q(order__customer=request.user))
            .select_related('order', 'product')
            .distinct()
            .order_by('-order__created_at')
        )

        merged_rows = []
        for item in item_qs:
            order = item.order
            is_refunded = item.item_status == 'refunded'
            product_name = getattr(item, 'product_name', None) or (
                item.product.name if item.product_id else "Item"
            )
            merged_rows.append({
                "order_number": order.order_number,
                "item_id": item.id,
                "row_key": f"{order.order_number}#item{item.id}",
                "product_name": product_name,
                "customer": order.customer.email if order.customer else "Unknown",
                "amount": float(item.total_price),
                "status": item.item_status,               # delivered / pending / refunded / etc
                "payment_status": order.payment_status,
                "date": order.created_at.isoformat(),
                "source": "website",
                "type": "website_order",
                "is_referral": order.referral_agent_id == agent.id,
                "is_own": order.customer_id == request.user.id,
                "commission_processed": item.mlm_commission_processed,
                "order_id": order.id,
                "is_refunded": is_refunded,
            })

        # ── POS SALES (unchanged — POS abhi bhi sale-level hai) ──────────
        branches = Branch.objects.filter(user=request.user)
        branch_ids = branches.values_list('id', flat=True)

        pos_sales = (
            SalesMaster.objects
            .filter(Q(referral_agent=request.user) | Q(branch__in=branch_ids))
            .distinct()
            .order_by("-date", "-created_at")
        )

        for sale in pos_sales:
            is_referral = sale.referral_agent_id == request.user.id if sale.referral_agent_id else False
            customer_name = sale.customer.account_name if sale.customer else "Walk-in"
            total_amount = sale.items.aggregate(total=Sum('net_amount'))['total'] or sale.grand_total
            is_cancelled = bool(sale.is_cancelled)

            merged_rows.append({
                "order_number": sale.bill_no,
                "item_id": None,
                "row_key": sale.bill_no,
                "product_name": None,
                "customer": customer_name,
                "amount": float(total_amount),
                "status": "cancelled" if is_cancelled else "delivered",
                "payment_status": get_pos_payment_status(sale),
                "date": sale.created_at.isoformat(),
                "source": "pos",
                "type": "pos_sale",
                "is_referral": is_referral,
                "is_own": False,
                "commission_processed": sale.mlm_commission_processed,
                "order_id": sale.id,
                "is_refunded": is_cancelled,
            })

        merged_rows.sort(key=lambda x: x["date"], reverse=True)

        # ── Cross-check running total — refunded/cancelled rows excluded ──
        all_rows_asc = sorted(merged_rows, key=lambda x: x["date"])
        running_total = Decimal("0")
        crossed_row_key = None
        threshold_crossed = False

        for row in all_rows_asc:
            if row["is_refunded"]:
                continue
            amount = Decimal(str(row["amount"]))
            running_total += amount
            if not threshold_crossed and running_total >= threshold_decimal:
                crossed_row_key = row["row_key"]
                threshold_crossed = True

        total_rows = len(merged_rows)
        delivered_sales = sum(
            r["amount"] for r in merged_rows
            if not r["is_refunded"] and r["status"].lower() in
            ["delivered", "confirmed", "completed", "paid"]
        )
        refunded_total = sum(r["amount"] for r in merged_rows if r["is_refunded"])

        data = []
        for row in merged_rows:
            if row["is_refunded"]:
                commission_eligible = False
                reason = "refunded"
            elif crossed_row_key is None:
                commission_eligible = False
                reason = "minimum_not_reached"
            elif row["row_key"] == crossed_row_key:
                commission_eligible = False
                reason = "threshold_crossing_order"
            elif agent.minimum_achieved_at:
                try:
                    row_date = datetime.fromisoformat(row["date"])
                    if row_date > agent.minimum_achieved_at:
                        commission_eligible = True
                        reason = "eligible"
                    else:
                        commission_eligible = False
                        reason = "placed_before_activation"
                except Exception:
                    commission_eligible = False
                    reason = "date_error"
            else:
                commission_eligible = False
                reason = "not_active"

            data.append({
                "order_number": row["order_number"],
                "product_name": row["product_name"],
                "customer": row["customer"],
                "amount": row["amount"],
                "status": row["status"],
                "payment_status": row["payment_status"],
                "date": row["date"],
                "source": row["source"],
                "type": row["type"],
                "is_referral": row["is_referral"],
                "is_own": row["is_own"],
                "is_refunded": row["is_refunded"],
                "commission_eligible": commission_eligible,
                "commission_reason": reason,
                "commission_processed": row["commission_processed"],
            })

        return Response({
            "agent": agent.full_name,
            "is_active": agent.is_active_agent,
            # ✅ DB truth — wahi field jo commission engine ke liye
            # eligibility decide karta hai
            "total_sales": float(agent.total_sales),
            # cross-check ke liye — non-refunded rows ka simple sum
            "computed_running_total": float(running_total),
            "delivered_sales": float(delivered_sales),
            "refunded_total": float(refunded_total),
            "total_orders": total_rows,
            "minimum_required": min_required,
            "remaining_for_activation": max(0, min_required - float(agent.total_sales)),
            "minimum_achieved_at": agent.minimum_achieved_at.isoformat() if agent.minimum_achieved_at else None,
            "orders": data,
        })
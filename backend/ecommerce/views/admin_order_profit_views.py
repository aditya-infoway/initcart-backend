# mlm/views/admin_order_profit_views.py
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication

from users.utils.permissions import IsSuperAdmin
from mlm.models.mlm_transaction import MLMTransaction
from mlm.models.profit_distribution import ProfitDistribution
from ecommerce.models.order import Order, OrderItem
from ecommerce.models.refund import OrderRefund


class AdminOrderProfitBreakdownAPIView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, order_number):
        # ── 1. Order ──────────────────────────────────────────────────
        try:
            order = Order.objects.select_related(
                "customer",
                "referral_agent",
                "referral_agent__user",
            ).get(order_number=order_number)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        # ── 2. Items ──────────────────────────────────────────────────
        items_qs = OrderItem.objects.filter(order=order).select_related("vendor", "product")

        # ✅ NEW — refunds for this order, keyed by order_item_id so each
        # item row can show its own refund state with no extra queries.
        refunds_qs = OrderRefund.objects.filter(order=order).select_related(
            "order_item", "return_request"
        )
        refunds_by_item = {r.order_item_id: r for r in refunds_qs}

        total_platform_profit   = Decimal("0")
        total_vendor_receivable = Decimal("0")
        total_refunded_profit   = Decimal("0")  # platform_profit of REFUNDED items only
        items_data = []

        for item in items_qs:
            pf = Decimal(str(item.platform_profit  or 0))
            vr = Decimal(str(item.vendor_receivable or 0))
            total_platform_profit   += pf
            total_vendor_receivable += vr

            is_refunded = item.item_status == 'refunded'
            refund = refunds_by_item.get(item.id)
            if is_refunded:
                total_refunded_profit += pf

            items_data.append({
                "product_name":      item.product_name,
                "sku":               item.sku or "—",
                "color":             item.color or "—",
                "size":              item.size  or "—",
                "quantity":          item.quantity,
                "unit_price":        float(item.unit_price),
                "total_price":       float(item.total_price),
                "vendor_receivable": float(vr),
                "platform_profit":   float(pf),
                "vendor_name":       item.vendor.business_name if item.vendor else "—",
                "item_status":       item.item_status,       
                "is_refunded":       is_refunded,            
                "refund": {                                  
                    "refund_id":            refund.refund_id,
                    "refund_amount":        float(refund.refund_amount),
                    "status":               refund.status,
                    "commission_reversed":  refund.commission_reversed,
                    "processed_at":         refund.processed_at.isoformat() if refund.processed_at else None,
                } if refund else None,
            })

        # ── 3. Config ─────────────────────────────────────────────────
        config = ProfitDistribution.objects.first()
        config_data = {
            "pos_percentage":     float(config.pos_percentage)     if config else 0,
            "service_percentage": float(config.service_percentage) if config else 0,
            "mlm_percentage":     float(config.mlm_percentage)     if config else 0,
            "company_percentage": float(config.company_percentage) if config else 0,
        }

        # ── 4. MLM Transactions for this order ───────────────────────
        # ✅ NOTE: this includes both positive commission rows AND
        # negative refund-reversal rows (amount < 0) — both matter for
        # showing "actually paid" net figures, and for the report to
        # reflect what really happened after a return.
        tx_qs = MLMTransaction.objects.filter(
            order=order
        ).select_related("user", "user__agent", "order_item").order_by("level", "created_at")

        mlm_chain            = []
        extra_profit_entries = []   # ✅ CHANGED — was a single `seller_extra` object,
                                     # now a list. A multi-item order can have several
                                     # pos/society profit rows (one per item) plus their
                                     # refund-reversal rows; a single object silently
                                     # overwrote earlier entries and hid reversals.
        total_mlm_paid       = Decimal("0")   # net (positive + reversal) = actual wallet impact
        total_pos_paid       = Decimal("0")
        total_society_paid   = Decimal("0")

        for tx in tx_qs:
            amount      = Decimal(str(tx.amount))
            tx_type     = tx.transaction_type
            is_reversal = amount < 0   # ✅ NEW — refund-driven negative entry
            agent_obj   = getattr(tx.user, "agent", None)
            agent_name  = agent_obj.full_name if agent_obj else tx.user.username

            tx_data = {
                "agent_name":   agent_name,
                "agent_type":   agent_obj.agent_type if agent_obj else "normal",
                "username":     tx.user.username,
                "amount":       float(amount),
                "level":        tx.level,
                "percentage":   float(tx.percentage),
                "type":         tx_type,
                "is_reversal":  is_reversal,                                            # ✅ NEW
                "product_name": tx.order_item.product_name if tx.order_item_id else None,  # ✅ NEW
                "date":         tx.created_at.isoformat(),
            }

            if tx_type == "upline":
                total_mlm_paid += amount
                mlm_chain.append(tx_data)
            elif tx_type in ("pos_profit", "service_profit"):
                if tx_type == "pos_profit":
                    total_pos_paid += amount
                else:
                    total_society_paid += amount
                extra_profit_entries.append(tx_data)

        total_agents_paid = total_mlm_paid + total_pos_paid + total_society_paid

        # ── 5. Company profit calculation ──────────────────────────────
        if config and total_platform_profit > Decimal("0"):
            pos_pool     = total_platform_profit * Decimal(str(config.pos_percentage))     / Decimal("100")
            soc_pool     = total_platform_profit * Decimal(str(config.service_percentage)) / Decimal("100")
            mlm_pool     = total_platform_profit * Decimal(str(config.mlm_percentage))     / Decimal("100")
            config_co    = total_platform_profit * Decimal(str(config.company_percentage)) / Decimal("100")

            undist_mlm   = max(Decimal("0"), mlm_pool - total_mlm_paid)
            undist_pos   = max(Decimal("0"), pos_pool - total_pos_paid)
            undist_soc   = max(Decimal("0"), soc_pool - total_society_paid)

            company_total = config_co + undist_mlm + undist_pos + undist_soc
        else:
            pos_pool = soc_pool = mlm_pool = config_co = Decimal("0")
            undist_mlm = undist_pos = undist_soc = Decimal("0")
            company_total = total_platform_profit

        # ── 6. Commission status ──────────────────────────────────────
        ref_agent = order.referral_agent
        if not ref_agent:
            commission_status = "no_agent"
        elif order.mlm_commission_processed:
            commission_status = "distributed"
        else:
            commission_status = "pending"

        referral_agent_info = None
        if ref_agent:
            referral_agent_info = {
                "id":         ref_agent.id,
                "full_name":  ref_agent.full_name,
                "agent_type": ref_agent.agent_type,
                "username":   ref_agent.user.username,
                "is_active":  ref_agent.is_active_agent,
                "status":     ref_agent.status,
            }

        # ── 7. Refund summary for this order ────────────────────────────
        refund_list = []
        total_refunded_amount = Decimal("0")
        for r in refunds_qs:
            total_refunded_amount += Decimal(str(r.refund_amount))
            refund_list.append({
                "refund_id":           r.refund_id,
                "product_name":        r.order_item.product_name,
                "refund_amount":       float(r.refund_amount),
                "status":              r.status,
                "commission_reversed": r.commission_reversed,
                "failure_reason":      r.failure_reason,
                "processed_at":        r.processed_at.isoformat() if r.processed_at else None,
                "created_at":          r.created_at.isoformat(),
            })

        total_items    = items_qs.count()
        refunded_items = sum(1 for i in items_data if i["is_refunded"])
        if refunded_items == 0:
            refund_status = "none"
        elif refunded_items == total_items:
            refund_status = "fully_refunded"
        else:
            refund_status = "partially_refunded"

        return Response({
            "order_info": {
                "order_number":    order.order_number,
                "customer_name":   order.billing_name or order.customer.username,
                "customer_email":  order.customer.email,
                "customer_phone":  order.billing_phone or "",
                "order_date":      order.created_at.isoformat(),
                "order_status":    order.order_status,
                "payment_status":  order.payment_status,
                "payment_method":  order.payment_method,
                "total_amount":    float(order.total_amount),
                "discount_amount": float(order.discount_amount or 0),
                "shipping_charge": float(order.shipping_charge or 0),
                "final_amount":    float(order.final_amount),
            },
            "profit_summary": {
                "total_platform_profit":    float(total_platform_profit),
                "total_vendor_receivable":  float(total_vendor_receivable),
                "total_agents_paid":        float(total_agents_paid),
                "commission_status":        commission_status,
                "referral_agent":           referral_agent_info,
                "mlm_commission_processed": order.mlm_commission_processed,
                "refund_status":            refund_status,                # ✅ NEW
                "total_refunded_amount":    float(total_refunded_amount), # ✅ NEW
                "total_refunded_profit":    float(total_refunded_profit), # ✅ NEW
                "refunded_items_count":     refunded_items,               # ✅ NEW
                "total_items_count":        total_items,                  # ✅ NEW
            },
            "config": config_data,
            "items": items_data,
            "refunds": refund_list,   # ✅ NEW
            "distribution": {
                "mlm_chain":            mlm_chain,
                "extra_profit_entries": extra_profit_entries,   # ✅ CHANGED (was seller_extra)
                "pools": {
                    "pos_pool":  float(pos_pool),
                    "soc_pool":  float(soc_pool),
                    "mlm_pool":  float(mlm_pool),
                    "config_co": float(config_co),
                },
                "paid": {
                    "mlm_paid":     float(total_mlm_paid),
                    "pos_paid":     float(total_pos_paid),
                    "society_paid": float(total_society_paid),
                },
                "undistributed": {
                    "mlm": float(undist_mlm),
                    "pos": float(undist_pos),
                    "soc": float(undist_soc),
                },
                "company": {
                    "configured_share":  float(config_co),
                    "undistributed_mlm": float(undist_mlm),
                    "undistributed_pos": float(undist_pos),
                    "undistributed_soc": float(undist_soc),
                    "total":             float(company_total),
                },
            },
        })


class AdminOrderProfitStatsAPIView(APIView):
    """
    Overall stats for the Order Profit Report page header cards.
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from django.db.models import Sum, Q

        total_platform = OrderItem.objects.filter(
            order__order_status="delivered"
        ).aggregate(total=Sum("platform_profit"))["total"] or Decimal("0")

        agents_agg = MLMTransaction.objects.aggregate(
            mlm=Sum("amount", filter=Q(transaction_type="upline")),
            pos=Sum("amount", filter=Q(transaction_type="pos_profit")),
            soc=Sum("amount", filter=Q(transaction_type="service_profit")),
        )
        total_mlm = Decimal(str(agents_agg["mlm"] or 0))
        total_pos = Decimal(str(agents_agg["pos"] or 0))
        total_soc = Decimal(str(agents_agg["soc"] or 0))
        total_agents_paid = total_mlm + total_pos + total_soc

        company_profit = total_platform - total_agents_paid

        total_orders  = Order.objects.count()
        agent_orders  = Order.objects.filter(referral_agent__isnull=False).count()
        direct_orders = Order.objects.filter(referral_agent__isnull=True).count()
        distributed   = Order.objects.filter(mlm_commission_processed=True).count()
        pending_dist  = Order.objects.filter(
            referral_agent__isnull=False,
            mlm_commission_processed=False
        ).count()

        # ✅ NEW — refund stats
        refund_agg = OrderRefund.objects.aggregate(
            total_amount=Sum("refund_amount", filter=Q(status="processed")),
            pending_amount=Sum("refund_amount", filter=Q(status="pending")),
        )
        total_refunded  = Decimal(str(refund_agg["total_amount"] or 0))
        pending_refunds = Decimal(str(refund_agg["pending_amount"] or 0))

        return Response({
            "stats": {
                "total_platform_profit": float(total_platform),
                "total_agents_paid":     float(total_agents_paid),
                "total_company_profit":  float(company_profit),
                "breakdown_agents": {
                    "mlm":     float(total_mlm),
                    "pos":     float(total_pos),
                    "society": float(total_soc),
                },
                "total_refunded_amount": float(total_refunded),   # ✅ NEW
                "pending_refund_amount": float(pending_refunds),  # ✅ NEW
            },
            "order_counts": {
                "total":         total_orders,
                "agent_orders":  agent_orders,
                "direct_orders": direct_orders,
                "distributed":   distributed,
                "pending":       pending_dist,
            },
            "refund_counts": {                                    # ✅ NEW
                "processed": OrderRefund.objects.filter(status="processed").count(),
                "pending":   OrderRefund.objects.filter(status="pending").count(),
                "failed":    OrderRefund.objects.filter(status="failed").count(),
            },
        })
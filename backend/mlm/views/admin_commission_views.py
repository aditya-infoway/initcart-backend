# mlm/views/admin_commission_views.py
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication

from users.utils.permissions import IsSuperAdmin
from mlm.models.agent import Agent
from mlm.models.mlm_transaction import MLMTransaction
from mlm.models.mlm_settings import MLMSettings
from mlm.models.profit_distribution import ProfitDistribution
from ecommerce.models.order import Order
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate


class AdminMLMOverviewAPIView(APIView):
    """
    Super Admin — complete MLM financial overview.
    Shows all agent commissions, company profit, POS/Society profits,
    undistributed MLM (chain shorter than total levels → company).
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        # ── Profit distribution config ────────────────────────────────
        config   = ProfitDistribution.objects.first()
        settings = MLMSettings.objects.first()

        config_data = {
            "pos_percentage":     float(config.pos_percentage)     if config else 0,
            "service_percentage": float(config.service_percentage) if config else 0,
            "mlm_percentage":     float(config.mlm_percentage)     if config else 0,
            "company_percentage": float(config.company_percentage) if config else 0,
        } if config else {}

        # ── All MLM transactions ──────────────────────────────────────
        all_tx = MLMTransaction.objects.select_related(
            "user", "order", "user__agent","pos_sale"
        ).order_by("-created_at")

        total_upline_paid   = Decimal("0")
        total_pos_paid      = Decimal("0")
        total_society_paid  = Decimal("0")

        upline_tx_list  = []
        pos_tx_list     = []
        society_tx_list = []

        level_summary = {}
        agent_summary = {}  # per-agent totals

        for tx in all_tx:
            amount  = Decimal(str(tx.amount))
            tx_type = tx.transaction_type

            agent_obj = getattr(tx.user, 'agent', None)
            agent_name = agent_obj.full_name if agent_obj else tx.user.username

            tx_data = {
                "id":           tx.id,
                "agent_name":   agent_name,
                "agent_type":   agent_obj.agent_type if agent_obj else "—",
                "username":     tx.user.username,
                "order": (
                    tx.order.order_number if tx.order
                    else tx.pos_sale.bill_no if tx.pos_sale
                    else None
                ),
                "amount":       float(amount),
                "level":        tx.level,
                "percentage":   float(tx.percentage),
                "type":         tx_type,
                "date":         tx.created_at.isoformat(),
            }

            # Per-agent summary
            uid = tx.user.id
            if uid not in agent_summary:
                agent_summary[uid] = {
                    "agent_id":      agent_obj.id if agent_obj else None,
                    "agent_name":    agent_name,
                    "agent_type":    agent_obj.agent_type if agent_obj else "—",
                    "username":      tx.user.username,
                    "upline":        Decimal("0"),
                    "pos_profit":    Decimal("0"),
                    "society_profit":Decimal("0"),
                    "total":         Decimal("0"),
                    "tx_count":      0,
                }
            agent_summary[uid]["total"]    += amount
            agent_summary[uid]["tx_count"] += 1

            if tx_type == "upline":
                total_upline_paid += amount
                upline_tx_list.append(tx_data)
                agent_summary[uid]["upline"] += amount

                lvl = tx.level
                if lvl not in level_summary:
                    level_summary[lvl] = {"level": lvl, "total": Decimal("0"), "count": 0}
                level_summary[lvl]["total"] += amount
                level_summary[lvl]["count"] += 1

            elif tx_type == "pos_profit":
                total_pos_paid += amount
                pos_tx_list.append(tx_data)
                agent_summary[uid]["pos_profit"] += amount

            elif tx_type == "service_profit":
                total_society_paid += amount
                society_tx_list.append(tx_data)
                agent_summary[uid]["society_profit"] += amount

        total_paid_out = total_upline_paid + total_pos_paid + total_society_paid

        # ── Company profit from delivered orders ──────────────────────
        # Total platform_profit from all delivered orders
        from ecommerce.models.order import OrderItem
        from django.db.models import Sum as DSum

        total_platform_profit = OrderItem.objects.filter(
            order__order_status="delivered"
        ).aggregate(total=DSum("platform_profit"))["total"] or Decimal("0")

        # Company profit = platform_profit * company_percentage / 100
        # + undistributed MLM (chain gaps)
        # We calculate it as: total_platform_profit - total_paid_out
        # (because paid_out = upline + pos + society)
        # But we also need to show breakdown:

        configured_company_profit = (
            total_platform_profit * Decimal(str(config.company_percentage)) / Decimal("100")
            if config else Decimal("0")
        )
        configured_mlm_profit = (
            total_platform_profit * Decimal(str(config.mlm_percentage)) / Decimal("100")
            if config else Decimal("0")
        )
        undistributed_mlm = configured_mlm_profit - total_upline_paid
        total_company_profit = configured_company_profit + undistributed_mlm

        # ── Per-agent list ────────────────────────────────────────────
        agents_list = [
            {
                **{k: float(v) if isinstance(v, Decimal) else v for k, v in info.items()},
            }
            for info in agent_summary.values()
        ]
        agents_list.sort(key=lambda x: x["total"], reverse=True)

        return Response({
            "config": config_data,
            "summary": {
                "total_platform_profit":   float(total_platform_profit),
                "total_paid_to_agents":    float(total_paid_out),
                "total_upline_commission": float(total_upline_paid),
                "total_pos_profit":        float(total_pos_paid),
                "total_society_profit":    float(total_society_paid),
                "configured_company_profit": float(configured_company_profit),
                "undistributed_mlm":       float(undistributed_mlm),
                "total_company_profit":    float(total_company_profit),
                "total_agents_paid":       len(agent_summary),
                "total_transactions":      len(upline_tx_list) + len(pos_tx_list) + len(society_tx_list),
            },
            "level_breakdown": [
                {"level": v["level"], "total": float(v["total"]), "count": v["count"]}
                for v in sorted(level_summary.values(), key=lambda x: x["level"])
            ],
            "agents_summary": agents_list,
            "upline_transactions":  upline_tx_list,
            "pos_transactions":     pos_tx_list,
            "society_transactions": society_tx_list,
        })


class AdminAgentCommissionDetailAPIView(APIView):
    """Single agent ka full commission detail — super admin ke liye"""
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request, agent_id):
        try:
            agent = Agent.objects.get(id=agent_id)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        transactions_qs = MLMTransaction.objects.filter(
            user=agent.user
        ).select_related("order", "pos_sale").order_by("-created_at")

        mlm_tx, pos_tx, soc_tx = [], [], []
        total_mlm = total_pos = total_soc = Decimal("0")
        level_summary = {}

        for tx in transactions_qs:
            amount  = Decimal(str(tx.amount))
            tx_type = tx.transaction_type
            tx_data = {
                "id":         tx.id,
                "order": (
                    tx.order.order_number if tx.order
                    else tx.pos_sale.bill_no if tx.pos_sale
                    else None
                ),
                "amount":     float(amount),
                "level":      tx.level,
                "percentage": float(tx.percentage),
                "type":       tx_type,
                "date":       tx.created_at.isoformat(),
            }

            if tx_type == "upline":
                total_mlm += amount
                mlm_tx.append(tx_data)
                lvl = tx.level
                if lvl not in level_summary:
                    level_summary[lvl] = {"level": lvl, "total": Decimal("0"), "count": 0}
                level_summary[lvl]["total"] += amount
                level_summary[lvl]["count"] += 1
            elif tx_type == "pos_profit":
                total_pos += amount
                pos_tx.append(tx_data)
            elif tx_type == "service_profit":
                total_soc += amount
                soc_tx.append(tx_data)

        settings = MLMSettings.objects.first()

        return Response({
            "agent": {
                "id":           agent.id,
                "full_name":    agent.full_name,
                "agent_type":   agent.agent_type,
                "status":       agent.status,
                "is_active":    agent.is_active_agent,
                "total_sales":  float(agent.total_sales),
                "minimum_required": float(settings.minimum_sale_amount) if settings else 0,
            },
            "summary": {
                "total_earnings":      float(total_mlm + total_pos + total_soc),
                "total_mlm":           float(total_mlm),
                "total_pos_profit":    float(total_pos),
                "total_society_profit":float(total_soc),
                "mlm_count":           len(mlm_tx),
            },
            "level_breakdown": [
                {"level": v["level"], "total": float(v["total"]), "count": v["count"]}
                for v in sorted(level_summary.values(), key=lambda x: x["level"])
            ],
            "mlm_transactions":     mlm_tx,
            "pos_transactions":     pos_tx,
            "society_transactions": soc_tx,
        })
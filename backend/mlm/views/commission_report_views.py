# mlm/views/commission_report_views.py

from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mlm.models.agent import Agent
from mlm.models.mlm_transaction import MLMTransaction
from mlm.models.mlm_settings import MLMSettings


class AgentCommissionReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agent = Agent.objects.filter(user=request.user).first()

        transactions_qs = (
            MLMTransaction.objects
            .filter(user=request.user)
            .select_related("order", "pos_sale")  # pos_sale bhi select karo
            .order_by("-created_at")
        )

        mlm_transactions = []
        pos_transactions = []
        society_transactions = []

        total_mlm_commission = Decimal("0.00")
        total_pos_profit = Decimal("0.00")
        total_society_profit = Decimal("0.00")

        level_summary = {}

        for tx in transactions_qs:
            amount = Decimal(str(tx.amount))
            tx_type = tx.transaction_type

            #  Order ya pos_sale dono handle karo
            ref = None
            ref_type = None
            source_name = None
            
            if tx.order:
                ref = tx.order.order_number
                ref_type = "website"
                source_name = "Website Order"
            elif tx.pos_sale:
                ref = tx.pos_sale.bill_no
                ref_type = "pos"
                if tx.pos_sale.branch:
                    source_name = f"POS ({tx.pos_sale.branch.branch_name})"
                else:
                    source_name = "POS Sale"

            tx_data = {
                "id": tx.id,
                "order": ref,
                "source": ref_type,
                "source_name": source_name,
                "amount": float(amount),
                "level": tx.level,
                "percentage": float(tx.percentage),
                "type": tx_type,
                "date": tx.created_at.isoformat(),
                "type_label": {
                    "pos_profit": "POS Profit",
                    "service_profit": "Society Profit",
                    "upline": "MLM Commission",
                }.get(tx_type, tx_type),
            }

            if tx_type == "pos_profit":
                total_pos_profit += amount
                pos_transactions.append(tx_data)
            elif tx_type == "service_profit":
                total_society_profit += amount
                society_transactions.append(tx_data)
            else:
                total_mlm_commission += amount
                mlm_transactions.append(tx_data)

                lvl = tx.level
                if lvl not in level_summary:
                    level_summary[lvl] = {"level": lvl, "total": Decimal("0"), "count": 0}
                level_summary[lvl]["total"] += amount
                level_summary[lvl]["count"] += 1

        total_all = total_mlm_commission + total_pos_profit + total_society_profit
        mlm_count = len(mlm_transactions)
        settings = MLMSettings.objects.first()

        return Response({
            "user_type": "agent" if agent else "customer",
            "agent_type": agent.agent_type if agent else "normal",

            "summary": {
                "total_commission": float(total_all),
                "total_mlm_commission": float(total_mlm_commission),
                "total_pos_profit": float(total_pos_profit),
                "total_society_profit": float(total_society_profit),
                "total_transactions": len(mlm_transactions) + len(pos_transactions) + len(society_transactions),
                "average_commission": float(total_mlm_commission / mlm_count) if mlm_count else 0,
                "agent_total_sales": float(agent.total_sales) if agent else 0,
                "is_active": agent.is_active_agent if agent else False,
                "minimum_required": float(settings.minimum_sale_amount) if settings else 0,
            },

            "level_breakdown": [
                {
                    "level": v["level"],
                    "total": float(v["total"]),
                    "count": v["count"],
                }
                for v in sorted(level_summary.values(), key=lambda x: x["level"])
            ],

            "transactions": mlm_transactions,
            "pos_transactions": pos_transactions,
            "society_transactions": society_transactions,
        })
        
        
        
        
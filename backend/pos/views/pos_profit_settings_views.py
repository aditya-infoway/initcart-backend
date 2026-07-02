# ============================================================
# FILE: pos/views/pos_profit_settings_views.py
# ACTION: REPLACE entire file
# ============================================================

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from decimal import Decimal

from pos.models.pos_profit_settings import POSProfitSettings
from mlm.models.mlm_transaction import MLMTransaction
from mlm.models.profit_distribution import ProfitDistribution


# ────────────────────────────────────────────────────────────
# 1. Toggle GET + UPDATE
# ────────────────────────────────────────────────────────────

class POSProfitSettingsView(APIView):
    """
    GET  → current toggle + config dikhao
    POST → toggle update karo (superadmin only)

    Toggle meaning:
      ON  (True)  = Walk-in 90% Branch, 10% Company
      OFF (False) = Walk-in pos_% Branch (from ProfitDistribution), rest Company
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def get(self, request):
        obj    = POSProfitSettings.objects.first()
        toggle = obj.walk_in_toggle if obj else True

        config = ProfitDistribution.objects.first()

        return Response({
            "success"       : True,
            "walk_in_toggle": toggle,
            "description"   : {
                "toggle_on" : "Walk-in customer → 90% Branch, 10% Company",
                "toggle_off": f"Walk-in customer → {config.pos_percentage if config else '?'}% Branch (from ProfitDistribution config), rest Company",
                "referral"  : "Koi bhi referral code diya → hamesha MLM distribution (toggle se independent)",
            },
            "profit_distribution_config": {
                "pos_percentage"    : float(config.pos_percentage)     if config else None,
                "mlm_percentage"    : float(config.mlm_percentage)     if config else None,
                "company_percentage": float(config.company_percentage)  if config else None,
                "service_percentage": float(config.service_percentage)  if config else None,
            } if config else None,
        })

    def post(self, request):
        if request.user.role != "superadmin":
            return Response({"success": False, "message": "Superadmin only"}, status=403)

        toggle = request.data.get("walk_in_toggle")
        if toggle is None:
            return Response({
                "success": False,
                "message": "walk_in_toggle required. Send: {\"walk_in_toggle\": true} or false"
            }, status=400)

        obj, _ = POSProfitSettings.objects.get_or_create(pk=1)
        obj.walk_in_toggle = bool(toggle)
        obj.save()

        return Response({
            "success"       : True,
            "message"       : "POS profit mode updated",
            "walk_in_toggle": obj.walk_in_toggle,
            "active_mode"   : "90/10 simple split" if obj.walk_in_toggle else "ProfitDistribution config %",
        })


# ────────────────────────────────────────────────────────────
# 2. Agent ka POS Commission Report
# ────────────────────────────────────────────────────────────

class POSCommissionReportView(APIView):
    """
    Logged-in agent/branch user ke POS commissions history.
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def get(self, request):
        user = request.user

        txns = (
            MLMTransaction.objects
            .filter(user=user, pos_sale__isnull=False)
            .select_related("pos_sale")
            .order_by("-created_at")
        )

        pos_profit_total     = Decimal("0")
        mlm_commission_total = Decimal("0")
        data = []

        for tx in txns:
            amt = Decimal(str(tx.amount))
            if tx.transaction_type == "pos_profit":
                pos_profit_total += amt
            else:
                mlm_commission_total += amt

            data.append({
                "id"        : tx.id,
                "bill_no"   : tx.pos_sale.bill_no  if tx.pos_sale else None,
                "sale_date" : tx.pos_sale.date.isoformat() if tx.pos_sale else None,
                "amount"    : float(amt),
                "level"     : tx.level,
                "percentage": float(tx.percentage),
                "type"      : tx.transaction_type,
                "type_label": {
                    "pos_profit"    : "POS Branch Profit",
                    "upline"        : "MLM Upline Commission",
                    "service_profit": "Society Agent Profit",
                }.get(tx.transaction_type, tx.transaction_type),
                "created_at": tx.created_at.isoformat(),
            })

        return Response({
            "success": True,
            "summary": {
                "total_pos_profit"     : float(pos_profit_total),
                "total_mlm_commission" : float(mlm_commission_total),
                "total_earned"         : float(pos_profit_total + mlm_commission_total),
                "total_transactions"   : len(data),
            },
            "transactions": data,
        })


# ────────────────────────────────────────────────────────────
# 3. Superadmin: All Branches POS Overview
# ────────────────────────────────────────────────────────────

class AdminPOSCommissionOverview(APIView):
    """
    Superadmin ke liye — sab branches ka POS commission summary.
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes     = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "superadmin":
            return Response({"success": False, "message": "Superadmin only"}, status=403)

        from django.db.models import Sum, Count

        summary = (
            MLMTransaction.objects
            .filter(pos_sale__isnull=False)
            .values("user__username", "transaction_type")
            .annotate(
                total_amount = Sum("amount"),
                count        = Count("id"),
            )
            .order_by("user__username")
        )

        return Response({
            "success": True,
            "data"   : list(summary),
        })
# ============================================================
# FILE: mlm/models/mlm_transaction.py
# ACTION: REPLACE the entire file with this
# ============================================================
# CHANGE: Added `pos_sale` nullable FK to SalesMaster
#         So one table handles both website orders AND POS sales
# ============================================================

from django.db import models
from users.models import User
from ecommerce.models.order import Order


class MLMTransaction(models.Model):

    TRANSACTION_TYPE = (
        ("upline",         "Upline Commission"),
        ("pos_profit",     "POS Agent Profit"),
        ("service_profit", "Society Agent Profit"),
    )

    user  = models.ForeignKey(User,  on_delete=models.CASCADE)

    # ── Website order (ecommerce) ──────────────────────────────────────
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mlm_transactions",
    )

    # ── POS sale (NEW) ─────────────────────────────────────────────────
    # Rule: either `order` OR `pos_sale` will be filled, never both
    pos_sale = models.ForeignKey(
        "pos.SalesMaster",          # string ref → avoids circular import
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mlm_transactions",
    )

    level      = models.IntegerField()
    percentage = models.DecimalField(max_digits=5,  decimal_places=2)
    amount     = models.DecimalField(max_digits=12, decimal_places=2)

    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        ref = self.order_id or self.pos_sale_id
        return (
            f"{self.user.username} | L{self.level} | "
            f"₹{self.amount} | {self.transaction_type} | ref={ref}"
        )
        
        
        
        
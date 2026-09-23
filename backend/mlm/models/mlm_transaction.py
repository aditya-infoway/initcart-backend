# mlm/models/mlm_transaction.py  (FULL FILE — replace your existing one with this)
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

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mlm_transactions",
    )

    # ✅ NAYA: item-level commission ke liye. Multi-vendor order mein
    # ek order ke andar 2+ alag commission-runs ho sakte hain (har
    # vendor ka item apni delivery pe apna commission trigger karta
    # hai) — is FK ke bina saari transactions sirf `order` se hi
    # linked hoti, aur refund reversal (jo ek specific item refund
    # karta hai) galti se DOOSRE vendor ke item ki commission bhi
    # reverse kar deta. Website orders ke liye set; POS sales ke liye
    # hamesha null (POS abhi bhi sale-level hai, item-level nahi).
    order_item = models.ForeignKey(
        "ecommerce.OrderItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mlm_transactions",
    )

    pos_sale = models.ForeignKey(
        "pos.SalesMaster",
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
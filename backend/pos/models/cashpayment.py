#pos/models/cashpayment.py
# ✅ UPDATED — stock_transfer FK added for "Stock Received" payments
# (branch pays superadmin against a received Stock Transfer, party is
# always that branch's own single "Sundry Creditor(Main)" account)

from django.db import models, transaction
from django.core.exceptions import ValidationError
from pos.models.branch import Branch
from pos.models.account import Account

class CashPayment(models.Model):
    date = models.DateField()
    voucher_no = models.CharField(max_length=50)

    cash_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="cash_payments"
    )
    op_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="op_payments"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    mode = models.CharField(max_length=20, blank=True, null=True)

    narration = models.TextField(blank=True)
    type = models.CharField(max_length=50, default="CP")
    created_at = models.DateTimeField(auto_now_add=True)
    
    sales_return = models.ForeignKey(
        'pos.SalesReturnMaster',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='cash_payments'
    )
    
    purchase = models.ForeignKey(
        'pos.PurchaseMaster',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='cash_payments'
    )

    # ✅ NEW — Stock Received link (branch → superadmin's "Sundry Creditor(Main)")
    stock_transfer = models.ForeignKey(
        'pos.StockTransfer',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='cash_payments'
    )

    def clean(self):
        """Validate only on CREATE"""
        if self._state.adding:
            if self.cash_account.current_balance < self.amount:
                raise ValidationError(
                    f"⚠ Cash account balance ({self.cash_account.current_balance}) "
                    f"is less than the payment amount ({self.amount})."
                )


    def save(self, *args, **kwargs):
        with transaction.atomic():
            is_new = self._state.adding
            self.full_clean()

            if is_new:
                # 🔻 CASH ACCOUNT (money goes OUT)
                self.cash_account.current_balance -= self.amount
                self.cash_account.save(update_fields=["current_balance"])

                should_update_party = True

                # ✅ FIX: Cash/Bank Purchase - Supplier balance nahi badalna
                if self.purchase and self.purchase.terms.lower() != "credit":
                    should_update_party = False
                    print(f"Cash Purchase PCP - Supplier balance unchanged")

                # ✅ FIX: Sales Return Cash (SRCP) - Customer balance nahi badalna
                # Sirf Credit Sales Return me customer Dr badhega
                if self.sales_return and self.type == "SRCP":
                    should_update_party = False
                    print(f"SRCP - Cash Sales Return, Customer balance unchanged")

                # ✅ Stock Received payment (STCP) → Sundry Creditor(Main) ka
                # Cr due kam karo — default should_update_party=True already
                # covers this, no special-case needed.

                if should_update_party:
                    if self.op_account.current_drcr == "Dr":
                        if self.amount > self.op_account.current_balance:
                            self.op_account.current_balance = self.amount - self.op_account.current_balance
                            self.op_account.current_drcr = "Cr"
                        elif self.amount < self.op_account.current_balance:
                            self.op_account.current_balance -= self.amount
                        else:
                            self.op_account.current_balance = 0
                    else:
                        if self.amount > self.op_account.current_balance:
                            self.op_account.current_balance = self.amount - self.op_account.current_balance
                            self.op_account.current_drcr = "Dr"
                        elif self.amount < self.op_account.current_balance:
                            self.op_account.current_balance -= self.amount
                        else:
                            self.op_account.current_balance = 0

                    self.op_account.save(update_fields=["current_balance", "current_drcr"])
                else:
                    print(f"✅ Party balance NOT updated for SRCP/PCP")

            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.voucher_no} - {self.amount}"
    
    
    
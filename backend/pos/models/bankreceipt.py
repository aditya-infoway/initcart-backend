from django.db import models, transaction
from pos.models.account import Account
from pos.models.branch import Branch

class BankReceipt(models.Model):
    MODE_CHOICES = [
        ('NEFT', 'NEFT'),
        ('RTGS', 'RTGS'),
        ('IMPS', 'IMPS'),
        ('UPI', 'UPI'),
        ('CHEQUE', 'Cheque'),
    ]

    TYPE_CHOICES = [
        ('BR', 'Bank Receipt'),
        ('SBR', 'Sales Bank Receipt'),
        ('PRBR', 'Purchase Return Bank Receipt'),  # ✅ ADD
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    bank_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='bank_receipts')
    op_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='bank_receipt_op_accounts')
    voucher_no = models.CharField(max_length=50)
    date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='UPI')
    cheque_no = models.CharField(max_length=50, blank=True, null=True)
    cheque_date = models.DateField(blank=True, null=True)
    cheque_clear_date = models.DateField(blank=True, null=True)
    narration = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='BR')
    purchase_return = models.ForeignKey(
        'pos.PurchaseReturnMaster',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='bank_receipts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sales_entry = models.ForeignKey(
        'pos.SalesMaster', on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"{self.voucher_no} - {self.amount}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['branch', 'voucher_no'], name='unique_br_per_branch')
        ]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            is_new = self._state.adding

            if is_new:
                # 🔺 BANK ACCOUNT (money comes IN)
                self.bank_account.current_balance += self.amount
                self.bank_account.save(update_fields=["current_balance"])

                should_update_party = False

                # ✅ Credit Sale payment → Customer Dr kam karo
                if self.sales_entry and self.sales_entry.payment_terms.lower() == "credit":
                    should_update_party = True
                elif self.type == "SBR" and not self.sales_entry:
                    should_update_party = True

                # ✅ Purchase Return receipt — party balance NAHI badle
                if self.purchase_return:
                    should_update_party = False
                    print(f"ℹ️ PRBR - Purchase Return receipt, party balance unchanged")

                if should_update_party:
                    print(f"💰 Updating party balance for credit payment")
                    if self.op_account.current_drcr == "Cr":
                        if self.amount > self.op_account.current_balance:
                            self.op_account.current_balance = self.amount - self.op_account.current_balance
                            self.op_account.current_drcr = "Dr"
                        elif self.amount < self.op_account.current_balance:
                            self.op_account.current_balance -= self.amount
                        else:
                            self.op_account.current_balance = 0
                    else:  # Dr
                        if self.amount > self.op_account.current_balance:
                            self.op_account.current_balance = self.amount - self.op_account.current_balance
                            self.op_account.current_drcr = "Cr"
                        elif self.amount < self.op_account.current_balance:
                            self.op_account.current_balance -= self.amount
                        else:
                            self.op_account.current_balance = 0

                    self.op_account.save(update_fields=["current_balance", "current_drcr"])
                    print(f"✅ Party balance updated: {self.op_account.current_balance} {self.op_account.current_drcr}")
                else:
                    print(f"ℹ️ No party balance update needed")

            super().save(*args, **kwargs)
# pos/models/cashreceipt.py
# ✅ UPDATED — Stock Transfer Cash Receipt (STCR) support added

from django.db import models, transaction
from pos.models.account import Account
from pos.models.branch import Branch
from decimal import Decimal


class CashReceipt(models.Model):
    TYPE_CHOICES = [
        ('CR', 'Cash Receipt'),
        ('SCR', 'Sales Cash Receipt'),
        ('PRCR', 'Purchase Return Cash Receipt'),
        ('STCR', 'Stock Transfer Cash Receipt'),  # ✅ ADD
        ('STRCR', 'Stock Return Cash Receipt'),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    cash_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='cash_receipts')
    op_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='cash_receipt_op_accounts')
    voucher_no = models.CharField(max_length=50)
    date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    narration = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='CR')
    purchase_return = models.ForeignKey(
        'pos.PurchaseReturnMaster',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='cash_receipts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sales_entry = models.ForeignKey(
        'pos.SalesMaster', on_delete=models.SET_NULL, null=True, blank=True
    )

    # ✅ NEW — Stock Transfer link (superadmin → branch receivable)
    stock_transfer = models.ForeignKey(
        'pos.StockTransfer',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='cash_receipts'
    )
        # ✅ NEW — Stock Return link (company → branch refund)
    stock_return = models.ForeignKey(
        'pos.StockReturn', on_delete=models.CASCADE, null=True, blank=True, related_name='cash_receipts'
    )

    def __str__(self):
        return f"{self.voucher_no} - {self.amount}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['branch', 'voucher_no'], name='unique_cr_per_branch')
        ]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            is_new = self._state.adding

            if is_new:

                self.cash_account.current_balance += Decimal(str(self.amount))
                self.cash_account.save(update_fields=["current_balance"])

                should_update_party = False

                if self.sales_entry and self.sales_entry.payment_terms.lower() == "credit":
                    should_update_party = True
                elif self.type == "SCR" and not self.sales_entry:
                    should_update_party = True

                if self.stock_transfer:
                    should_update_party = True
                    
                if self.stock_return:       
                    should_update_party = True    

                if self.purchase_return:
                    should_update_party = False
                    print(f"ℹ️ PRCR - Purchase Return receipt, party balance unchanged")

                if should_update_party:
                   
                    amount_decimal = Decimal(str(self.amount))
                    current_balance = Decimal(str(self.op_account.current_balance))
                    
                    if self.op_account.current_drcr == "Cr":
                        if amount_decimal > current_balance:
                            self.op_account.current_balance = amount_decimal - current_balance
                            self.op_account.current_drcr = "Dr"
                        elif amount_decimal < current_balance:
                            self.op_account.current_balance = current_balance - amount_decimal
                        else:
                            self.op_account.current_balance = Decimal('0.00')
                    else:  # Dr
                        if amount_decimal > current_balance:
                            self.op_account.current_balance = amount_decimal - current_balance
                            self.op_account.current_drcr = "Cr"
                        elif amount_decimal < current_balance:
                            self.op_account.current_balance = current_balance - amount_decimal
                        else:
                            self.op_account.current_balance = Decimal('0.00')

                    self.op_account.save(update_fields=["current_balance", "current_drcr"])
                    print(f"✅ Party balance updated: {self.op_account.current_balance} {self.op_account.current_drcr}")
                else:
                    print(f"ℹ️ No party balance update needed")

            super().save(*args, **kwargs)
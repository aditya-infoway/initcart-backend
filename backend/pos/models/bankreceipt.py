# pos/models/bankreceipt.py
# ✅ UPDATED — Stock Transfer Bank Receipt (STBR) support added

from django.db import models, transaction
from pos.models.account import Account
from pos.models.branch import Branch
from decimal import Decimal


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
        ('PRBR', 'Purchase Return Bank Receipt'),
        ('STBR', 'Stock Transfer Bank Receipt'),
        ('STRBR', 'Stock Return Bank Receipt'),
        ('B2BSBR', 'B2B Sale Bank Receipt'),
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

    # ✅ NEW — Stock Transfer link (superadmin → branch receivable)
    stock_transfer = models.ForeignKey(
        'pos.StockTransfer',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='bank_receipts'
    )
    
    stock_return = models.ForeignKey(
        'pos.StockReturn', on_delete=models.CASCADE, null=True, blank=True, related_name='bank_receipts'
    )
    
    b2b_sale = models.ForeignKey(
        'pos.B2BSale', on_delete=models.CASCADE, null=True, blank=True, related_name='bank_receipts'
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

            amount_decimal = Decimal(str(self.amount))
            
            self.bank_account.current_balance = Decimal(str(self.bank_account.current_balance)) + amount_decimal
            self.bank_account.save(update_fields=["current_balance"])

            should_update_party = False

            if self.sales_entry and self.sales_entry.payment_terms.lower() == "credit":
                should_update_party = True
            elif self.type == "SBR" and not self.sales_entry:
                should_update_party = True

            if self.stock_transfer:
                should_update_party = True
                
            if self.stock_return:             
                should_update_party = True 
                
            if self.b2b_sale:
                should_update_party = True       

            if self.purchase_return:
                should_update_party = False
                print(f" PRBR - Purchase Return receipt, party balance unchanged")

            if should_update_party:
                print(f" Updating party balance for credit payment")
                
                #  Sabko Decimal mein convert karo
                current_balance = Decimal(str(self.op_account.current_balance))
                amount_decimal = Decimal(str(self.amount))
                
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
                print(f" Party balance updated: {self.op_account.current_balance} {self.op_account.current_drcr}")
            else:
                print(f"No party balance update needed")

        super().save(*args, **kwargs)
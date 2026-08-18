# pos/models/contra.py

from django.db import models, transaction
from django.core.exceptions import ValidationError
from pos.models.branch import Branch
from pos.models.account import Account
from pos.models.mixins import CreatedByMixin

class Contra(CreatedByMixin, models.Model):
    TYPE_CHOICES = (
        ("Cash Deposit", "Cash Deposit"),
        ("Cash Withdrawal", "Cash Withdrawal"),
        ("Bank Transfer", "Bank Transfer"),
    )

    date = models.DateField()
    voucher_no = models.CharField(max_length=50)  # ❌ REMOVE unique=True

    cash_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="cash_payments"
    )
    op_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="op_payments"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    narration = models.TextField(blank=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # ✅ Branch + voucher_no unique together (branch-wise unique)
        unique_together = ['branch', 'voucher_no']

    def __str__(self):
        return f"{self.voucher_no} - {self.amount}"

    def clean(self):
        if self.cash_account == self.op_account:
            raise ValidationError("Cash and opposite accounts cannot be the same.")

    def save(self, *args, **kwargs):
        if not self.pk:
            self.clean()

            with transaction.atomic():
                if self.type == "Cash Deposit":
                    if self.cash_account.current_balance < self.amount:
                        raise ValidationError("Insufficient balance in Cash Account.")
                    self.cash_account.current_balance -= self.amount
                    self.op_account.current_balance += self.amount

                elif self.type == "Cash Withdrawal":
                    if self.op_account.current_balance < self.amount:
                        raise ValidationError("Insufficient balance in Bank Account.")
                    self.op_account.current_balance += self.amount
                    self.cash_account.current_balance -= self.amount

                elif self.type == "Bank Transfer":
                    if self.cash_account.current_balance < self.amount:
                        raise ValidationError("Insufficient balance in From Account.")
                    self.cash_account.current_balance -= self.amount
                    self.op_account.current_balance += self.amount

                self.cash_account.save()
                self.op_account.save()
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
            
            
            
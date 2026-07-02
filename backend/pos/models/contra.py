#pos/models/contra.py
from django.db import models, transaction
from django.core.exceptions import ValidationError
from pos.models.branch import Branch
from pos.models.account import Account

class Contra(models.Model):
    TYPE_CHOICES = (
        ("Cash Deposit", "Cash Deposit"),
        ("Cash Withdrawal", "Cash Withdrawal"),
        ("Bank Transfer", "Bank Transfer"),
    )

    date = models.DateField()
    voucher_no = models.CharField(max_length=50, unique=True)  # Add unique=True

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
        # Ensure voucher_no is unique per branch
        unique_together = ['branch', 'voucher_no']

    def __str__(self):
        return f"{self.voucher_no} - {self.amount}"

    def clean(self):
        # Prevent selecting the same account for both sides
        if self.cash_account == self.op_account:
            raise ValidationError("Cash and opposite accounts cannot be the same.")

    def save(self, *args, **kwargs):
        if not self.pk:  # Only run on create
            self.clean()  # Validate first

            with transaction.atomic():
                # Update balances based on type
                if self.type == "Cash Deposit":
                    # Cash goes out, Bank receives
                    if self.cash_account.current_balance < self.amount:
                        raise ValidationError("Insufficient balance in Cash Account.")
                    self.cash_account.current_balance -= self.amount
                    self.op_account.current_balance += self.amount

                elif self.type == "Cash Withdrawal":
                    # Bank goes out, Cash receives
                    if self.op_account.current_balance < self.amount:
                        raise ValidationError("Insufficient balance in Bank Account.")
                    self.op_account.current_balance += self.amount
                    self.cash_account.current_balance -= self.amount

                elif self.type == "Bank Transfer":
                    # From cash_account to op_account
                    if self.cash_account.current_balance < self.amount:
                        raise ValidationError("Insufficient balance in From Account.")
                    self.cash_account.current_balance -= self.amount
                    self.op_account.current_balance += self.amount

                # Save updated account balances
                self.cash_account.save()
                self.op_account.save()

                # Finally save this contra entry
                super().save(*args, **kwargs)
        else:
            # For updates, you can decide whether to allow or block balance changes
            super().save(*args, **kwargs)
            
            

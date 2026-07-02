# models/journal_master.py
from django.db import models,transaction
from pos.models.account import Account
from decimal import Decimal
from pos.models.branch import Branch

class JournalMaster(models.Model):
    date = models.DateField()
    voucher_no = models.CharField(max_length=50, unique=True)
    reference_no = models.CharField(max_length=50, blank=True, null=True)

    total_debit = models.DecimalField(max_digits=12, decimal_places=2)
    total_credit = models.DecimalField(max_digits=12, decimal_places=2)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.voucher_no

class JournalEntry(models.Model):
    journal = models.ForeignKey(
        JournalMaster,
        related_name="entries",
        on_delete=models.CASCADE
    )

    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    narration = models.CharField(max_length=255, blank=True)
    
    from decimal import Decimal

    def save(self, *args, **kwargs):
        with transaction.atomic():
            is_new = self._state.adding
            self.full_clean()

            if is_new:
                acc = self.account
                balance = Decimal(acc.current_balance or 0)

                debit_amt = Decimal(self.debit or 0)
                credit_amt = Decimal(self.credit or 0)

                # RULE:
                # Debit  -> PLUS
                # Credit -> MINUS
                balance = balance + debit_amt - credit_amt

                if balance >= 0:
                    acc.current_balance = balance
                    #acc.current_drcr = "Dr"
                else:
                    acc.current_balance = abs(balance)
                    acc.current_drcr = "Cr"

                acc.save(update_fields=["current_balance", "current_drcr"])

            super().save(*args, **kwargs)

                
    def __str__(self):
        return f"{self.account} - {self.debit}/{self.credit}"

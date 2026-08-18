# pos/models/account.py
from django.db import models
from pos.models.branch import Branch
from pos.models.mixins import CreatedByMixin

class Account(CreatedByMixin, models.Model):
    DRCR_CHOICES = (
        ("Dr", "Receivable"),
        ("Cr", "Payable"),
    )
    GROUP_CHOICES = (
        ('Customer', 'Customer'),
        ('Supplier', 'Supplier'),
        ('Bank Account', 'Bank Account'),
        ('Case In Hand', 'Case In Hand'),
        ('Customer - Sundry Debitor', 'Customer - Sundry Debitor'),
        ('Supplier - Sundry Creditor', 'Supplier - Sundry Creditor'),
        ('Sundry Debitor(Internal)', 'Sundry Debitor(Internal)'),
        ('Sundry Creditor(Internal)', 'Sundry Creditor(Internal)'),
        ('Sundry Creditor(Main)', 'Sundry Creditor(Main)'),
    )

    account_name = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    group = models.CharField(max_length=50, choices=GROUP_CHOICES)
    opening_balance = models.DecimalField(max_digits=25, decimal_places=2, default=0)
    drcr = models.CharField(max_length=2, choices=DRCR_CHOICES)

    address = models.TextField(blank=True)
    country = models.CharField(max_length=50, blank=True)
    state = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=50, blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    mobile = models.CharField(max_length=10, blank=True)
    email = models.EmailField(max_length=254, blank=True, null=True)
    
    current_balance = models.DecimalField(max_digits=25, decimal_places=2, default=0)
    current_drcr = models.CharField(max_length=2, choices=DRCR_CHOICES, blank=True, null=True)

    gst_no = models.CharField(max_length=15, blank=True)
    pan_card = models.CharField(max_length=10, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        # ✅ FIX: Current balance always equals opening balance for now
        # (Jab tak transactions implement nahi hote)
        if not self.pk:  # New record
            self.current_balance = self.opening_balance
            self.current_drcr = self.drcr
        else:
            # Check if we should update
            should_update = False
            
            # Option 1: Check if opening_balance changed
            try:
                old_instance = Account.objects.get(pk=self.pk)
                if old_instance.opening_balance != self.opening_balance:
                    should_update = True
            except Account.DoesNotExist:
                should_update = True
            
            # Option 2: Force update if current_balance is 0 but opening_balance is not
            if self.current_balance == 0 and self.opening_balance != 0:
                should_update = True
                
            # Option 3: Force update if current_drcr is null or empty
            if not self.current_drcr:
                should_update = True
            
            if should_update:
                self.current_balance = self.opening_balance
                self.current_drcr = self.drcr
                
        super().save(*args, **kwargs)

    def __str__(self):
        return self.account_name
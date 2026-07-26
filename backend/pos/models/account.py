# pos/models/account.py
from django.db import models
from pos.models.branch import Branch

class Account(models.Model):
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

    # Basic Information
    account_name = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    group = models.CharField(max_length=50, choices=GROUP_CHOICES)
    opening_balance = models.DecimalField(max_digits=25, decimal_places=2, default=0)
    drcr = models.CharField(max_length=2, choices=DRCR_CHOICES)

    # Contact Details
    address = models.TextField(blank=True)
    country = models.CharField(max_length=50, blank=True)  # New field
    state = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=50, blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    mobile = models.CharField(max_length=10, blank=True)
    email = models.EmailField(max_length=254, blank=True, null=True)
    
    current_balance = models.DecimalField(max_digits=25, decimal_places=2, default=0)
    current_drcr = models.CharField(max_length=2, choices=DRCR_CHOICES, blank=True, null=True)

    # Legal & Financial
    gst_no = models.CharField(max_length=15, blank=True)
    pan_card = models.CharField(max_length=10, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if self.pk is None:
            self.current_balance = self.opening_balance
            self.current_drcr = self.drcr
        super().save(*args, **kwargs)

    def __str__(self):
        return self.account_name
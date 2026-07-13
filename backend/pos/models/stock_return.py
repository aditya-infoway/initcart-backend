# pos/models/stock_return.py


from django.db import models, transaction
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.models.items import items, itemvariants
from datetime import datetime

User = get_user_model()


def get_financial_year(now=None):
    """
    April-March financial year string banata hai, e.g. "26-27"
    """
    now = now or datetime.now()
    year = now.year
    if now.month >= 4:
        fy_start, fy_end = year, year + 1
    else:
        fy_start, fy_end = year - 1, year
    return f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"


class ReturnSequence(models.Model):
    """
    Har financial year ke liye ek hi row — global running counter,
    BranchOrder.OrderSequence jaisa hi. select_for_update() se atomically
    increment hota hai, taaki concurrent return-creation requests (do
    branches ek hi second mein return karein) mein bhi kabhi duplicate
    ya skipped number na bane.
    """
    financial_year = models.CharField(max_length=10, unique=True)  # e.g. "26-27"
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Return Sequence"
        verbose_name_plural = "Return Sequences"
    
    def __str__(self):
        return f"FY {self.financial_year} → last used: {self.last_number}"

    @classmethod
    def get_next_number(cls, financial_year: str) -> int:
        """
        Atomically FY ka agla number nikaalta hai aur turant save karta hai.
        Hamesha ek transaction.atomic() block ke andar call hona chahiye
        (StockReturn.save() mein already wrapped hai).
        """
        seq, _ = cls.objects.select_for_update().get_or_create(
            financial_year=financial_year,
            defaults={'last_number': 0},
        )
        seq.last_number += 1
        seq.save(update_fields=['last_number'])
        return seq.last_number


class StockReturn(models.Model):
    """
    Stock Return from branch to company (superadmin)
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),          # Branch ne return request bheji
        ('packaging_ready', 'Packaging Ready'),  # Branch ne packaging complete kar li
        ('approved', 'Approved'),         # Superadmin ne approve kar diya
        ('received', 'Received'),         # Superadmin ne received kar liya
        ('rejected', 'Rejected'),         # Superadmin ne reject kar diya
        ('cancelled', 'Cancelled'),       # Branch ne cancel kar diya
    ]

    return_no = models.CharField(max_length=50, unique=True)  # e.g. RTN/UGF/26-27/0001
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='stock_returns_sent')
    to_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='stock_returns_received')

    # Original stock transfer reference
    source_transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_returns'
    )

    # Original order reference (if from order)
    source_order = models.ForeignKey(
        'pos.BranchOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_returns'
    )

    return_date = models.DateField()
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_returns')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_returns')
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_returns')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.return_no} | {self.branch} → {self.to_branch} | {self.status}"

    def save(self, *args, **kwargs):
        if not self.return_no:
            from pos.models.settings import setting
            settings_obj = setting.objects.filter(branch=self.branch).first()
            prefix = getattr(settings_obj, 'SR', 'RTN') if settings_obj else 'RTN'

            fy = get_financial_year()

            # Branch's own code — sirf DISPLAY format ko affect karta hai,
            # counter ko nahi (BranchOrder ke exact same pattern)
            branch_code = ""
            if self.branch_id and self.branch and self.branch.branch_code:
                branch_code = self.branch.branch_code.strip().upper()

            # ✅ Ek hi global, atomic counter per FY — sab branches ke liye
            #    shared, chahe branch_code set ho ya blank ho.
            with transaction.atomic():
                next_no = ReturnSequence.get_next_number(fy)
                next_no_str = str(next_no).zfill(4)

                if branch_code:
                    self.return_no = f"{prefix}/{branch_code}/{fy}/{next_no_str}"
                else:
                    self.return_no = f"{prefix}/{fy}/{next_no_str}"

                super().save(*args, **kwargs)
            return

        super().save(*args, **kwargs)


class StockReturnItem(models.Model):
    """
    Items being returned
    """
    return_request = models.ForeignKey(StockReturn, on_delete=models.CASCADE, related_name='items')

    # Reference to original transfer item
    source_transfer_item = models.ForeignKey(
        StockTransferItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='return_items'
    )

    # Branch's variant (the one they received)
    branch_variant = models.ForeignKey(
        'pos.itemvariants',
        on_delete=models.PROTECT,
        related_name='returned_items_from_branch'
    )

    # Company's variant (the original source)
    company_variant = models.ForeignKey(
        'pos.itemvariants',
        on_delete=models.PROTECT,
        related_name='returned_items_to_company'
    )

    # Snapshot fields
    item_name = models.CharField(max_length=255)
    variant_info = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    hsnCode = models.CharField(max_length=50, blank=True, null=True)
    taxSlab = models.CharField(max_length=20, blank=True, null=True)
    tax_percent  = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)


    # Quantity and rate
    quantity = models.IntegerField(default=0)
    rate = models.FloatField(default=0)  # Branch price at which it was received

    # Tracking
    is_packaging_ready = models.BooleanField(default=False)
    is_returned_to_company = models.BooleanField(default=False)  # Stock increased in company

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.return_request.return_no} | {self.item_name} × {self.quantity}"
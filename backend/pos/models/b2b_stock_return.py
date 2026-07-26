# pos/models/b2b_stock_return.py
"""
✅ COMPLETELY SEPARATE MODULE — B2B Stock Return

Existing pos/models/stock_return.py (StockReturn / StockReturnItem) ko
BILKUL HAATH NAHI LAGAYA GAYA — wo purana flow (jahan branch seedha
superadmin ke Stock Transfer se aayi item ko return karti hai) waisa hi,
bina kisi change ke, chalta rahega.

Yeh naya module sirf un items ke liye hai jo kisi branch ko B2B Stock
Transfer (branch → branch) se mili thi — chahe woh item beech mein
kitni bhi branches se hoke guzri ho, aakhir mein wo hamesha SUPERADMIN
(company) branch se hi originate hui thi. Is module se wo item wapas
superadmin ko return hoti hai, poore transfer-chain ki visibility ke saath
(pos/utils/transfer_chain.py use hota hai — wo bhi ek independent utility
hai, kisi model ko modify nahi karta).
"""

from django.db import models, transaction
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.b2b_transfer import B2BStockTransfer, B2BStockTransferItem
from datetime import datetime

User = get_user_model()


def get_financial_year(now=None):
    """April-March financial year string, e.g. "26-27" """
    now = now or datetime.now()
    year = now.year
    if now.month >= 4:
        fy_start, fy_end = year, year + 1
    else:
        fy_start, fy_end = year - 1, year
    return f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"


class B2BReturnSequence(models.Model):
    """
    Har financial year ke liye ek global, atomic running counter —
    existing ReturnSequence (stock_return.py) jaisa hi pattern, lekin
    poori tarah alag table taaki dono return-types ke numbers kabhi
    mix na ho.
    """
    financial_year = models.CharField(max_length=10, unique=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "B2B Return Sequence"
        verbose_name_plural = "B2B Return Sequences"

    def __str__(self):
        return f"FY {self.financial_year} → last used: {self.last_number}"

    @classmethod
    def get_next_number(cls, financial_year: str) -> int:
        seq, _ = cls.objects.select_for_update().get_or_create(
            financial_year=financial_year,
            defaults={'last_number': 0},
        )
        seq.last_number += 1
        seq.save(update_fields=['last_number'])
        return seq.last_number


class B2BStockReturn(models.Model):
    """
    B2B-origin item ka return — koi bhi branch, jisne kisi B2B (branch to
    branch) transfer se item receive ki thi, use superadmin (company)
    branch ko wapas return kar rahi hai.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),                  # Branch ne return request bheji
        ('packaging_ready', 'Packaging Ready'),  # Branch ne packaging complete kar li
        ('approved', 'Approved'),                # Superadmin ne approve kar diya
        ('received', 'Received'),                # Superadmin ne received kar liya
        ('rejected', 'Rejected'),                # Superadmin ne reject kar diya
        ('cancelled', 'Cancelled'),              # Branch ne cancel kar diya
    ]

    return_no = models.CharField(max_length=50, unique=True)  # e.g. RTN/B2B/UGF/26-27/0001
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_stock_returns_sent')
    to_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_stock_returns_received')

    # ✅ Immediate B2B transfer jisse is branch ko item mili thi. Yeh sirf
    # ek "hint" hai — poora multi-hop chain (superadmin tak) barcode se
    # transfer_chain.py dynamically banata hai, kisi extra storage ki
    # zaroorat nahi.
    source_b2b_transfer = models.ForeignKey(
        B2BStockTransfer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_returns'
    )

    return_date = models.DateField()
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_b2b_returns')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_b2b_returns')
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_b2b_returns')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "B2B Stock Return"
        verbose_name_plural = "B2B Stock Returns"

    def __str__(self):
        return f"{self.return_no} | {self.branch} → {self.to_branch} | {self.status}"

    def save(self, *args, **kwargs):
        if not self.return_no:
            from pos.models.settings import setting
            settings_obj = setting.objects.filter(branch=self.branch).first()
            prefix = getattr(settings_obj, 'SR', 'RTN') if settings_obj else 'RTN'

            fy = get_financial_year()

            branch_code = ""
            if self.branch_id and self.branch and self.branch.branch_code:
                branch_code = self.branch.branch_code.strip().upper()

            # ✅ Ek hi global, atomic counter per FY — sab branches ke liye
            #    shared, existing StockReturn jaisa hi pattern, lekin
            #    poori tarah alag sequence table.
            with transaction.atomic():
                next_no = B2BReturnSequence.get_next_number(fy)
                next_no_str = str(next_no).zfill(4)

                if branch_code:
                    self.return_no = f"{prefix}/B2B/{branch_code}/{fy}/{next_no_str}"
                else:
                    self.return_no = f"{prefix}/B2B/{fy}/{next_no_str}"

                super().save(*args, **kwargs)
            return

        super().save(*args, **kwargs)


class B2BStockReturnItem(models.Model):
    """
    Items being returned — ORIGIN hamesha ek B2BStockTransferItem hota hai
    (kabhi StockTransferItem nahi — wo purane StockReturn module ka scope hai).
    """
    return_request = models.ForeignKey(B2BStockReturn, on_delete=models.CASCADE, related_name='items')

    # Immediate B2B transfer item jisse yeh return item bana
    source_b2b_transfer_item = models.ForeignKey(
        B2BStockTransferItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='return_items'
    )

    # Branch ka apna variant (jo usne receive kiya tha)
    branch_variant = models.ForeignKey(
        'pos.itemvariants',
        on_delete=models.PROTECT,
        related_name='b2b_returned_items_from_branch'
    )

    # Superadmin (company) branch ka original variant — barcode se resolve hota hai
    company_variant = models.ForeignKey(
        'pos.itemvariants',
        on_delete=models.PROTECT,
        related_name='b2b_returned_items_to_company'
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

    quantity = models.IntegerField(default=0)
    rate = models.FloatField(default=0)  # Branch price jis par receive hui thi

    is_packaging_ready = models.BooleanField(default=False)
    is_returned_to_company = models.BooleanField(default=False)  # Stock company mein increase hua

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.return_request.return_no} | {self.item_name} × {self.quantity}"
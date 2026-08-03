# pos/models/stock_transfer.py
# SIMPLIFIED - No mapping, direct transfer

from django.db import models
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from datetime import datetime
from pos.models.branch_order import BranchOrder

User = get_user_model()


class StockTransfer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # ✅ ADD THIS - Transfer type to distinguish manual vs order
    TRANSFER_TYPE_CHOICES = [
        ('manual', 'Manual Transfer'),
        ('order', 'Order Transfer'),
    ]

    transfer_no   = models.CharField(max_length=50, unique=True)
    from_branch   = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='transfers_sent')
    to_branch     = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='transfers_received')
    transfer_date = models.DateField()
    note          = models.TextField(blank=True, null=True)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    
    #  ADD THESE FIELDS
    transfer_type = models.CharField(max_length=10, choices=TRANSFER_TYPE_CHOICES, default='manual')
    
    #  Use string reference instead of direct import to avoid circular dependency
    source_order = models.ForeignKey(
        'pos.BranchOrder',  # ← String reference, not direct import
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_transfers'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transfer_no} | {self.from_branch} → {self.to_branch} | {self.transfer_type}"

    def save(self, *args, **kwargs):
        if not self.transfer_no:
            from pos.models.settings import setting
            settings_obj = setting.objects.filter(branch=self.from_branch).first()
            prefix = getattr(settings_obj, 'ST', 'ST') if settings_obj else 'ST'
            
            now = datetime.now()
            year = now.year
            if now.month >= 4:
                fy_start = year
                fy_end = year + 1
            else:
                fy_start = year - 1
                fy_end = year
            fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
            
            pattern = f"{prefix}/{fy}/"
            last_transfer = StockTransfer.objects.filter(
                transfer_no__startswith=pattern
            ).order_by('-id').first()
            
            last_no = 0
            if last_transfer and last_transfer.transfer_no:
                try:
                    parts = last_transfer.transfer_no.split('/')
                    if len(parts) >= 3:
                        last_no = int(parts[-1])
                except (ValueError, IndexError):
                    last_no = 0
            
            next_no = str(last_no + 1).zfill(4)
            self.transfer_no = f"{prefix}/{fy}/{next_no}"
        super().save(*args, **kwargs)


class StockTransferItem(models.Model):
    """
    Simplified Stock Transfer Item - NO MAPPING
    Direct transfer from source variant to destination branch
    """
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')

    # ── SOURCE (Super Admin branch) ──────────────────────────
    from_item    = models.ForeignKey(
        'pos.items',
        on_delete=models.PROTECT,
        related_name='transfer_outgoing_items',
    )
    from_variant = models.ForeignKey(
        'pos.itemvariants',
        on_delete=models.PROTECT,
        related_name='transfer_outgoing',
    )
    
    # Snapshot fields
    from_item_name    = models.CharField(max_length=255)
    from_variant_info = models.CharField(max_length=100, blank=True, null=True)
    from_barcode      = models.CharField(max_length=100, blank=True, null=True)

    # ── Transfer details ──────────────────────────────────────
    quantity = models.IntegerField(default=0)
    rate     = models.FloatField(default=0)

    # stock_transfer.py model mein yeh field add karo
    to_variant = models.ForeignKey(
        'pos.itemvariants',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transfer_incoming',
    )
    
    # ✅ Stock verification flag
    is_stock_updated = models.BooleanField(default=False)
    
    # ✅ NEW — GST breakup (branch_price par, toggle ke hisaab se inclusive/exclusive)
    tax_percent  = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0,  blank=True, null=True,)
    tax_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0,  blank=True, null=True,)
    cgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True,)
    sgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True,)
    igst         = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True,)
    net_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0,blank=True, null=True,)

    website_display_on_verify = models.BooleanField(default=False)
    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.transfer.transfer_no} | {self.from_item_name} × {self.quantity}"
    
    
    
class VariantBranchMapping(models.Model):
    """
    Permanent link: ek source (superadmin) variant, ek destination branch me
    kis variant se corresponds karta hai — barcode se independent.
    Isse superadmin barcode/price/fields edit kare toh bhi agli transfer
    SAME destination variant ko update karegi, naya duplicate nahi banega.
    """
    source_variant = models.ForeignKey(
        'pos.itemvariants', on_delete=models.CASCADE, related_name='branch_mappings'
    )
    to_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='variant_mappings')
    dest_variant = models.ForeignKey(
        'pos.itemvariants', on_delete=models.CASCADE, related_name='source_mapping'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('source_variant', 'to_branch')

    def __str__(self):
        return f"src {self.source_variant_id} -> branch {self.to_branch_id} -> dest {self.dest_variant_id}"    
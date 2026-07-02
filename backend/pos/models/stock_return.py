from django.db import models
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.models.items import items, itemvariants
from datetime import datetime

User = get_user_model()


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

    return_no = models.CharField(max_length=50, unique=True)
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
            prefix = getattr(settings_obj, 'SR', 'SR') if settings_obj else 'SR'
            
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
            last_return = StockReturn.objects.filter(
                return_no__startswith=pattern
            ).order_by('-id').first()
            
            last_no = 0
            if last_return and last_return.return_no:
                try:
                    parts = last_return.return_no.split('/')
                    if len(parts) >= 3:
                        last_no = int(parts[-1])
                except (ValueError, IndexError):
                    last_no = 0
            
            next_no = str(last_no + 1).zfill(4)
            self.return_no = f"{prefix}/{fy}/{next_no}"
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
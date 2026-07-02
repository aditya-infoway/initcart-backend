# pos/models/branch_order.py
# NEW FILE — Branch Order Tracking Module

from django.db import models
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants

User = get_user_model()


class BranchOrder(models.Model):
    """
    Normal branch dwara superadmin ke company items ka order request.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),          # branch ne order diya, superadmin ne process nahi kiya
        ('processing', 'Processing'),    # superadmin ne items adjust karke bheja
        ('partially_sent', 'Partially Sent'),  # kuch items bheji, kuch nahi
        ('sent', 'Sent'),               # superadmin ne sab items bheji (stock transfer complete)
        ('cancelled', 'Cancelled'),
    ]

    order_id = models.CharField(max_length=50, unique=True)  # e.g. ORD/25-26/0001
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name='branch_orders'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_orders'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note = models.TextField(blank=True, null=True)
    order_date = models.DateField(auto_now_add=True)

    # Linked stock transfer (jab superadmin ne order process karke bheja)
    linked_transfer = models.ForeignKey(
        'pos.StockTransfer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='linked_orders'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_id} | {self.branch.branch_name} | {self.status}"

    def save(self, *args, **kwargs):
        if not self.order_id:
            from datetime import datetime
            now = datetime.now()
            year = now.year
            if now.month >= 4:
                fy_start, fy_end = year, year + 1
            else:
                fy_start, fy_end = year - 1, year
            fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"

            # Branch's own code — only affects DISPLAY format, never the counter
            branch_code = ""
            if self.branch_id and self.branch and self.branch.branch_code:
                branch_code = self.branch.branch_code.strip().upper()

            # ✅ ONE global counter per FY, shared across ALL branches,
            #    regardless of whether branch_code is set or blank
            fy_marker = f"/{fy}/"
            last = BranchOrder.objects.filter(
                order_id__contains=fy_marker
            ).order_by('-id').first()

            last_no = 0
            if last and last.order_id:
                try:
                    last_no = int(last.order_id.split('/')[-1])
                except (ValueError, IndexError):
                    last_no = 0

            next_no = str(last_no + 1).zfill(4)

            if branch_code:
                self.order_id = f"ORD/{branch_code}/{fy}/{next_no}"
            else:
                self.order_id = f"ORD/{fy}/{next_no}"

        super().save(*args, **kwargs)

class BranchOrderItem(models.Model):
    """
    Order ki ek item — superadmin ke company item + variant ka reference.
    Global code se future orders mein same item identify hogi.
    """
    order = models.ForeignKey(
        BranchOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )

    # Source item — superadmin ke branch ka company item
    source_item = models.ForeignKey(
        Items,
        on_delete=models.PROTECT,
        related_name='order_references'
    )
    source_variant = models.ForeignKey(
        ItemVariants,
        on_delete=models.PROTECT,
        related_name='order_references'
    )

    # Snapshot fields (item delete hone par bhi data rahe)
    item_name = models.CharField(max_length=255)
    variant_info = models.CharField(max_length=100, blank=True, null=True)  # "Red / XL"
    barcode = models.CharField(max_length=100, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    hsnCode = models.CharField(max_length=50, blank=True, null=True)
    taxSlab = models.CharField(max_length=20, blank=True, null=True)

    # Global Item Code — yeh same variant ka consistent identifier hai
    # Barcode se generate hota hai; barcode same hoga toh same item match hogi
    global_item_code = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Branch ne kitna manga
    requested_quantity = models.IntegerField(default=0)
    # Superadmin ne kitna approve kiya / bheja (adjust kar sakta hai)
    approved_quantity = models.IntegerField(default=0, null=True, blank=True)

    # Superadmin ne is item ko order se hataya
    is_removed_by_admin = models.BooleanField(default=False)
    admin_note = models.CharField(max_length=255, blank=True, null=True)
    
    branch_price = models.FloatField(default=0) 
    rate = models.FloatField(default=0) 

    # Kya yeh item stock transfer mein chali gayi
    is_transferred = models.BooleanField(default=False)

    # Rate
    rate = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.order.order_id} | {self.item_name} x {self.requested_quantity}"

    def save(self, *args, **kwargs):
        # Global item code = barcode if available, else item_id-variant_id
        if not self.global_item_code:
            if self.barcode:
                self.global_item_code = f"GIC-{self.barcode}"
            else:
                self.global_item_code = f"GIC-{self.source_item_id}-{self.source_variant_id}"
              #  Auto-set branch_price from source variant if not set
        if not self.branch_price and self.source_variant:
            self.branch_price = self.source_variant.branchPrice or 0        
        super().save(*args, **kwargs)
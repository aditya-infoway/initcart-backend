# pos/models/b2b_transfer.py
# B2B Stock Transfer — Branch-to-Branch (superadmin involved nahi).
# Flow:
#   1) B (requesting) -> B2BOrder create (single round, no multi-round)
#   2) A (source) -> process order: live stock capped qty, B2BStockTransfer(status=pending) create
#   3) B -> confirm (status=confirmed)
#   4) A -> packaging ready (status=packaging_ready, A KA STOCK MINUS)
#   5) B -> receive (status=received, B KA STOCK PLUS)

from django.db import models, transaction
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants
from datetime import datetime

User = get_user_model()


def get_financial_year(now=None):
    now = now or datetime.now()
    year = now.year
    if now.month >= 4:
        fy_start, fy_end = year, year + 1
    else:
        fy_start, fy_end = year - 1, year
    return f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"


# ════════════════════════════════════════════════════════════
# B2B ORDER (requesting branch → source branch) — SINGLE ROUND
# ════════════════════════════════════════════════════════════

class B2BOrderSequence(models.Model):
    financial_year = models.CharField(max_length=10, unique=True)
    last_number = models.PositiveIntegerField(default=0)

    @classmethod
    def get_next_number(cls, financial_year: str) -> int:
        seq, _ = cls.objects.select_for_update().get_or_create(
            financial_year=financial_year, defaults={'last_number': 0},
        )
        seq.last_number += 1
        seq.save(update_fields=['last_number'])
        return seq.last_number


class B2BOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),      # B ne place kiya, A ne process nahi kiya
        ('sent', 'Sent'),            # A ne process kiya, kam se kam kuch items available the
        ('no_stock', 'No Stock'),    # A ne process kiya, koi bhi item available nahi tha
        ('cancelled', 'Cancelled'),  # process se pehle cancel
    ]

    order_id = models.CharField(max_length=50, unique=True)  # B2B/TRW/26-27/0001
    requesting_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_orders_placed')
    source_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_orders_received')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_b2b_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note = models.TextField(blank=True, null=True)
    order_date = models.DateField(auto_now_add=True)

    linked_transfer = models.ForeignKey(
        'pos.B2BStockTransfer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='linked_orders'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_id} | {self.requesting_branch.branch_name} ← {self.source_branch.branch_name}"

    def save(self, *args, **kwargs):
        if not self.order_id:
            fy = get_financial_year()
            req_code = ""
            if self.requesting_branch_id and self.requesting_branch and self.requesting_branch.branch_code:
                req_code = self.requesting_branch.branch_code.strip().upper()
            with transaction.atomic():
                next_no = B2BOrderSequence.get_next_number(fy)
                next_no_str = str(next_no).zfill(4)
                self.order_id = f"B2B/{req_code}/{fy}/{next_no_str}" if req_code else f"B2B/{fy}/{next_no_str}"
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


class B2BOrderItem(models.Model):
    order = models.ForeignKey(B2BOrder, on_delete=models.CASCADE, related_name='items')

    source_item = models.ForeignKey(Items, on_delete=models.PROTECT, related_name='b2b_order_references')
    source_variant = models.ForeignKey(ItemVariants, on_delete=models.PROTECT, related_name='b2b_order_references')

    item_name = models.CharField(max_length=255)
    variant_info = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    hsnCode = models.CharField(max_length=50, blank=True, null=True)
    taxSlab = models.CharField(max_length=20, blank=True, null=True)
    global_item_code = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    requested_quantity = models.IntegerField(default=0)

    # ✅ Process time par live stock se capped — kabhi requested se zyada nahi
    available_quantity = models.IntegerField(default=0)
    # ✅ Final bheji gayi qty — max available_quantity, source branch isse aur kam kar sakti hai
    approved_quantity = models.IntegerField(default=0)

    is_removed = models.BooleanField(default=False)  # available_quantity 0 hone par ya source ne hataya
    admin_note = models.CharField(max_length=255, blank=True, null=True)

    branch_price = models.FloatField(default=0)
    rate = models.FloatField(default=0)

    tax_percent  = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.order.order_id} | {self.item_name} x {self.requested_quantity}"

    def save(self, *args, **kwargs):
        if not self.global_item_code:
            self.global_item_code = f"GIC-{self.barcode}" if self.barcode else f"GIC-{self.source_item_id}-{self.source_variant_id}"
        if not self.branch_price and self.source_variant:
            self.branch_price = self.source_variant.branchPrice or 0
        super().save(*args, **kwargs)


# ════════════════════════════════════════════════════════════
# B2B STOCK TRANSFER (actual movement, confirm → packaging → receive)
# ════════════════════════════════════════════════════════════

class B2BTransferSequence(models.Model):
    financial_year = models.CharField(max_length=10, unique=True)
    last_number = models.PositiveIntegerField(default=0)

    @classmethod
    def get_next_number(cls, financial_year: str) -> int:
        seq, _ = cls.objects.select_for_update().get_or_create(
            financial_year=financial_year, defaults={'last_number': 0},
        )
        seq.last_number += 1
        seq.save(update_fields=['last_number'])
        return seq.last_number


class B2BStockTransfer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),                     # A ne banaya, B ka confirm baaki
        ('confirmed', 'Confirmed'),                 # B ne confirm kiya, A packaging start kar sakti hai
        ('packaging_start', 'Packaging Started'),    # A ne packaging start ki — STOCK ABHI MINUS NAHI HUA
        ('packaging_ready', 'Packaging Ready'),      # A ne pack complete kiya — A KA STOCK MINUS HO CHUKA
        ('partially_received', 'Partially Received'),
        ('received', 'Received'),                    # B ne receive kiya — B KA STOCK PLUS HO CHUKA
        ('cancelled', 'Cancelled'),
    ]

    transfer_no = models.CharField(max_length=50, unique=True)
    from_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_transfers_sent')
    to_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_transfers_received')

    transfer_date = models.DateField()
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    source_order = models.ForeignKey(B2BOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transfers')

    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='b2b_confirmed_transfers')
    packaging_started_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='b2b_packaging_started_transfers')
    packaged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='b2b_packaged_transfers')
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='b2b_received_transfers')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transfer_no} | {self.from_branch} → {self.to_branch} | {self.status}"

    def save(self, *args, **kwargs):
        if not self.transfer_no:
            fy = get_financial_year()
            with transaction.atomic():
                next_no = B2BTransferSequence.get_next_number(fy)
                self.transfer_no = f"B2BST/{fy}/{str(next_no).zfill(4)}"
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


class B2BStockTransferItem(models.Model):
    transfer = models.ForeignKey(B2BStockTransfer, on_delete=models.CASCADE, related_name='items')

    from_item = models.ForeignKey(Items, on_delete=models.PROTECT, related_name='b2b_transfer_outgoing_items')
    from_variant = models.ForeignKey(ItemVariants, on_delete=models.PROTECT, related_name='b2b_transfer_outgoing')

    from_item_name = models.CharField(max_length=255)
    from_variant_info = models.CharField(max_length=100, blank=True, null=True)
    from_barcode = models.CharField(max_length=100, blank=True, null=True)

    quantity = models.IntegerField(default=0)
    rate = models.FloatField(default=0)

    to_variant = models.ForeignKey(ItemVariants, on_delete=models.SET_NULL, null=True, blank=True, related_name='b2b_transfer_incoming')

    is_packaged = models.BooleanField(default=False)   # A ne stock minus kiya
    is_received = models.BooleanField(default=False)   # B ne stock plus kiya

    tax_percent  = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.transfer.transfer_no} | {self.from_item_name} × {self.quantity}"
    
    
    
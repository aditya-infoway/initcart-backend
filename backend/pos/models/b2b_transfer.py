# pos/models/b2b_transfer.py
# NEW FILE — B2B Stock Transfer Module (normal branch ↔ normal branch)
# Completely separate tables from StockTransfer/BranchOrder (jo superadmin<->branch ke liye hain).
#
# FLOW:
#   1. Requesting branch (from_branch) B2BOrder banati hai, ek source branch (to_branch) select karke.
#      Sirf woh items order kiye ja sakte hain jo to_branch ke paas created_by_superadmin=True hain
#      (yaani jo originally superadmin ke Stock Transfer se aaye the).
#   2. Source branch (to_branch) order ko process/approve karti hai (superadmin AdminProcessOrderSerializer
#      jaisa hi) -> B2BStockTransfer + B2BStockTransferItem create hote hain.
#   3. Requesting branch (to_branch of the B2BStockTransfer) apne B2B Stock Verify page se verify karti hai
#      -> stock source branch se minus, requesting branch me plus.

from django.db import models, transaction
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.branch_order import get_financial_year

User = get_user_model()


class B2BOrderSequence(models.Model):
    """Global atomic counter per FY for B2B Order numbers — OrderSequence/ReturnSequence jaisa pattern."""
    financial_year = models.CharField(max_length=10, unique=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "B2B Order Sequence"
        verbose_name_plural = "B2B Order Sequences"

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


class B2BTransferSequence(models.Model):
    """Global atomic counter per FY for B2B Transfer numbers."""
    financial_year = models.CharField(max_length=10, unique=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "B2B Transfer Sequence"
        verbose_name_plural = "B2B Transfer Sequences"

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


class B2BOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('partially_sent', 'Partially Sent'),
        ('sent', 'Sent'),
        ('cancelled', 'Cancelled'),
    ]

    order_id = models.CharField(max_length=50, unique=True)  # e.g. B2B/BRC/26-27/0001

    # Branch jo order kar rahi hai (maal receive karegi)
    from_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_orders_placed')
    # Branch jisse maal manga gaya hai (maal bhejegi / source)
    to_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_orders_received')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='b2b_orders_created')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note = models.TextField(blank=True, null=True)
    order_date = models.DateField(auto_now_add=True)

    linked_transfer = models.ForeignKey(
        'pos.B2BStockTransfer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='linked_orders'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_id} | {self.from_branch.branch_name} → {self.to_branch.branch_name} | {self.status}"

    def save(self, *args, **kwargs):
        if not self.order_id:
            fy = get_financial_year()
            branch_code = ""
            if self.from_branch_id and self.from_branch and self.from_branch.branch_code:
                branch_code = self.from_branch.branch_code.strip().upper()

            with transaction.atomic():
                next_no = B2BOrderSequence.get_next_number(fy)
                next_no_str = str(next_no).zfill(4)
                if branch_code:
                    self.order_id = f"B2B/{branch_code}/{fy}/{next_no_str}"
                else:
                    self.order_id = f"B2B/{fy}/{next_no_str}"
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


class B2BOrderItem(models.Model):
    order = models.ForeignKey(B2BOrder, on_delete=models.CASCADE, related_name='items')

    source_item = models.ForeignKey('pos.items', on_delete=models.PROTECT, related_name='b2b_order_references')
    source_variant = models.ForeignKey('pos.itemvariants', on_delete=models.PROTECT, related_name='b2b_order_references')

    item_name = models.CharField(max_length=255)
    variant_info = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    hsnCode = models.CharField(max_length=50, blank=True, null=True)
    taxSlab = models.CharField(max_length=20, blank=True, null=True)

    global_item_code = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    requested_quantity = models.IntegerField(default=0)
    approved_quantity = models.IntegerField(default=0, null=True, blank=True)
    # ✅ Cumulative — ab tak total kitni qty dispatch ho chuki hai (multi-round support, BranchOrder jaisa)
    sent_quantity = models.IntegerField(default=0)

    is_removed_by_source = models.BooleanField(default=False)
    source_note = models.CharField(max_length=255, blank=True, null=True)

    branch_price = models.FloatField(default=0)
    rate = models.FloatField(default=0)

    tax_percent = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    is_transferred = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.order.order_id} | {self.item_name} x {self.requested_quantity}"

    @property
    def remaining_quantity(self):
        if self.is_removed_by_source:
            return 0
        return max(0, self.requested_quantity - (self.sent_quantity or 0))

    @property
    def is_fully_sent(self):
        return (self.sent_quantity or 0) >= self.requested_quantity

    def save(self, *args, **kwargs):
        if not self.global_item_code:
            if self.barcode:
                self.global_item_code = f"GIC-{self.barcode}"
            else:
                self.global_item_code = f"GIC-{self.source_item_id}-{self.source_variant_id}"
        if not self.branch_price and self.source_variant:
            self.branch_price = self.source_variant.branchPrice or 0
        super().save(*args, **kwargs)


class B2BStockTransfer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    transfer_no = models.CharField(max_length=50, unique=True)  # e.g. B2BTR/26-27/0001
    from_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_transfers_sent')
    to_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_transfers_received')
    transfer_date = models.DateField()
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    source_order = models.ForeignKey(
        B2BOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transfers'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transfer_no} | {self.from_branch} → {self.to_branch}"

    def save(self, *args, **kwargs):
        if not self.transfer_no:
            fy = get_financial_year()
            with transaction.atomic():
                next_no = B2BTransferSequence.get_next_number(fy)
                next_no_str = str(next_no).zfill(4)
                self.transfer_no = f"B2BTR/{fy}/{next_no_str}"
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


class B2BStockTransferItem(models.Model):
    transfer = models.ForeignKey(B2BStockTransfer, on_delete=models.CASCADE, related_name='items')

    from_item = models.ForeignKey('pos.items', on_delete=models.PROTECT, related_name='b2b_transfer_outgoing_items')
    from_variant = models.ForeignKey('pos.itemvariants', on_delete=models.PROTECT, related_name='b2b_transfer_outgoing')

    from_item_name = models.CharField(max_length=255)
    from_variant_info = models.CharField(max_length=100, blank=True, null=True)
    from_barcode = models.CharField(max_length=100, blank=True, null=True)

    quantity = models.IntegerField(default=0)
    rate = models.FloatField(default=0)

    to_variant = models.ForeignKey(
        'pos.itemvariants', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='b2b_transfer_incoming',
    )

    is_stock_updated = models.BooleanField(default=False)

    tax_percent = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.transfer.transfer_no} | {self.from_item_name} × {self.quantity}"
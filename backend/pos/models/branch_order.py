# pos/models/branch_order.py
# UPDATED FILE — Branch Order Tracking Module
# Order-number logic ab ek dedicated OrderSequence counter se atomically generate hota hai,
# taaki chahe kitni bhi branches ek saath order karein, serial number kabhi duplicate/clash na ho
# aur sequence hamesha global chale (branch_code set ho ya na ho).

from django.db import models, transaction
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants

User = get_user_model()


def get_financial_year(now=None):
    """
    April-March financial year string banata hai, e.g. "26-27"
    """
    from datetime import datetime
    now = now or datetime.now()
    year = now.year
    if now.month >= 4:
        fy_start, fy_end = year, year + 1
    else:
        fy_start, fy_end = year - 1, year
    return f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"


class OrderSequence(models.Model):
    """
    Har financial year ke liye ek hi row — global running counter.
    Order number generate karte waqt is row ko `select_for_update()`
    se DB-level lock karke atomically increment karte hain.
    Isse concurrent requests (do branches ek hi second mein order karein)
    mein bhi kabhi duplicate ya skipped number nahi banega.
    """
    financial_year = models.CharField(max_length=10, unique=True)  # e.g. "26-27"
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Order Sequence"
        verbose_name_plural = "Order Sequences"

    def __str__(self):
        return f"FY {self.financial_year} → last used: {self.last_number}"

    @classmethod
    def get_next_number(cls, financial_year: str) -> int:
        """
        Atomically FY ka agla number nikaalta hai aur turant save karta hai.
        Yeh method hamesha ek transaction.atomic() block ke andar call hona chahiye
        (BranchOrder.save() mein already wrapped hai).
        """
        seq, _ = cls.objects.select_for_update().get_or_create(
            financial_year=financial_year,
            defaults={'last_number': 0},
        )
        seq.last_number += 1
        seq.save(update_fields=['last_number'])
        return seq.last_number


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

    order_id = models.CharField(max_length=50, unique=True)  # e.g. ORD/TRW/26-27/0001
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
            fy = get_financial_year()

            # Branch's own code — sirf DISPLAY format ko affect karta hai, counter ko nahi
            branch_code = ""
            if self.branch_id and self.branch and self.branch.branch_code:
                branch_code = self.branch.branch_code.strip().upper()

            # ✅ Ek hi global, atomic counter per FY — sab branches ke liye shared,
            #    chahe branch_code set ho ya blank ho. select_for_update() ki wajah se
            #    concurrent requests bhi safe hain (koi duplicate/skip nahi hoga).
            with transaction.atomic():
                next_no = OrderSequence.get_next_number(fy)
                next_no_str = str(next_no).zfill(4)

                if branch_code:
                    self.order_id = f"ORD/{branch_code}/{fy}/{next_no_str}"
                else:
                    self.order_id = f"ORD/{fy}/{next_no_str}"

                super().save(*args, **kwargs)
            return

        super().save(*args, **kwargs)


class BranchOrderItem(models.Model):
    """
    Order ki ek item — superadmin ke company item + variant ka reference.
    """
    order = models.ForeignKey(
        BranchOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )

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

    item_name = models.CharField(max_length=255)
    variant_info = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    hsnCode = models.CharField(max_length=50, blank=True, null=True)
    taxSlab = models.CharField(max_length=20, blank=True, null=True)

    global_item_code = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    requested_quantity = models.IntegerField(default=0)

    # Ab yeh field sirf "is round mein kitna approve/send kiya" store karta hai
    approved_quantity = models.IntegerField(default=0, null=True, blank=True)

    # ✅ NEW FIELD — cumulative: ab tak total kitni qty dispatch ho chuki hai (sab rounds milakar)
    sent_quantity = models.IntegerField(default=0)

    is_removed_by_admin = models.BooleanField(default=False)
    admin_note = models.CharField(max_length=255, blank=True, null=True)

    branch_price = models.FloatField(default=0)
    rate = models.FloatField(default=0)
    # ✅ NEW — GST breakup (branch_price par, toggle-based, requested_quantity ke hisaab se)
    tax_percent  = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Ab sirf True hoga jab FULL requested_quantity dispatch ho chuki ho
    is_transferred = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.order.order_id} | {self.item_name} x {self.requested_quantity}"

    @property
    def remaining_quantity(self):
        """Is item ki kitni quantity abhi bhi bhejni baaki hai. Removed item ke liye 0."""
        if self.is_removed_by_admin:
            return 0
        remaining = self.requested_quantity - (self.sent_quantity or 0)
        return max(0, remaining)

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
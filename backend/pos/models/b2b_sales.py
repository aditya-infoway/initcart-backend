from django.db import models
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from datetime import datetime

User = get_user_model()


class B2BSale(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    sale_no      = models.CharField(max_length=50, unique=True)
    from_branch  = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_sales_sent')
    to_branch    = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='b2b_sales_received')
    sale_date    = models.DateField()
    note         = models.TextField(blank=True, null=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sale_no} | {self.from_branch} → {self.to_branch}"

    # ✅ NEW — reusable, dono save() aur preview API isi ko call karenge
    @classmethod
    def get_next_sale_no(cls):
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start, fy_end = year, year + 1
        else:
            fy_start, fy_end = year - 1, year
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        prefix = "B2BS"
        pattern = f"{prefix}/{fy}/"

        last = cls.objects.filter(sale_no__startswith=pattern).order_by('-id').first()
        last_no = 0
        if last and last.sale_no:
            try:
                parts = last.sale_no.split('/')
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = str(last_no + 1).zfill(4)
        return f"{prefix}/{fy}/{next_no}"

    def save(self, *args, **kwargs):
        if not self.sale_no:
            self.sale_no = self.__class__.get_next_sale_no()   # ✅ same logic, ab classmethod se
        super().save(*args, **kwargs)


class B2BSaleItem(models.Model):
    sale = models.ForeignKey(B2BSale, on_delete=models.CASCADE, related_name='items')

    # ── SOURCE (Super Admin branch) ──────────────────────────
    from_item    = models.ForeignKey('pos.items', on_delete=models.PROTECT, related_name='b2bsale_outgoing_items')
    from_variant = models.ForeignKey('pos.itemvariants', on_delete=models.PROTECT, related_name='b2bsale_outgoing')

    from_item_name    = models.CharField(max_length=255)
    from_variant_info = models.CharField(max_length=100, blank=True, null=True)
    from_barcode      = models.CharField(max_length=100, blank=True, null=True)

    quantity = models.IntegerField(default=0)
    rate     = models.FloatField(default=0)

    # ── DESTINATION (Franchise branch) — verify ke baad set hota hai ──
    to_variant = models.ForeignKey(
        'pos.itemvariants', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='b2bsale_incoming'
    )

    is_stock_updated = models.BooleanField(default=False)

    tax_percent  = models.CharField(max_length=20, blank=True, null=True, default="0")
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)
    tax_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)
    cgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    sgst         = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    igst         = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    net_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, null=True)

    website_display_on_verify = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.sale.sale_no} | {self.from_item_name} × {self.quantity}"
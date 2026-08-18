from django.db import models, transaction
from pos.models.branch import Branch
from pos.models.items import items, itemvariants
from pos.models.account import Account
from django.core.validators import MinValueValidator
from decimal import Decimal
from pos.models.salesentry import SalesItem, SalesMaster
from pos.models.mixins import CreatedByMixin


class SalesReturnMaster(CreatedByMixin, models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    return_no = models.CharField(max_length=50)
    date = models.DateField()
    dueDate = models.DateField(null=True, blank=True)
    original_bill_no = models.CharField(max_length=50)
    customer = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        limit_choices_to={'group': 'Customer'}
    )
    reason_for_return = models.CharField(max_length=200)
    approved_by = models.CharField(max_length=100)
    return_type = models.CharField(max_length=50, choices=[
        ('Full', 'Full Return'),
        ('Partial', 'Partial Return')
    ])
    return_status = models.CharField(max_length=20, default='Pending', choices=[
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Completed', 'Completed')
    ])
    payment_terms = models.CharField(max_length=50, blank=True, null=True)
    bank_account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales_return_bank",
        limit_choices_to={'group': 'Bank Account'}
    )
    cash_account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales_return_cash",
        limit_choices_to={'group': 'Case In Hand'}
    )
    total_basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    narration = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.return_no} - {self.customer.account_name}"

    def save(self, *args, **kwargs):
        from datetime import datetime
        from pos.models.settings import setting

        # ── Sirf voucher number generate karo, KOI BALANCE UPDATE NAHI ──
        if not self.return_no:
            settings_obj = setting.objects.filter(branch=self.branch).first()
            prefix = getattr(settings_obj, "SR", "SR") if settings_obj else "SR"

            now = datetime.now()
            year = now.year
            fy_start = year if now.month >= 4 else year - 1
            fy_end = fy_start + 1
            fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"

            last_return = SalesReturnMaster.objects.filter(
                branch=self.branch,
                return_no__startswith=f"{prefix}/{fy}/"
            ).order_by("-id").first()

            last_no = 0
            if last_return and last_return.return_no:
                try:
                    last_no = int(last_return.return_no.split("/")[-1])
                except Exception:
                    last_no = 0

            self.return_no = f"{prefix}/{fy}/{str(last_no + 1).zfill(4)}"

        super().save(*args, **kwargs)
        # ❌ BALANCE UPDATE YAHAN NAHI — VIEW MEIN HOGA (double call se bachne ke liye)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'return_no'],
                name='unique_sr_per_branch'
            )
        ]


class SalesReturnItem(models.Model):
    sales_return = models.ForeignKey(
        SalesReturnMaster, related_name="items", on_delete=models.CASCADE
    )
    sales_item = models.ForeignKey(
        SalesItem, on_delete=models.CASCADE,
        null=True, blank=True, related_name='returns'
    )
    item = models.ForeignKey(items, on_delete=models.CASCADE)
    variant = models.ForeignKey(
        itemvariants, on_delete=models.CASCADE, null=True, blank=True
    )
    hsn_code = models.CharField(max_length=20)
    batch_no = models.CharField(max_length=50, blank=True)
    return_quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    basic_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.item.itemName} - {self.return_quantity}"
    
    def save(self, *args, **kwargs):
        """
        GST Toggle:
        - ON:  Price is BASIC (exclusive) → net = basic + tax
        - OFF: Price is NET (inclusive)   → tax = net * rate/100, basic = net - tax
        """
        from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
        from pos.models.settings import setting

        def safe_decimal(val, default=Decimal("0.00")):
            try:
                if val is None:
                    return default
                val = str(val).replace("%", "").strip()
                if val == "":
                    return default
                return Decimal(val)
            except (InvalidOperation, ValueError):
                return default

        settings_obj = setting.objects.filter(branch=self.sales_return.branch).first()
        sales_gst_toggle = getattr(settings_obj, 'sales_gst_toggle', True)

        price            = safe_decimal(self.price)
        qty              = safe_decimal(self.return_quantity)
        discount_percent = safe_decimal(self.discount_percent)

        total_price = (price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        discount_amount       = (total_price * discount_percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        amount_after_discount = (total_price - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        tax_rate = safe_decimal(self.tax_percent)

        if tax_rate > 0:
            if sales_gst_toggle:
                # ON: exclusive
                total_tax    = (amount_after_discount * tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                basic_amount = amount_after_discount
                net_amount   = (basic_amount + total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                # OFF: inclusive
                total_tax    = (amount_after_discount * tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                basic_amount = (amount_after_discount - total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                net_amount   = amount_after_discount
        else:
            total_tax    = Decimal("0.00")
            basic_amount = amount_after_discount
            net_amount   = amount_after_discount

        if self.sales_return.branch.state == self.sales_return.customer.state:
            half_tax  = (total_tax / 2).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.cgst = half_tax
            self.sgst = half_tax
            self.igst = Decimal("0.00")
            if self.cgst + self.sgst != total_tax:
                if total_tax - (self.cgst + self.sgst) > 0:
                    self.cgst += (total_tax - (self.cgst + self.sgst))
        else:
            self.cgst = Decimal("0.00")
            self.sgst = Decimal("0.00")
            self.igst = total_tax

        self.basic_amount    = basic_amount
        self.discount_amount = discount_amount
        self.tax_amount      = total_tax
        self.net_amount      = net_amount

        super().save(*args, **kwargs)
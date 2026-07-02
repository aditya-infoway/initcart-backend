
#pos/models/purchasereturn.py
from django.db import models
from pos.models.branch import Branch
from pos.models.items import items, itemvariants
from pos.models.account import Account
from pos.models.purchaseentry import PurchaseItem
from django.core.validators import MinValueValidator
from decimal import Decimal

class PurchaseReturnMaster(models.Model):
    """Main Purchase Return record"""
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='purchase_returns')
    return_no = models.CharField(max_length=50)
    date = models.DateField()
    original_bill_no = models.CharField(max_length=50)
    party = models.ForeignKey(Account, on_delete=models.PROTECT, limit_choices_to={'group': 'Supplier'}, related_name='purchase_returns')
    reason_for_return = models.CharField(max_length=200)
    approved_by = models.CharField(max_length=100)
    return_type = models.CharField(max_length=20, choices=[
        ('Full', 'Full Return'),
        ('Partial', 'Partial Return')
    ])
    return_status = models.CharField(max_length=20, default='Pending', choices=[
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Completed', 'Completed')
    ])
    
    # Payment fields
    payment_terms = models.CharField(max_length=50, blank=True, null=True)  # Cash, Bank, Credit
    bank_account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="purchase_return_bank", limit_choices_to={'group': 'Bank Account'}
    )
    cash_account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name="purchase_return_cash", limit_choices_to={'group': 'Case In Hand'}
    )
    
    total_basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    dueDate = models.DateField(null=True, blank=True)
    narration = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.return_no} - {self.party.account_name}"

    def save(self, *args, **kwargs):
        from datetime import datetime
        from pos.models.settings import setting
        from django.db import transaction

        with transaction.atomic():
            if not self.return_no:
                settings_obj = setting.objects.filter(branch=self.branch).first()
                prefix = getattr(settings_obj, "PR", "PR") if settings_obj else "PR"

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

                last_return = PurchaseReturnMaster.objects.select_for_update().filter(
                    branch=self.branch,
                    return_no__startswith=pattern
                ).order_by("-id").first()

                last_no = 0
                if last_return and last_return.return_no:
                    try:
                        parts = last_return.return_no.split("/")
                        if len(parts) >= 3:
                            last_no = int(parts[-1])
                    except:
                        last_no = 0

                next_no = last_no + 1
                self.return_no = f"{pattern}{str(next_no).zfill(4)}"

                # ✅ Branch filter add kiya
                while PurchaseReturnMaster.objects.filter(
                    branch=self.branch,  # ✅ FIXED
                    return_no=self.return_no
                ).exists():
                    next_no += 1
                    self.return_no = f"{pattern}{str(next_no).zfill(4)}"

                print(f"🔐 Branch: {self.branch.branch_name} (ID: {self.branch.id}) - PR No: {self.return_no} (last: {last_no})")

            super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['branch', 'return_no'], name='unique_pr_per_branch')
        ]
class PurchaseReturnItem(models.Model):
    """Individual items in Purchase Return"""
    purchase_return = models.ForeignKey(
        PurchaseReturnMaster,
        related_name="items",
        on_delete=models.CASCADE
    )
    purchase_item = models.ForeignKey(
        PurchaseItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    item = models.ForeignKey(items, on_delete=models.CASCADE)
    variant = models.ForeignKey(
        itemvariants,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    hsn_code = models.CharField(max_length=20, blank=True)
    batch_no = models.CharField(max_length=50, blank=True)
    return_quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
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
    created_at = models.DateTimeField(auto_now_add=True, blank=True) 
    
    def __str__(self):
        return f"{self.item.itemName} - {self.return_quantity}"
    

    def save(self, *args, **kwargs):
        """
        GST calculation for Purchase Return with discount support
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

        # Get GST toggle from settings
        settings_obj = setting.objects.filter(branch=self.purchase_return.branch).first()
        gst_toggle = getattr(settings_obj, 'gst_toggle', True)

        price = safe_decimal(self.price)
        qty = safe_decimal(self.return_quantity)
        discount_percent = safe_decimal(self.discount_percent)

        # ---------- TOTAL PRICE BEFORE DISCOUNT ----------
        total_price = (price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # ---------- APPLY DISCOUNT ----------
        discount_amount = (total_price * discount_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        amount_after_discount = (total_price - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # ---------- TAX RATE ----------
        tax_rate = safe_decimal(self.tax_percent)

        if tax_rate > 0:
            if gst_toggle:
                # ON MODE: Price is BASIC, Add GST on top
                total_tax = (amount_after_discount * tax_rate / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                basic_amount = amount_after_discount
                net_amount = (basic_amount + total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                # OFF MODE: Price is NET (includes GST)
                total_tax = (amount_after_discount * tax_rate / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                net_amount = amount_after_discount
                basic_amount = (net_amount - total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            total_tax = Decimal("0.00")
            basic_amount = amount_after_discount
            net_amount = amount_after_discount

        # ---------- GST SPLIT ----------
        if self.purchase_return.branch.state == self.purchase_return.party.state:
            half_tax = (total_tax / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.cgst = half_tax
            self.sgst = half_tax
            self.igst = Decimal("0.00")
            # Adjust for rounding
            if self.cgst + self.sgst != total_tax:
                if total_tax - (self.cgst + self.sgst) > 0:
                    self.cgst += (total_tax - (self.cgst + self.sgst))
        else:
            self.cgst = Decimal("0.00")
            self.sgst = Decimal("0.00")
            self.igst = total_tax

        # ---------- FINAL VALUES ----------
        self.basic_amount = basic_amount
        self.discount_amount = discount_amount
        self.tax_amount = total_tax
        self.net_amount = net_amount

        super().save(*args, **kwargs)
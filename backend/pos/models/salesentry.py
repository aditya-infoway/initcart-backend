#pos/models/salesentry.py
from django.db import IntegrityError, models
from pos.models.account import Account
from pos.models.items import items, itemvariants
from pos.models.branch import Branch
from decimal import Decimal
from django.db import transaction
from pos.models.settings import setting
from pos.models.mixins import CreatedByMixin

class SalesMaster(CreatedByMixin, models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    bill_no = models.CharField(max_length=50, db_index=True)
    date = models.DateField()
    customer = models.ForeignKey(Account, on_delete=models.PROTECT)
    payment_terms = models.CharField(max_length=50)  # e.g., 'Credit' or 'Cash'
    narration = models.TextField(blank=True)

    total_basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    bank_account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="bank_sales"
    )
    case_account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="case_sales"
    )
    dueDate = models.DateField(blank=True, null=True)
    frightcharge = models.DecimalField(default=0, max_digits=5, decimal_places=2)
    otherexpnse = models.DecimalField(default=0, max_digits=5, decimal_places=2)    
    roundamount = models.DecimalField(default=0, max_digits=5, decimal_places=2)
    is_cancelled = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
        # ── POS MLM fields (NEW) ──────────────────────────────────────────
    referral_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Customer ne jo referral code diya sale ke time",
        db_index=True,
    )
    referral_agent = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_referred_sales",
        help_text="Agent jiska referral code use hua",
        db_index=True,
    )
    mlm_commission_processed = models.BooleanField(
        default=False,
        help_text="True = MLM commission already distribute ho gaya",
    )
    @staticmethod
    def update_balance(account, amount, transaction_type):
        """Update an account's balance correctly handling Dr/Cr flipping."""
        from decimal import Decimal
        
        amount = Decimal(amount or 0)
        if amount == 0:
            return

        print(f"\n{'='*50}")
        print(f" UPDATE BALANCE CALLED")
        print(f"Account: {account.account_name} (ID: {account.id})")
        print(f"Current Balance: {account.current_balance} {account.current_drcr}")
        print(f"Transaction: {transaction_type} of ₹{amount}")
        print(f"{'='*50}")

        if transaction_type == "Dr":
            if account.current_drcr == "Dr":
                # Dr + Dr = Dr increases (customer owes more)
                old_balance = account.current_balance
                account.current_balance += amount
                print(f" Dr + Dr: {old_balance} + {amount} = {account.current_balance} Dr")
                
            elif account.current_drcr == "Cr":
                # We owe customer, sale reduces what we owe
                if account.current_balance > amount:
                    old_balance = account.current_balance
                    account.current_balance -= amount
                    print(f" Cr reduction: {old_balance} - {amount} = {account.current_balance} Cr")
                elif account.current_balance < amount:
                    # Flip from Cr to Dr
                    old_balance = account.current_balance
                    account.current_balance = amount - account.current_balance
                    account.current_drcr = "Dr"
                    print(f"✅ Cr→Dr flip: {old_balance} Cr → {account.current_balance} Dr")
                else:  # Equal
                    account.current_balance = Decimal("0.00")
                    print(f"✅ Settled to 0")
        
        elif transaction_type == "Cr":
            if account.current_drcr == "Cr":
                old_balance = account.current_balance
                account.current_balance += amount
                print(f"✅ Cr + Cr: {old_balance} + {amount} = {account.current_balance} Cr")
            elif account.current_drcr == "Dr":
                if account.current_balance > amount:
                    old_balance = account.current_balance
                    account.current_balance -= amount
                    print(f"✅ Dr reduction: {old_balance} - {amount} = {account.current_balance} Dr")
                elif account.current_balance < amount:
                    old_balance = account.current_balance
                    account.current_balance = amount - account.current_balance
                    account.current_drcr = "Cr"
                    print(f"✅ Dr→Cr flip: {old_balance} Dr → {account.current_balance} Cr")
                else:
                    account.current_balance = Decimal("0.00")
                    print(f"✅ Settled to 0")

        account.save(update_fields=["current_balance", "current_drcr"])
        print(f"🏁 Final Balance: {account.current_balance} {account.current_drcr}\n")
    class Meta:
        unique_together = ('branch', 'bill_no')
        constraints = [
            models.UniqueConstraint(fields=['branch', 'bill_no'], name='unique_bill_per_branch')
        ]
            
    def save(self, *args, **kwargs):
        from datetime import datetime

        with transaction.atomic():
            is_new = self.pk is None

            if is_new and not self.bill_no:
                settings_obj = setting.objects.filter(branch=self.branch).first()
                prefix = getattr(settings_obj, "SI", "SI") if settings_obj else "SI"

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

                last_sale = SalesMaster.objects.select_for_update().filter(
                    branch=self.branch,
                    bill_no__startswith=pattern
                ).order_by("-id").first()

                last_no = 0
                if last_sale and last_sale.bill_no:
                    try:
                        parts = last_sale.bill_no.split("/")
                        if len(parts) >= 3:
                            last_no = int(parts[-1])
                    except:
                        last_no = 0

                next_no = last_no + 1
                self.bill_no = f"{pattern}{str(next_no).zfill(4)}"

                #  Branch filter add kiya
                while SalesMaster.objects.filter(
                    branch=self.branch,  #  FIXED
                    bill_no=self.bill_no
                ).exists():
                    next_no += 1
                    self.bill_no = f"{pattern}{str(next_no).zfill(4)}"

                print(f"🔐 Branch: {self.branch.branch_name} (ID: {self.branch.id}) - Bill No: {self.bill_no} (last: {last_no})")

            super().save(*args, **kwargs)
                    #  UPDATE CUSTOMER BALANCE FOR CREDIT SALES ONLY
            if is_new and self.customer:
                if self.payment_terms.lower() == "credit":
                    # Credit Sale = Customer Dr increases
                    self.update_balance(self.customer, self.grand_total, "Dr")
        
class SalesItem(models.Model):
    sales = models.ForeignKey(
        SalesMaster,
        related_name="items",
        on_delete=models.CASCADE
    )
    item_name = models.ForeignKey(items, on_delete=models.CASCADE)
    variant = models.ForeignKey(
        itemvariants,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    hsn_code = models.CharField(max_length=20)
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2)

    basic_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gst_toggle_status = models.BooleanField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def calculate_gst(taxable, tax_percent, branch_state, party_state):
        """
        Calculates CGST, SGST, IGST, and total tax.
        Tax-free if tax_percent <= 0.
        """
        from decimal import Decimal
        cgst = sgst = igst = Decimal("0.00")

        if tax_percent > 0:
            if branch_state == party_state:
                tax = (taxable * tax_percent) / 100
                cgst = tax / 2
                sgst = tax / 2
            else:
                igst = (taxable * tax_percent) / 100

        total_tax = cgst + sgst + igst
        return {
            "cgst": cgst,
            "sgst": sgst,
            "igst": igst,
            "total_tax": total_tax
        }
# pos/models/salesentry.py - SalesItem.save() FIX

def save(self, *args, **kwargs):
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

    settings_obj = setting.objects.filter(branch=self.sales.branch).first()
    sales_gst_toggle = getattr(settings_obj, 'sales_gst_toggle', True)

    self.gst_toggle_status = sales_gst_toggle
    price = safe_decimal(self.price)
    qty = safe_decimal(self.qty)
    discount_percent = safe_decimal(self.discount_percent)
    tax_rate = safe_decimal(self.tax_percent)

    # Total price before discount
    total_price = (price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Discount
    discount_amount = (total_price * discount_percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    amount_after_discount = (total_price - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    if tax_rate > 0:
        if sales_gst_toggle:
            # ========== GST ON (Exclusive) ==========
            total_tax = (amount_after_discount * tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            basic_amount = amount_after_discount  # Sales Net = discounted price
            net_amount = (basic_amount + total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            # ========== GST OFF (Inclusive) ==========
            # 🔥 YOUR LOGIC: GST = discounted_price × rate / 100
            # Sales Net = discounted_price - GST
            total_tax = (amount_after_discount * tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            basic_amount = (amount_after_discount - total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            net_amount = amount_after_discount  # Customer pays this
    else:
        total_tax = Decimal("0.00")
        basic_amount = amount_after_discount
        net_amount = amount_after_discount

    # GST Split
    if self.sales.branch.state == self.sales.customer.state:
        half_tax = (total_tax / 2).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.cgst = half_tax
        self.sgst = half_tax
        self.igst = Decimal("0.00")
        if self.cgst + self.sgst != total_tax:
            diff = total_tax - (self.cgst + self.sgst)
            if diff > 0:
                self.cgst += diff
    else:
        self.cgst = Decimal("0.00")
        self.sgst = Decimal("0.00")
        self.igst = total_tax

    self.basic_amount = basic_amount      # 👈 Sales Net for profit
    self.discount_amount = discount_amount
    self.tax_amount = total_tax
    self.net_amount = net_amount          # 👈 Customer pays

    super().save(*args, **kwargs)
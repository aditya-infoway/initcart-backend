#pos/models/purchaseentry.py
from django.db import models
from pos.models.account import Account
from pos.models.items import items,itemvariants
from pos.models.branch import Branch

class PurchaseMaster(models.Model):
    date = models.DateField()
    partyName = models.ForeignKey(Account, on_delete=models.CASCADE, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True)
    #partyName = models.CharField(max_length=50)
    billNo = models.CharField(max_length=50)
    terms = models.CharField(max_length=50)
    dueDate = models.DateField(null=True, blank=True)
    narration = models.TextField(blank=True)
    total_basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bank_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="bank_purchases")
    case_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="case_purchases")
    purchasebill_no = models.CharField(max_length=50)
    frightcharge = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    otherexpnse = models.DecimalField(default=0, max_digits=5, decimal_places=2)
    roundamount = models.DecimalField(default=0, max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.billNo

    @staticmethod
    def update_balance(account, amount, transaction_type):
        from decimal import Decimal

        amount = Decimal(amount or 0)
        if amount <= 0:
            return

        print(f"\n💰 UPDATE BALANCE CALLED")
        print(f"   Account: {account.account_name} (ID: {account.id})")
        print(f"   Current: ₹{account.current_balance} {account.current_drcr}")
        print(f"   Transaction: {transaction_type} ₹{amount}")

        # ================= CREDIT ENTRY =================
        if transaction_type == "Cr":

            if account.current_drcr == "Cr":
                # Cr + Cr = Plus
                old_balance = account.current_balance
                account.current_balance += amount
                print(f"   ✅ Cr + Cr: {old_balance} + {amount} = {account.current_balance} Cr")

            else:  # Account is Dr
                if account.current_balance > amount:
                    # Dr minus
                    old_balance = account.current_balance
                    account.current_balance -= amount
                    print(f"   ✅ Dr reduction: {old_balance} - {amount} = {account.current_balance} Dr")
                elif account.current_balance < amount:
                    # Dr → Cr (flip)
                    old_balance = account.current_balance
                    account.current_balance = amount - account.current_balance
                    account.current_drcr = "Cr"
                    print(f"   ✅ Dr→Cr flip: {old_balance} Dr → {account.current_balance} Cr")
                else:
                    # Equal
                    account.current_balance = Decimal("0.00")
                    print(f"   ✅ Settled to 0")

        # ================= DEBIT ENTRY =================
        else:  # transaction_type == "Dr"

            if account.current_drcr == "Dr":
                if account.current_balance > amount:
                    # Dr minus
                    old_balance = account.current_balance
                    account.current_balance -= amount
                    print(f"   ✅ Dr reduction: {old_balance} - {amount} = {account.current_balance} Dr")
                elif account.current_balance < amount:
                    # Dr → Cr
                    old_balance = account.current_balance
                    account.current_balance = amount - account.current_balance
                    account.current_drcr = "Cr"
                    print(f"   ✅ Dr→Cr flip: {old_balance} Dr → {account.current_balance} Cr")
                else:
                    # Equal
                    account.current_balance = Decimal("0.00")
                    print(f"   ✅ Settled to 0")

            else:  # Account is Cr
                # Cr + Dr = Plus
                old_balance = account.current_balance
                account.current_balance += amount
                print(f"   ✅ Cr + Dr: {old_balance} + {amount} = {account.current_balance} Cr")

        # ✅ DONO CASES MEIN SAVE KARO - YEH IMPORTANT HAI!
        account.save(update_fields=["current_balance", "current_drcr"])
        print(f"   🏁 Final Balance: ₹{account.current_balance} {account.current_drcr}\n")



    # ---------------- Main save method ----------------
    def save(self, *args, **kwargs):
        from django.db import transaction
        from decimal import Decimal
        from rest_framework.exceptions import ValidationError

        with transaction.atomic():
            is_new = self.pk is None

            old = None
            if not is_new:
                old = PurchaseMaster.objects.get(pk=self.pk)

            super().save(*args, **kwargs)

            # ---------------- BANK / CASH ----------------
            #from rest_framework.exceptions import ValidationError

            # # Inside your Purchase save() or serializer
            # if self.bank_account:
            #     diff = self.grand_total if is_new else self.grand_total - old.grand_total
            #     if self.bank_account.current_balance < diff:
            #         raise ValidationError(
            #             f"⚠ Bank account balance ({self.bank_account.current_balance}) "
            #             f"is less than required amount ({diff}). Purchase not allowed."
            #         )
            #     self.bank_account.current_balance -= diff
            #     self.bank_account.save(update_fields=["current_balance"])

            # if self.case_account:
            #     diff = self.grand_total if is_new else self.grand_total - old.grand_total
            #     if self.case_account.current_balance < diff:
            #         raise ValidationError(
            #             f" Cash in hand balance ({self.case_account.current_balance}) "
            #             f"is less than required amount ({diff}). Purchase not allowed."
            #         )
            #     self.case_account.current_balance -= diff
            #     self.case_account.save(update_fields=["current_balance"])


            # ---------------- PARTY ACCOUNT ----------------
            # if self.partyName:
            #     transaction_type = "Dr" if self.terms.lower() == "credit" else "Cr"
            #     diff = self.grand_total if is_new else self.grand_total - old.grand_total
            #     self.update_balance(self.partyName, diff, transaction_type)




class PurchaseItem(models.Model):
    purchase = models.ForeignKey(PurchaseMaster, related_name="items", on_delete=models.CASCADE, blank=True, null=True)
    itemName = models.ForeignKey(items, on_delete=models.CASCADE, blank=True, null=True)
    variant = models.ForeignKey(
        itemvariants,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    hsnCode = models.CharField(max_length=50)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    altQuantity = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    per = models.CharField(max_length=20)
    basicAmount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discountPercent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discountAmount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxAmount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    netValue = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rate = models.FloatField(default=0)

    def save(self, *args, **kwargs):
        """
        GST calculation with discount support:
        - ON MODE: Price is BASIC, GST = (Basic × Tax%) / 100, Net = Basic + GST
        - OFF MODE: Price is NET, GST = (Net × Tax%) / 100, Basic = Net - GST
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
        settings_obj = setting.objects.filter(branch=self.purchase.branch).first()
        gst_toggle = getattr(settings_obj, 'gst_toggle', True)

        price = safe_decimal(self.price)
        qty = safe_decimal(self.quantity)
        discount_percent = safe_decimal(self.discountPercent)

        # ---------- TOTAL PRICE BEFORE DISCOUNT ----------
        total_price = (price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # ---------- APPLY DISCOUNT ----------
        discount_amount = (total_price * discount_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        amount_after_discount = (total_price - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # ---------- TAX RATE ----------
        tax_rate = safe_decimal(self.itemName.taxSlab)

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
        if self.purchase.branch.state == self.purchase.partyName.state:
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
        self.basicAmount = basic_amount
        self.discountAmount = discount_amount
        self.taxAmount = total_tax
        self.netValue = net_amount

        super().save(*args, **kwargs)
# pos/serializers/salesentry_serializers.py
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework import serializers
from pos.serializers.mixins_serializers import CreatedByReadMixin

from pos.models.items import items, itemvariants
from pos.models.account import Account
from pos.models.salesentry import SalesMaster, SalesItem


# ─────────────────────────────────────────────────────────────────────────────
# Sales entry (list / read) serializers
# ─────────────────────────────────────────────────────────────────────────────

class SalesItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(
        source="item_name",
        queryset=items.objects.all()
    )
    variant = serializers.PrimaryKeyRelatedField(
        queryset=itemvariants.objects.all(),
        required=False,
        allow_null=True
    )
    item_name = serializers.SerializerMethodField(read_only=True)
    purchase_price = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SalesItem
        fields = [
            "item",
            "variant",
            "item_name",
            "hsn_code",
            "qty",
            "price",
            "unit",
            "discount_percent",
            "tax_percent",
            "basic_amount",
            "discount_amount",
            "tax_amount",
            "net_amount",
            "purchase_price",
        ]

    def get_item_name(self, obj):
        if obj.item_name:
            return obj.item_name.itemName
        return None

    def get_purchase_price(self, obj):
        # light=1 -> list screen par purchase price ki zarurat nahi (fast)
        if self.context.get("light"):
            return None
        return float(obj.effective_purchase_price or 0)


class SalesMasterSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    items = SalesItemSerializer(many=True)
    customer_name = serializers.SerializerMethodField(read_only=True)
    bank_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        required=False,
        allow_null=True
    )
    case_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        required=False,
        allow_null=True
    )
    dueDate = serializers.DateField(
        required=False,
        allow_null=True
    )
    grand_total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        coerce_to_string=False
    )

    class Meta:
        model = SalesMaster
        fields = [
            "id",
            "bill_no",
            "date",
            "customer",
            "customer_name",
            "payment_terms",
            "narration",
            "total_basic",
            "total_discount",
            "total_tax",
            "grand_total",
            "items",
            "bank_account",
            "case_account",
            "dueDate",
            "frightcharge",
            "otherexpnse",
            "roundamount",
            "created_by",
            "created_by_name",
        ]

    def get_customer_name(self, obj):
        if obj.customer:
            return obj.customer.account_name
        return None


# ─────────────────────────────────────────────────────────────────────────────
# GST calculation serializer (abhi kahin use nahi ho raha, par ab safe hai)
# Formula SalesItemTaxAPIView / SalesItem.save() jaisa hi: GST exclusive,
# same state -> CGST+SGST, alag state -> IGST.
# ─────────────────────────────────────────────────────────────────────────────

_TWO = Decimal("0.01")


def _q(value):
    return Decimal(value).quantize(_TWO, rounding=ROUND_HALF_UP)


def _tax_rate(tax_slab):
    """'18%', '18', 'Tax Free', None -> Decimal (invalid = 0)"""
    try:
        return Decimal(str(tax_slab or 0).replace("%", "").strip() or 0)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _calculate_gst(taxable, tax_percent, branch_state, party_state):
    cgst = sgst = igst = Decimal("0.00")
    if tax_percent > 0:
        tax = _q(taxable * tax_percent / 100)
        if (branch_state or "") == (party_state or ""):
            cgst = _q(tax / 2)
            sgst = _q(tax / 2)
            diff = tax - (cgst + sgst)
            if diff > 0:
                cgst += diff
        else:
            igst = tax
    return {
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "total_tax": cgst + sgst + igst,
    }


class SaleItemTaxSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0
    )

    basicAmount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discountAmount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    taxAmount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    cgst = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    sgst = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    igst = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    netValue = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    def validate(self, data):
        price = Decimal(data["price"])
        qty = Decimal(data["quantity"])
        discount = Decimal(data.get("discount_percent") or 0)

        try:
            item = items.objects.get(id=data["item_id"])
        except items.DoesNotExist:
            raise serializers.ValidationError("Invalid item")

        basic = _q(price * qty)
        discount_amt = _q(basic * discount / 100)
        taxable = _q(basic - discount_amt)

        gst = _calculate_gst(
            taxable,
            _tax_rate(item.taxSlab),
            self.context.get("branch_state", ""),
            self.context.get("party_state", ""),
        )

        return {
            "basicAmount": basic,
            "discountAmount": discount_amt,
            "taxAmount": gst["total_tax"],
            "cgst": gst["cgst"],
            "sgst": gst["sgst"],
            "igst": gst["igst"],
            "netValue": _q(taxable + gst["total_tax"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Receipt serializers (pehle ye SalesItemSerializer ka naam overwrite kar rahe
# the aur model me na hone wali fields maangte the — ab real fields se map hain)
# ─────────────────────────────────────────────────────────────────────────────

class SalesReceiptItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="item_name.itemName", read_only=True)
    rate = serializers.DecimalField(
        source="price", max_digits=10, decimal_places=2, read_only=True
    )
    amount = serializers.DecimalField(
        source="net_amount", max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = SalesItem
        fields = ("name", "qty", "rate", "amount")


class SalesReceiptSerializer(serializers.ModelSerializer):
    items = SalesReceiptItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.account_name", read_only=True)
    mobile = serializers.CharField(source="customer.mobile", read_only=True)
    total_amount = serializers.DecimalField(
        source="total_basic", max_digits=12, decimal_places=2, read_only=True
    )
    tax_amount = serializers.DecimalField(
        source="total_tax", max_digits=12, decimal_places=2, read_only=True
    )
    net_amount = serializers.DecimalField(
        source="grand_total", max_digits=12, decimal_places=2, read_only=True
    )
    payment_mode = serializers.CharField(source="payment_terms", read_only=True)

    class Meta:
        model = SalesMaster
        fields = (
            "bill_no",
            "date",
            "customer_name",
            "mobile",
            "total_amount",
            "tax_amount",
            "net_amount",
            "payment_mode",
            "items",
        )
# pos/serializers/salesentry_serializers.py
from rest_framework import serializers
from pos.serializers.mixins_serializers import CreatedByReadMixin

from pos.models.items import items,itemvariants
from pos.models.account import Account
from pos.models.salesentry import SalesMaster, SalesItem

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
    # qty = serializers.DecimalField(max_digits=10, decimal_places=2)
    # price = serializers.DecimalField(max_digits=10, decimal_places=2)
    # discount_percent = serializers.DecimalField(
    #     max_digits=5, decimal_places=2, required=False, allow_null=True, default=0
    # )
    # tax_percent = serializers.DecimalField(
    #     max_digits=5, decimal_places=2, required=False, allow_null=True, default=0
    # )
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
        """
        Variant ki purchasePrice return karo.
        Agar variant nahi hai toh item ki first variant ki price do,
        ya 0 return karo.
        """
        if obj.variant:
            return float(obj.variant.purchasePrice or 0)
        # Fallback: item ke pehle variant ki price
        first_variant = obj.item_name.variants.first() if obj.item_name else None
        if first_variant:
            return float(first_variant.purchasePrice or 0)
        return 0.0    
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
    
        
from decimal import Decimal

class SaleItemTaxSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)

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
        discount = Decimal(data.get("discount_percent", 0))

        # Fetch item
        try:
            item = items.objects.get(id=data["item_id"])
        except items.DoesNotExist:
            raise serializers.ValidationError("Invalid item")

        # Basic & Discount
        basic = price * qty
        discount_amt = (basic * discount) / 100
        taxable = basic - discount_amt

        tax_rate = Decimal(item.taxSlab or 0)
        branch_state = self.context.get("branch_state", "")
        party_state = self.context.get("party_state", "")

        # Calculate GST using reusable function
        gst = calculate_gst(taxable, tax_rate, branch_state, party_state)

        net_value = taxable + gst["total_tax"]

        return {
            "basicAmount": basic,
            "discountAmount": discount_amt,
            "taxAmount": gst["total_tax"],
            "cgst": gst["cgst"],
            "sgst": gst["sgst"],
            "igst": gst["igst"],
            "netValue": net_value,
        }
        
class SalesItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")

    class Meta:
        model = SalesItem
        fields = ("product_name", "qty", "rate", "amount")


class SalesReceiptSerializer(serializers.ModelSerializer):
    items = SalesItemSerializer(many=True, source="items.all")

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
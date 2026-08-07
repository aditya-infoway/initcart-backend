#pos/serializer/prchaseentry_serializers.py
from rest_framework import serializers
from pos.models.items import items, itemvariants
from pos.models.account import Account
from pos.models.purchaseentry import PurchaseMaster, PurchaseItem


# -----------------------
# Variant Serializer
# -----------------------
class VariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = itemvariants
        fields = ['id', 'size', 'color', 'srno', 'warrantydate', 'purchasePrice','salesPrice', 'barcode']


# -----------------------
# Item Serializer
# -----------------------
class ItemSerializer(serializers.ModelSerializer):
    variants = VariantSerializer(many=True, read_only=True)

    class Meta:
        model = items
        fields = ['id', 'itemName', 'hsnCode','taxSlab','unit', 'variants']


# -----------------------
# Purchase Item Serializer
# -----------------------
class PurchaseItemSerializer(serializers.ModelSerializer):
    itemName = serializers.PrimaryKeyRelatedField(queryset=items.objects.all())
    itemName_name = serializers.SerializerMethodField(read_only=True)
    variant = serializers.PrimaryKeyRelatedField(   # ADD
        queryset=itemvariants.objects.all(),
        required=False,
        allow_null=True
    )

    #per = serializers.CharField(required=False, allow_blank=True, default="pcs")
    #discountPercent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    #basicAmount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    #discountAmount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    #taxAmount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    netValue = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = PurchaseItem
        fields = [
            "itemName",
            "variant",
            "itemName_name",
            "hsnCode",
            "quantity",
            "altQuantity",
            "price",
            "per",
            "discountPercent",
            "basicAmount",
            "discountAmount",
            "taxAmount",
            "netValue",
        ]
    def get_itemName_name(self, obj):
        return obj.itemName.itemName if obj.itemName else None

# -----------------------
# Purchase Master Serializer (with nested items)
# -----------------------
class PurchaseSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True)
    party_name = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all(), source="partyName")
    party_name_name = serializers.SerializerMethodField(read_only=True)
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
        allow_null=True,
        input_formats=["%Y-%m-%d"]
    )

    class Meta:
        model = PurchaseMaster
        fields = [
            "id",   
            "billNo",
            "date",
            "dueDate",
            "grand_total",
            "total_basic",
            "total_net",
            "total_tax",
            "terms",
            "narration",
            "party_name",
            "party_name_name",
            "items",
            "branch",
            "bank_account",
            "case_account",
            "purchasebill_no",
            "frightcharge",
            "otherexpnse",
            "roundamount",
        ]
        read_only_fields = ["branch"]
    
            
    def get_party_name_name(self, obj):
            if obj.partyName:
                return obj.partyName.account_name
            return None
    
    def create(self, validated_data):
        request = self.context.get("request")

        # 👇 user ni branch
        branch = request.user.branch  
        

        items_data = validated_data.pop("items", [])
        

        purchase = PurchaseMaster.objects.create(
            branch=branch,   #  IMPORTANT
            **validated_data
            
        )

        total_basic = 0
        total_tax = 0
        total_net = 0

        for item in items_data:
            price = item.get("price", 0)
            quantity = item.get("quantity", 0)
            discount_percent = item.get("discountPercent", 0)
            tax_amount = item.get("taxAmount", 0)

            basic_amount = price * quantity
            discount_amount = (basic_amount * discount_percent) / 100
            net_value = basic_amount - discount_amount + tax_amount

            PurchaseItem.objects.create(
                purchase=purchase,
                itemName=item["itemName"],
                variant=item.get("variant"),
                hsnCode=item.get("hsnCode"),
                quantity=quantity,
                altQuantity=item.get("altQuantity", 0),
                price=price,
                per=item.get("per") or "pcs",
                discountPercent=discount_percent,
                basicAmount=basic_amount,
                discountAmount=discount_amount,
                taxAmount=tax_amount,
                netValue=net_value,
            )

            total_basic += basic_amount
            total_tax += tax_amount
            total_net += net_value

        purchase.total_basic = total_basic
        purchase.total_tax = total_tax
        purchase.total_net = total_net
        purchase.save()

        return purchase

# class PurchaseItemTaxSerializer(serializers.Serializer):
#     item_id = serializers.IntegerField()
#     quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
#     price = serializers.DecimalField(max_digits=10, decimal_places=2)
#     discount_percent = serializers.DecimalField(
#     max_digits=5,
#     decimal_places=2,
#     required=False,
#     default=0
# )
#     basicAmount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
#     discountAmount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
#     taxAmount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
#     cgst = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
#     sgst = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
#     igst = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
#     netValue = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

from decimal import Decimal

class PurchaseItemTaxSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    gst_toggle = serializers.BooleanField(default=True)  # GST toggle

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
        gst_toggle = data.get("gst_toggle", True)

        # Fetch item
        try:
            item = items.objects.get(id=data["item_id"])
        except items.DoesNotExist:
            raise serializers.ValidationError("Invalid item")

        # Basic & discount
        basic = price * qty
        discount_amt = (basic * discount) / 100
        taxable = basic - discount_amt

        # Tax calculation
        cgst = sgst = igst = tax = Decimal("0.00")
        if gst_toggle:
            tax_rate = Decimal(item.taxSlab or 0)
            branch_state = self.context.get("branch_state", "")
            party_state = self.context.get("party_state", "")
            if tax_rate > 0:
                if branch_state == party_state:
                    cgst = sgst = taxable * tax_rate / 100 / 2
                else:
                    igst = taxable * tax_rate / 100
            tax = cgst + sgst + igst

        net_value = taxable + tax

        return {
            "basicAmount": basic,
            "discountAmount": discount_amt,
            "taxAmount": tax,
            "cgst": cgst,
            "sgst": sgst,
            "igst": igst,
            "netValue": net_value,
        }

        
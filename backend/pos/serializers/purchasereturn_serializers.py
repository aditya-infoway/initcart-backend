#pos/serializer/purchasereturn_serializers.py
from rest_framework import serializers
from pos.models.purchasereturn import PurchaseReturnMaster, PurchaseReturnItem
from pos.models.account import Account
from pos.models.items import items, itemvariants

class PurchaseReturnItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.itemName', read_only=True)
    variant_details = serializers.SerializerMethodField()
    
    class Meta:
        model = PurchaseReturnItem
        fields = [
            'id', 'item', 'variant', 'item_name', 'variant_details',
            'hsn_code', 'batch_no', 'return_quantity', 'price',
            'discount_percent', 'tax_percent', 'basic_amount',
            'discount_amount', 'tax_amount', 'net_amount',
            'cgst', 'sgst', 'igst'
        ]
    
    def get_variant_details(self, obj):
        if obj.variant:
            return {
                'size': obj.variant.size,
                'color': obj.variant.color,
                'barcode': obj.variant.barcode
            }
        return None

class PurchaseReturnMasterSerializer(serializers.ModelSerializer):
    items = PurchaseReturnItemSerializer(many=True, read_only=True)
    party_name = serializers.CharField(source='party.account_name', read_only=True)
    
    class Meta:
        model = PurchaseReturnMaster
        fields = [
            'id', 'branch', 'return_no', 'date', 'original_bill_no',
            'party', 'party_name', 'reason_for_return', 'approved_by',
            'return_type', 'return_status', 'total_basic', 'total_tax',
            'grand_total', 'narration', 'created_at', 'items'
        ]
        read_only_fields = ['return_no', 'created_at']
#pos/serializers/salesreturn_serializers.py
from rest_framework import serializers
from pos.models.salesreturn import SalesReturnMaster, SalesReturnItem

class SalesReturnItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.itemName', read_only=True)
    variant_details = serializers.SerializerMethodField()
    
    class Meta:
        model = SalesReturnItem
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

class SalesReturnMasterSerializer(serializers.ModelSerializer):
    items = SalesReturnItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.account_name', read_only=True)
    
    class Meta:
        model = SalesReturnMaster
        fields = [
            'id', 'branch', 'return_no', 'date', 'original_bill_no',
            'customer', 'customer_name', 'reason_for_return', 'approved_by',
            'return_type', 'return_status', 'total_basic', 'total_tax',
            'grand_total', 'narration', 'created_at', 'items'
        ]
        read_only_fields = ['return_no', 'created_at']
        
        
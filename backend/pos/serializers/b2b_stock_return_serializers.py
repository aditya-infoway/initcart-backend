# pos/serializers/b2b_stock_return_serializers.py
"""
✅ COMPLETELY SEPARATE — B2B Stock Return serializers.
Existing pos/serializers/stock_return_serializers.py ko haath nahi lagaya.
"""

from rest_framework import serializers
from pos.models.b2b_stock_return import B2BStockReturn, B2BStockReturnItem
from pos.models.b2b_transfer import B2BStockTransfer, B2BStockTransferItem
from pos.models.branch import Branch
from pos.utils.transfer_chain import build_transfer_chain


def variant_info_str(variant):
    parts = [p for p in [variant.color, variant.size] if p]
    return " / ".join(parts) if parts else "Default"


class B2BStockReturnItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = B2BStockReturnItem
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class B2BStockReturnItemReadSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    company_stock = serializers.SerializerMethodField()
    branch_stock = serializers.SerializerMethodField()
    # ✅ Pura origin chain — superadmin se leke is branch tak, jitne bhi
    # B2B hops se hoke item guzri, sab dikhega
    transfer_chain = serializers.SerializerMethodField()

    class Meta:
        model = B2BStockReturnItem
        fields = [
            'id', 'item_name', 'variant_info', 'barcode', 'size', 'color',
            'hsnCode', 'taxSlab', 'quantity', 'rate',
            'is_packaging_ready', 'is_returned_to_company',
            'status', 'company_stock', 'branch_stock',
            'branch_variant_id', 'company_variant_id',
            'tax_percent', 'basic_amount', 'tax_amount', 'cgst', 'sgst', 'igst', 'net_amount',
            'transfer_chain',
        ]

    def get_status(self, obj):
        if obj.is_returned_to_company:
            return 'Returned'
        elif obj.is_packaging_ready:
            return 'Packaging Ready'
        else:
            return 'Pending'

    def get_company_stock(self, obj):
        if obj.company_variant:
            return obj.company_variant.current_stock or 0
        return 0

    def get_branch_stock(self, obj):
        if obj.branch_variant:
            return obj.branch_variant.current_stock or 0
        return 0

    def get_transfer_chain(self, obj):
        branch = obj.return_request.branch if obj.return_request else None
        if not branch or not obj.barcode:
            return []
        return build_transfer_chain(branch, obj.barcode)


class B2BStockReturnListSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.branch_name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    total_quantity = serializers.SerializerMethodField()
    source_b2b_transfer_no = serializers.CharField(source='source_b2b_transfer.transfer_no', read_only=True, default=None)

    class Meta:
        model = B2BStockReturn
        fields = [
            'id', 'return_no', 'branch_name', 'to_branch_name',
            'return_date', 'status', 'item_count', 'total_quantity',
            'note', 'created_at', 'source_b2b_transfer_no',
        ]

    def get_total_quantity(self, obj):
        return sum(item.quantity for item in obj.items.all())


class B2BStockReturnDetailSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.branch_name', read_only=True)
    items = B2BStockReturnItemReadSerializer(many=True, read_only=True)
    source_b2b_transfer_no = serializers.CharField(source='source_b2b_transfer.transfer_no', read_only=True, default=None)

    branch_details = serializers.SerializerMethodField()
    to_branch_details = serializers.SerializerMethodField()

    class Meta:
        model = B2BStockReturn
        fields = [
            'id', 'return_no', 'branch_name', 'branch_details',
            'to_branch_name', 'to_branch_details',
            'return_date', 'note', 'status',
            'source_b2b_transfer_no',
            'items', 'created_at', 'updated_at',
        ]

    def _branch_dict(self, branch):
        if not branch:
            return None
        return {
            'id': branch.id,
            'name': branch.branch_name,
            'phone': branch.phone or '',
            'email': branch.email or '',
            'address': branch.address or '',
            'city': branch.city or '',
            'state': branch.state or '',
            'pincode': branch.pincode or '',
            'owner_name': branch.owner_name or '',
            'branch_type': branch.branch_type or '',
            'status': branch.status or '',
        }

    def get_branch_details(self, obj):
        return self._branch_dict(obj.branch)

    def get_to_branch_details(self, obj):
        return self._branch_dict(obj.to_branch)


class B2BReturnStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=B2BStockReturn.STATUS_CHOICES)
    note = serializers.CharField(required=False, allow_blank=True)
    item_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class B2BReturnItemStatusSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.IntegerField(), required=True)
    is_packaging_ready = serializers.BooleanField(default=True)
    
    
    
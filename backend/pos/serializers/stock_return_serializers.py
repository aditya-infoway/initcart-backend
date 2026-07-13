from rest_framework import serializers
from pos.models.stock_return import StockReturn, StockReturnItem
from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.models.items import items, itemvariants
from pos.models.branch import Branch
from pos.models.branch_order import BranchOrder
from django.db import transaction
from pos.utils.gst_calc import calculate_gst_split


def variant_info_str(variant):
    parts = [p for p in [variant.color, variant.size] if p]
    return " / ".join(parts) if parts else "Default"


class StockReturnItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockReturnItem
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class StockReturnItemReadSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    company_stock = serializers.SerializerMethodField()
    branch_stock = serializers.SerializerMethodField()
    
    class Meta:
        model = StockReturnItem
        fields = [
            'id', 'item_name', 'variant_info', 'barcode', 'size', 'color',
            'hsnCode', 'taxSlab', 'quantity', 'rate',
            'is_packaging_ready', 'is_returned_to_company',
            'status', 'company_stock', 'branch_stock',
            'branch_variant_id', 'company_variant_id',
            'tax_percent', 'basic_amount', 'tax_amount', 'cgst', 'sgst', 'igst', 'net_amount',
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


class StockReturnListSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.branch_name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    total_quantity = serializers.SerializerMethodField()
    
    class Meta:
        model = StockReturn
        fields = [
            'id', 'return_no', 'branch_name', 'to_branch_name',
            'return_date', 'status', 'item_count', 'total_quantity',
            'note', 'created_at',
        ]
    
    def get_total_quantity(self, obj):
        return sum(item.quantity for item in obj.items.all())


# pos/serializers/stock_return_serializers.py

class StockReturnDetailSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.branch_name', read_only=True)
    items = StockReturnItemReadSerializer(many=True, read_only=True)
    source_transfer_no = serializers.CharField(
        source='source_transfer.transfer_no', read_only=True
    )
    source_order_id = serializers.CharField(
        source='source_order.order_id', read_only=True
    )
    
    # ✅ ADD BRANCH DETAILS
    branch_details = serializers.SerializerMethodField()
    to_branch_details = serializers.SerializerMethodField()
    
    class Meta:
        model = StockReturn
        fields = [
            'id', 'return_no', 'branch_name', 'branch_details',  # ✅ Added branch_details
            'to_branch_name', 'to_branch_details',  # ✅ Added to_branch_details
            'return_date', 'note', 'status',
            'source_transfer_no', 'source_order_id',
            'items', 'created_at', 'updated_at',
        ]
    
    def get_branch_details(self, obj):
        """Get full branch details for the sender branch"""
        branch = obj.branch
        if branch:
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
        return None
    
    def get_to_branch_details(self, obj):
        """Get full branch details for the receiver branch"""
        branch = obj.to_branch
        if branch:
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
        return None


class StockReturnCreateSerializer(serializers.Serializer):
    """
    Branch creates a return request
    """
    source_transfer_id = serializers.IntegerField(required=True)
    return_date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True)
    
    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        
        source_transfer_id = validated_data['source_transfer_id']
        return_date = validated_data['return_date']
        note = validated_data.get('note', '')
        
        # Get branch
        branch = getattr(user, 'branch', None)
        if not branch:
            raise serializers.ValidationError("User has no branch assigned.")
        
        # Get source transfer
        try:
            source_transfer = StockTransfer.objects.get(
                id=source_transfer_id,
                to_branch=branch,
                status='completed'
            )
        except StockTransfer.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid or not completed transfer."
            )
        
        # Check if return already exists for this transfer
        if StockReturn.objects.filter(source_transfer=source_transfer).exists():
            raise serializers.ValidationError(
                "Return already requested for this transfer."
            )
        
        # Get company/superadmin branch
        from pos.models.branch import Branch
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        superadmin_user = User.objects.filter(role='superadmin').first()
        if not superadmin_user:
            raise serializers.ValidationError("Superadmin not found.")
        
        try:
            company_branch = Branch.objects.get(user=superadmin_user)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Company branch not found.")
        
        # Create return
        return_request = StockReturn.objects.create(
            branch=branch,
            to_branch=company_branch,
            source_transfer=source_transfer,
            source_order=source_transfer.source_order,
            return_date=return_date,
            note=note,
            status='pending',
            created_by=user,
        )
        
        # Create return items from transfer items
        transfer_items = source_transfer.items.filter(
            is_stock_updated=True  # Only verified items can be returned
        )
        
        if not transfer_items.exists():
            return_request.delete()
            raise serializers.ValidationError(
                "No verified items found in this transfer to return."
            )
        
        for transfer_item in transfer_items:
            branch_variant = transfer_item.to_variant
            if not branch_variant:
                continue
            
            company_variant = transfer_item.from_variant
            
            tax_percent = getattr(transfer_item.from_item, 'taxSlab', '0') or "0"
            same_state = (branch.state or "") == (company_branch.state or "")
            gst_result = calculate_gst_split(
                transfer_item.rate, transfer_item.quantity, tax_percent, False, same_state
            )
            
            # Create return item with full quantity (can't return more than received)
            StockReturnItem.objects.create(
                return_request=return_request,
                source_transfer_item=transfer_item,
                branch_variant=branch_variant,
                company_variant=company_variant,
                item_name=transfer_item.from_item_name,
                variant_info=transfer_item.from_variant_info,
                barcode=transfer_item.from_barcode,
                size=getattr(company_variant, 'size', ''),
                color=getattr(company_variant, 'color', ''),
                hsnCode=getattr(transfer_item.from_item, 'hsnCode', ''),
                taxSlab=tax_percent,
                quantity=transfer_item.quantity,
                rate=transfer_item.rate,
                tax_percent=tax_percent,
                basic_amount=gst_result["basic_amount"],
                tax_amount=gst_result["tax_amount"],
                cgst=gst_result["cgst"],
                sgst=gst_result["sgst"],
                igst=gst_result["igst"],
                net_amount=gst_result["net_amount"],
            )
        
        return return_request


class ReturnStatusUpdateSerializer(serializers.Serializer):
    """
    Update return status
    """
    status = serializers.ChoiceField(choices=StockReturn.STATUS_CHOICES)
    note = serializers.CharField(required=False, allow_blank=True)
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="For packaging_ready status, list of item IDs to mark ready"
    )


class ReturnItemStatusSerializer(serializers.Serializer):
    """
    Update individual item status for packaging
    """
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True
    )
    is_packaging_ready = serializers.BooleanField(default=True)
    
    
    
# pos/serializers/branch_order_serializers.py
# NEW FILE

from rest_framework import serializers
from pos.models.branch_order import BranchOrder, BranchOrderItem
from pos.models.items import items as Items, itemvariants as ItemVariants


def variant_info_str(variant):
    parts = [p for p in [variant.color, variant.size] if p]
    return " / ".join(parts) if parts else "Default"


# ─────────────────────────────────────────────
# Branch: Order create karne ke liye
# ─────────────────────────────────────────────

class OrderItemCreateSerializer(serializers.Serializer):
    source_variant_id = serializers.IntegerField()
    requested_quantity = serializers.IntegerField(min_value=1)


class BranchOrderCreateSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)
    items = OrderItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        ids = [i['source_variant_id'] for i in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate variants in order.")
        return value

    def create(self, validated_data):
        from pos.models.branch import Branch
        request = self.context['request']
        user = request.user
        items_data = validated_data.pop('items')

        branch = getattr(user, 'branch', None)
        if not branch:
            raise serializers.ValidationError("User has no branch assigned.")

        order = BranchOrder.objects.create(
            branch=branch,
            created_by=user,
            note=validated_data.get('note', ''),
            status='pending',
        )

        for item_data in items_data:
            variant_id = item_data['source_variant_id']
            try:
                variant = ItemVariants.objects.select_related('item').get(
                    id=variant_id,
                    item__entry_type='company',
                    item__created_by_superadmin=True,
                )
            except ItemVariants.DoesNotExist:
                order.delete()
                raise serializers.ValidationError(
                    f"Variant {variant_id} not found or not a company item."
                )

            source_item = variant.item
            barcode = variant.barcode or ''
            global_code = f"GIC-{barcode}" if barcode else f"GIC-{source_item.id}-{variant.id}"
            
            # ✅ Calculate branch_price
            branch_price = variant.branchPrice or variant.salesPrice or 0

            BranchOrderItem.objects.create(
                order=order,
                source_item=source_item,
                source_variant=variant,
                item_name=source_item.itemName,
                variant_info=variant_info_str(variant),
                barcode=barcode,
                size=variant.size,
                color=variant.color,
                hsnCode=source_item.hsnCode,
                taxSlab=source_item.taxSlab,
                global_item_code=global_code,
                requested_quantity=item_data['requested_quantity'],
                approved_quantity=item_data['requested_quantity'],
                rate=variant.branchPrice,
                branch_price=branch_price,  # ✅ Save branch_price
            )

        return order


# ─────────────────────────────────────────────
# Read Serializers
# ─────────────────────────────────────────────


class BranchOrderItemReadSerializer(serializers.ModelSerializer):
    purchase_price = serializers.FloatField(source='rate', read_only=True)
    sales_price = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
    branch_price = serializers.FloatField(read_only=True)
    


    class Meta:
        model = BranchOrderItem
        fields = [
            'id', 'item_name', 'variant_info', 'barcode',
            'size', 'color', 'hsnCode', 'taxSlab',
            'global_item_code',
            'requested_quantity', 'approved_quantity',
            'is_removed_by_admin', 'admin_note',
            'is_transferred', 'rate',
            'purchase_price', 'sales_price', 'mrp',
            'branch_price',  # ✅ ADD THIS
            'source_item_id', 'source_variant_id',
        ]

    def get_sales_price(self, obj):
        try:
            return obj.source_variant.salesPrice
        except Exception:
            return None

    def get_mrp(self, obj):
        try:
            return obj.source_variant.mrp
        except Exception:
            return None


class BranchOrderListSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    total_requested_qty = serializers.SerializerMethodField()

    class Meta:
        model = BranchOrder
        fields = [
            'id', 'order_id', 'branch_name', 'status',
            'order_date', 'item_count', 'total_requested_qty',
            'note', 'created_at',
        ]

    def get_total_requested_qty(self, obj):
        return sum(i.requested_quantity for i in obj.items.all())


class BranchOrderDetailSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    items = BranchOrderItemReadSerializer(many=True, read_only=True)
    linked_transfer_no = serializers.CharField(
        source='linked_transfer.transfer_no', read_only=True
    )

    class Meta:
        model = BranchOrder
        fields = [
            'id', 'order_id', 'branch_name', 'status',
            'order_date', 'note', 'items',
            'linked_transfer_no', 'created_at', 'updated_at',
        ]


# ─────────────────────────────────────────────
# Superadmin: Order process karne ke liye
# ─────────────────────────────────────────────

class AdminOrderItemAdjustSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()  # BranchOrderItem.id
    approved_quantity = serializers.IntegerField(min_value=0)
    is_removed = serializers.BooleanField(default=False)
    admin_note = serializers.CharField(required=False, allow_blank=True)


# pos/serializers/branch_order_serializers.py - AdminProcessOrderSerializer

class AdminProcessOrderSerializer(serializers.Serializer):
    """
    Superadmin order items adjust karke stock transfer create karta hai.
    """
    transfer_date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True)
    items = AdminOrderItemAdjustSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Items required.")
        return value

    def update(self, instance: BranchOrder, validated_data):
        from pos.models.branch import Branch
        from pos.models.stock_transfer import StockTransfer, StockTransferItem
        from pos.serializers.stock_transfer_serializers import (
            create_full_item_in_destination, variant_info_str
        )

        request = self.context['request']
        user = request.user
        items_adjustments = validated_data['items']
        transfer_date = validated_data['transfer_date']
        note = validated_data.get('note', '')

        try:
            from_branch = Branch.objects.get(user=user)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Super Admin branch not found.")

        to_branch = instance.branch
        if from_branch.id == to_branch.id:
            raise serializers.ValidationError("Cannot transfer to same branch.")

        adj_map = {adj['item_id']: adj for adj in items_adjustments}

        active_items = []
        for order_item in instance.items.all():
            adj = adj_map.get(order_item.id)
            if adj:
                if adj.get('is_removed'):
                    order_item.is_removed_by_admin = True
                    order_item.admin_note = adj.get('admin_note', '')
                    order_item.approved_quantity = 0
                    order_item.save()
                    continue
                else:
                    order_item.approved_quantity = adj['approved_quantity']
                    order_item.admin_note = adj.get('admin_note', '')
                    order_item.save()

            if not order_item.is_removed_by_admin and (order_item.approved_quantity or 0) > 0:
                active_items.append(order_item)

        if not active_items:
            raise serializers.ValidationError(
                "No active items to transfer. All items removed or have 0 quantity."
            )

        # Stock Transfer create karo - ✅ WITHOUT STOCK DEDUCTION
        transfer = StockTransfer.objects.create(
            from_branch=from_branch,
            to_branch=to_branch,
            transfer_date=transfer_date,
            note=note or f"Order: {instance.order_id}",
            created_by=user,
            status='completed',  # ✅ Directly completed so branch can verify
            transfer_type='order',
            source_order=instance,
        )

        created_items_cache = {}

        for order_item in active_items:
            from_variant = order_item.source_variant
            from_item = order_item.source_item

            # ✅ NO STOCK CHECK AND NO STOCK DEDUCTION HERE
            # Stock will be deducted only during verification

            # Destination mein item create karo (agar nahi hai)
            item_cache_key = from_item.id
            if item_cache_key not in created_items_cache:
                dest_item = create_full_item_in_destination(from_item, to_branch)
                created_items_cache[item_cache_key] = dest_item
            else:
                dest_item = created_items_cache[item_cache_key]

            # Destination variant find karo
            dest_variant = ItemVariants.objects.filter(
                item=dest_item,
                size=from_variant.size,
                color=from_variant.color,
                srno=from_variant.srno,
                barcode=from_variant.barcode,
            ).first()

            if not dest_variant:
                dest_variant = ItemVariants.objects.create(
                    item=dest_item,
                    purchasePrice=from_variant.purchasePrice,
                    salesPrice=from_variant.salesPrice,
                    mrp=from_variant.mrp,
                    barcode=from_variant.barcode,
                    opStock=0,
                    current_stock=0,
                    size=from_variant.size,
                    color=from_variant.color,
                    srno=from_variant.srno,
                )

            # Transfer item create - ✅ rate mein branch_price store karo
            StockTransferItem.objects.create(
                transfer=transfer,
                from_item=from_item,
                from_variant=from_variant,
                from_item_name=from_item.itemName,
                from_variant_info=variant_info_str(from_variant),
                from_barcode=from_variant.barcode,
                quantity=order_item.approved_quantity,
                rate=order_item.branch_price or order_item.rate,  # ✅ branch_price as rate
                to_variant=dest_variant,
            )

            order_item.is_transferred = True
            order_item.save()

        all_items = instance.items.all()
        removed_count = all_items.filter(is_removed_by_admin=True).count()
        total_count = all_items.count()

        if removed_count == 0:
            instance.status = 'sent'
        elif removed_count < total_count:
            instance.status = 'partially_sent'
        else:
            instance.status = 'cancelled'

        instance.linked_transfer = transfer
        instance.save()

        return instance 
# pos/serializers/b2b_transfer_serializers.py

from rest_framework import serializers
from pos.models.b2b_transfer import B2BOrder, B2BOrderItem, B2BStockTransfer, B2BStockTransferItem
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants
from pos.utils.gst_calc import calculate_gst_split
from pos.models.settings import setting as SettingModel
from pos.serializers.stock_transfer_serializers import create_full_item_in_destination, variant_info_str


# ─────────────────────────────────────────────
# Requesting Branch (B): create order
# ─────────────────────────────────────────────

class B2BOrderItemCreateSerializer(serializers.Serializer):
    source_variant_id = serializers.IntegerField()
    requested_quantity = serializers.IntegerField(min_value=1)


class B2BOrderCreateSerializer(serializers.Serializer):
    source_branch_id = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True)
    items = B2BOrderItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        ids = [i['source_variant_id'] for i in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate variants in order.")
        return value

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        items_data = validated_data.pop('items')
        source_branch_id = validated_data.pop('source_branch_id')

        requesting_branch = getattr(user, 'branch', None)
        if not requesting_branch:
            raise serializers.ValidationError("User has no branch assigned.")

        try:
            source_branch = Branch.objects.get(id=source_branch_id)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Source branch not found.")

        if source_branch.id == requesting_branch.id:
            raise serializers.ValidationError("Cannot order from your own branch.")

        order = B2BOrder.objects.create(
            requesting_branch=requesting_branch,
            source_branch=source_branch,
            created_by=user,
            note=validated_data.get('note', ''),
            status='pending',
        )

        for item_data in items_data:
            variant_id = item_data['source_variant_id']
            try:
                variant = ItemVariants.objects.select_related('item').get(
                    id=variant_id, item__branch=source_branch, item__created_by_superadmin=True,
                )
            except ItemVariants.DoesNotExist:
                order.delete()
                raise serializers.ValidationError(
                    f"Variant {variant_id} not found in {source_branch.branch_name} or not eligible."
                )

            source_item = variant.item
            barcode = variant.barcode or ''
            branch_price = variant.branchPrice or variant.salesPrice or 0

            B2BOrderItem.objects.create(
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
                requested_quantity=item_data['requested_quantity'],
                rate=variant.branchPrice,
                branch_price=branch_price,
                tax_percent=source_item.taxSlab or "0",
                # available_quantity / approved_quantity / GST — 0 abhi, process time par bharega
            )

        return order


# ─────────────────────────────────────────────
# Read Serializers
# ─────────────────────────────────────────────

class B2BOrderItemReadSerializer(serializers.ModelSerializer):
    purchase_price = serializers.FloatField(source='rate', read_only=True)
    sales_price = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
    live_stock = serializers.SerializerMethodField()

    class Meta:
        model = B2BOrderItem
        fields = [
            'id', 'item_name', 'variant_info', 'barcode', 'size', 'color', 'hsnCode', 'taxSlab',
            'global_item_code', 'requested_quantity', 'available_quantity', 'approved_quantity',
            'is_removed', 'admin_note', 'rate', 'purchase_price', 'sales_price', 'mrp',
            'branch_price', 'source_item_id', 'source_variant_id', 'live_stock',
            'tax_percent', 'basic_amount', 'tax_amount', 'cgst', 'sgst', 'igst', 'net_amount',
        ]

    def get_sales_price(self, obj):
        try: return obj.source_variant.salesPrice
        except Exception: return None

    def get_mrp(self, obj):
        try: return obj.source_variant.mrp
        except Exception: return None

    def get_live_stock(self, obj):
        """Order abhi pending hai toh live stock dikhao (preview ke liye)."""
        try:
            v = obj.source_variant
            return (v.current_stock or 0) if (v.current_stock or 0) > 0 else (v.opStock or 0)
        except Exception:
            return 0


class B2BOrderListSerializer(serializers.ModelSerializer):
    requesting_branch_name = serializers.CharField(source='requesting_branch.branch_name', read_only=True)
    source_branch_name = serializers.CharField(source='source_branch.branch_name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    total_requested_qty = serializers.SerializerMethodField()

    class Meta:
        model = B2BOrder
        fields = [
            'id', 'order_id', 'requesting_branch_name', 'source_branch_name', 'status',
            'order_date', 'item_count', 'total_requested_qty', 'note', 'created_at',
        ]

    def get_total_requested_qty(self, obj):
        return sum(i.requested_quantity for i in obj.items.all())


class B2BOrderDetailSerializer(serializers.ModelSerializer):
    requesting_branch_name = serializers.CharField(source='requesting_branch.branch_name', read_only=True)
    requesting_branch_id = serializers.IntegerField(source='requesting_branch.id', read_only=True)
    source_branch_name = serializers.CharField(source='source_branch.branch_name', read_only=True)
    source_branch_id = serializers.IntegerField(source='source_branch.id', read_only=True)
    items = B2BOrderItemReadSerializer(many=True, read_only=True)
    linked_transfer_no = serializers.CharField(source='linked_transfer.transfer_no', read_only=True)
    linked_transfer_id = serializers.IntegerField(source='linked_transfer.id', read_only=True, default=None)
    credit_term = serializers.CharField(source='source_branch.credit_term', read_only=True)

    class Meta:
        model = B2BOrder
        fields = [
            'id', 'order_id', 'requesting_branch_name', 'requesting_branch_id',
            'source_branch_name', 'source_branch_id', 'status', 'order_date', 'note',
            'items', 'credit_term', 'linked_transfer_no', 'linked_transfer_id',
            'created_at', 'updated_at',
        ]


# ─────────────────────────────────────────────
# Source Branch (A): process order — SINGLE ROUND, hard-capped at live stock
# ─────────────────────────────────────────────

class B2BOrderItemAdjustSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    approved_quantity = serializers.IntegerField(min_value=0)
    admin_note = serializers.CharField(required=False, allow_blank=True)


class B2BProcessOrderSerializer(serializers.Serializer):
    """
    Source branch (A) order process karti hai — SINGLE ROUND, terminal action.
    Har item ki approved_quantity = min(requested, live_available_stock).
    A isse kam kar sakti hai, ZYADA NAHI (hard cap — validated yahin).
    Available=0 wale items automatically removed ho jaate hain.
    Jitni qty available/approved hai, usi par GST + amount banti hai.
    """
    transfer_date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True)
    items = B2BOrderItemAdjustSerializer(many=True, required=False)

    def update(self, instance: B2BOrder, validated_data):
        request = self.context['request']
        user = request.user
        transfer_date = validated_data['transfer_date']
        note = validated_data.get('note', '')
        adjustments = {a['item_id']: a for a in validated_data.get('items', [])}

        from_branch = instance.source_branch
        to_branch = instance.requesting_branch

        user_branch = getattr(user, 'branch', None)
        if not user_branch or user_branch.id != from_branch.id:
            raise serializers.ValidationError("Only the source branch can process this order.")

        if instance.status != 'pending':
            raise serializers.ValidationError(f"Order already {instance.status}.")

        settings_obj = SettingModel.objects.filter(branch=from_branch).first()
        gst_toggle = getattr(settings_obj, "stock_transfer_gst_toggle", False)
        same_state = (from_branch.state or "") == (to_branch.state or "")

        sendable_items = []  # (order_item, final_qty)

        for order_item in instance.items.all():
            variant = order_item.source_variant
            live_stock = variant.current_stock or 0
            if live_stock <= 0:
                live_stock = variant.opStock or 0

            available_qty = min(order_item.requested_quantity, max(0, live_stock))

            adj = adjustments.get(order_item.id)
            final_qty = available_qty
            note_text = ''
            if adj:
                # ✅ HARD CAP — admin kabhi available se zyada nahi bhej sakta
                final_qty = min(adj['approved_quantity'], available_qty)
                note_text = adj.get('admin_note', '')

            order_item.available_quantity = available_qty
            order_item.approved_quantity = final_qty
            order_item.admin_note = note_text
            order_item.is_removed = final_qty <= 0
            order_item.save(update_fields=['available_quantity', 'approved_quantity', 'admin_note', 'is_removed'])

            if final_qty > 0:
                sendable_items.append((order_item, final_qty))

        if not sendable_items:
            instance.status = 'no_stock'
            instance.save(update_fields=['status'])
            return instance

        transfer = B2BStockTransfer.objects.create(
            from_branch=from_branch, to_branch=to_branch, transfer_date=transfer_date,
            note=note or f"B2B Order: {instance.order_id}", created_by=user,
            status='pending', source_order=instance,
        )

        created_items_cache = {}
        for order_item, qty in sendable_items:
            from_variant = order_item.source_variant
            from_item = order_item.source_item

            if from_item.id not in created_items_cache:
                created_items_cache[from_item.id] = create_full_item_in_destination(from_item, to_branch)
            dest_item = created_items_cache[from_item.id]

            dest_variant = ItemVariants.objects.filter(
                item=dest_item, size=from_variant.size, color=from_variant.color,
                srno=from_variant.srno, barcode=from_variant.barcode,
            ).first()
            if not dest_variant:
                dest_variant = ItemVariants.objects.create(
                    item=dest_item, purchasePrice=from_variant.purchasePrice, salesPrice=from_variant.salesPrice,
                    mrp=from_variant.mrp, barcode=from_variant.barcode, opStock=0, current_stock=0,
                    size=from_variant.size, color=from_variant.color, srno=from_variant.srno,
                )

            branch_price = order_item.branch_price or from_variant.branchPrice or 0
            tax_percent = order_item.tax_percent or from_item.taxSlab or "0"
            gst_result = calculate_gst_split(branch_price, qty, tax_percent, gst_toggle, same_state)

            B2BStockTransferItem.objects.create(
                transfer=transfer, from_item=from_item, from_variant=from_variant,
                from_item_name=from_item.itemName, from_variant_info=variant_info_str(from_variant),
                from_barcode=from_variant.barcode, quantity=qty, rate=branch_price, to_variant=dest_variant,
                tax_percent=tax_percent, basic_amount=gst_result["basic_amount"], tax_amount=gst_result["tax_amount"],
                cgst=gst_result["cgst"], sgst=gst_result["sgst"], igst=gst_result["igst"], net_amount=gst_result["net_amount"],
            )

        instance.status = 'sent'
        instance.linked_transfer = transfer
        instance.save(update_fields=['status', 'linked_transfer'])
        return instance


# ─────────────────────────────────────────────
# Transfer Read Serializers
# ─────────────────────────────────────────────

class B2BTransferItemReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = B2BStockTransferItem
        fields = [
            'id', 'from_item_name', 'from_variant_info', 'from_barcode', 'quantity', 'rate',
            'is_packaged', 'is_received', 'tax_percent', 'basic_amount', 'tax_amount',
            'cgst', 'sgst', 'igst', 'net_amount',
        ]


class B2BTransferListSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source='from_branch.branch_name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.branch_name', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)
    total_quantity = serializers.SerializerMethodField()
    source_order_no = serializers.CharField(source='source_order.order_id', read_only=True)

    class Meta:
        model = B2BStockTransfer
        fields = [
            'id', 'transfer_no', 'from_branch_name', 'to_branch_name', 'transfer_date',
            'status', 'item_count', 'total_quantity', 'source_order_no', 'note', 'created_at',
        ]

    def get_total_quantity(self, obj):
        return sum(i.quantity for i in obj.items.all())


class B2BTransferDetailSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source='from_branch.branch_name', read_only=True)
    to_branch_name = serializers.CharField(source='to_branch.branch_name', read_only=True)
    items = B2BTransferItemReadSerializer(many=True, read_only=True)
    source_order_no = serializers.CharField(source='source_order.order_id', read_only=True)

    class Meta:
        model = B2BStockTransfer
        fields = [
            'id', 'transfer_no', 'from_branch_name', 'to_branch_name', 'transfer_date',
            'status', 'note', 'items', 'source_order_no', 'created_at', 'updated_at',
        ]
    
    
    
    
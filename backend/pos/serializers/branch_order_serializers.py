# pos/serializers/branch_order_serializers.py
# NEW FILE

from rest_framework import serializers
from pos.models.branch_order import BranchOrder, BranchOrderItem
from pos.models.items import items as Items, itemvariants as ItemVariants
from pos.utils.gst_calc import calculate_gst_split
from pos.models.settings import setting as SettingModel


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

                # ✅ Branch price sirf reference ke liye store hoti hai — GST yaha calculate NAHI hoti.
                # Order REQUEST stage par sirf quantity request hoti hai. GST (toggle-based)
                # sirf tab calculate hogi jab superadmin isse process/SEND karega
                # (dekho: AdminProcessOrderSerializer.update)
                branch_price = variant.branchPrice or variant.salesPrice or 0
                tax_percent = source_item.taxSlab or "0"

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
                    branch_price=branch_price,
                    tax_percent=tax_percent,
                    # basic_amount / tax_amount / cgst / sgst / igst / net_amount — default 0
                    # yaha intentionally set NAHI kiye — request stage par GST show nahi hogi
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
    sent_quantity = serializers.IntegerField(read_only=True)
    remaining_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = BranchOrderItem
        fields = [
            'id', 'item_name', 'variant_info', 'barcode',
            'size', 'color', 'hsnCode', 'taxSlab',
            'global_item_code',
            'requested_quantity', 'approved_quantity',
            'sent_quantity', 'remaining_quantity',
            'is_removed_by_admin', 'admin_note',
            'is_transferred', 'rate',
            'purchase_price', 'sales_price', 'mrp',
            'branch_price',
            'source_item_id', 'source_variant_id',
            'tax_percent', 'basic_amount', 'tax_amount', 'cgst', 'sgst', 'igst', 'net_amount',
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
    branch_id = serializers.IntegerField(source='branch.id', read_only=True)
    items = BranchOrderItemReadSerializer(many=True, read_only=True)
    linked_transfer_no = serializers.CharField(
        source='linked_transfer.transfer_no', read_only=True
    )

    class Meta:
        model = BranchOrder
        fields = [
            'id', 'order_id', 'branch_name', 'status','branch_id',
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
    Multi-round support: agar poori qty ek baar mein nahi bheji,
    baaki bachi (remaining_quantity) baad mein phir se process ki ja sakti hai.
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
        round_qty_map = {}

        for order_item in instance.items.all():
            adj = adj_map.get(order_item.id)
            if not adj:
                continue

            if adj.get('is_removed'):
                order_item.is_removed_by_admin = True
                order_item.admin_note = adj.get('admin_note', '')
                order_item.save()
                continue

            round_qty = adj.get('approved_quantity') or 0
            if round_qty <= 0:
                continue

            remaining = order_item.remaining_quantity
            if round_qty > remaining:
                raise serializers.ValidationError(
                    f"'{order_item.item_name}' ke liye sirf {remaining} qty baaki hai "
                    f"(Requested: {order_item.requested_quantity}, already sent: {order_item.sent_quantity or 0}). "
                    f"Aap {round_qty} bhejne ki koshish kar rahe ho."
                )

            order_item.approved_quantity = round_qty
            order_item.admin_note = adj.get('admin_note', '')
            order_item.save()

            active_items.append(order_item)
            round_qty_map[order_item.id] = round_qty

        if not active_items:
            raise serializers.ValidationError(
                "Is round mein bhejne layak koi item nahi mila. "
                "Ho sakta hai sab already fully sent ho ya sabki quantity 0 di gayi ho."
            )

        transfer = StockTransfer.objects.create(
            from_branch=from_branch,
            to_branch=to_branch,
            transfer_date=transfer_date,
            note=note or f"Order: {instance.order_id}",
            created_by=user,
            status='completed',
            transfer_type='order',
            source_order=instance,
        )

        settings_obj = SettingModel.objects.filter(branch=from_branch).first()
        gst_toggle = getattr(settings_obj, "stock_transfer_gst_toggle", False)
        same_state = (from_branch.state or "") == (to_branch.state or "")

        created_items_cache = {}

        for order_item in active_items:
            round_qty = round_qty_map[order_item.id]
            from_variant = order_item.source_variant
            from_item = order_item.source_item

            item_cache_key = from_item.id
            if item_cache_key not in created_items_cache:
                dest_item = create_full_item_in_destination(from_item, to_branch)
                created_items_cache[item_cache_key] = dest_item
            else:
                dest_item = created_items_cache[item_cache_key]

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
                
            branch_price = order_item.branch_price or order_item.rate or (from_variant.branchPrice or 0)
            tax_percent = order_item.tax_percent or from_item.taxSlab or "0"

            gst_result = calculate_gst_split(
                branch_price, round_qty, tax_percent, gst_toggle, same_state
            )

            StockTransferItem.objects.create(
                transfer=transfer,
                from_item=from_item,
                from_variant=from_variant,
                from_item_name=from_item.itemName,
                from_variant_info=variant_info_str(from_variant),
                from_barcode=from_variant.barcode,
                quantity=round_qty,
                rate=branch_price,
                to_variant=dest_variant,
                tax_percent=tax_percent,
                basic_amount=gst_result["basic_amount"],
                tax_amount=gst_result["tax_amount"],
                cgst=gst_result["cgst"],
                sgst=gst_result["sgst"],
                igst=gst_result["igst"],
                net_amount=gst_result["net_amount"],
            )

            order_item.sent_quantity = (order_item.sent_quantity or 0) + round_qty
            order_item.is_transferred = order_item.is_fully_sent
            order_item.save(update_fields=['sent_quantity', 'is_transferred'])

        all_items = list(instance.items.all())
        total_count = len(all_items)
        removed_count = sum(1 for i in all_items if i.is_removed_by_admin)
        fully_sent_count = sum(1 for i in all_items if not i.is_removed_by_admin and i.is_fully_sent)
        any_sent = any((i.sent_quantity or 0) > 0 for i in all_items)
        done_count = removed_count + fully_sent_count

        if removed_count == total_count:
            instance.status = 'cancelled'
        elif done_count == total_count:
            instance.status = 'sent'
        elif any_sent:
            instance.status = 'partially_sent'
        else:
            instance.status = 'processing'

        instance.linked_transfer = transfer
        instance.save()

        return instance 
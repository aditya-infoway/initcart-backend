# pos/serializers/stock_transfer_serializers.py
# SIMPLIFIED - No matching logic

from rest_framework import serializers
from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants


def variant_info_str(variant):
    """e.g. 'Red / XL' or 'Default'"""
    parts = [p for p in [variant.color, variant.size] if p]
    return " / ".join(parts) if parts else "Default"


def create_full_item_in_destination(source_item, destination_branch):
    """
    ✅ Create FULL item in destination branch with ALL variants (0 stock)
    Returns the created destination item
    """
    print(f"\n🏪 Creating FULL item in destination: {source_item.itemName}")
    print(f"   Destination branch: {destination_branch.branch_name}")
    print(f"   Source variants count: {source_item.variants.count()}")
    
    # Check if item already exists
    existing_item = Items.objects.filter(
        branch=destination_branch,
        itemName=source_item.itemName,
        created_by_superadmin=True
    ).first()
    
    if existing_item:
        print(f"   ⚠️ Item already exists in destination, skipping creation")
        return existing_item
    
    # Create new item (copy all fields from source)
    dest_item = Items.objects.create(
        entry_type=source_item.entry_type,
        itemName=source_item.itemName,
        branch=destination_branch,
        brand=source_item.brand,
        c_brand=source_item.c_brand,
        category=source_item.category,
        c_category=source_item.c_category,
        subCategory=source_item.subCategory,
        c_subCategory=source_item.c_subCategory,
        subSubCategory=source_item.subSubCategory,
        c_subSubCategory=source_item.c_subSubCategory,
        group=source_item.group,
        unit=source_item.unit,
        created_by_superadmin=True,
        hsnCode=source_item.hsnCode,
        taxSlab=source_item.taxSlab,
        website_display=source_item.website_display,
        short_description=source_item.short_description,
        full_description=source_item.full_description,
        keywords=source_item.keywords,
        main_image=source_item.main_image,
        thumbnail_image=source_item.thumbnail_image,
        gallery=source_item.gallery,
        product_condition=source_item.product_condition,
        return_policy=source_item.return_policy,
        estimated_delivery_time=source_item.estimated_delivery_time,
        free_shipping=source_item.free_shipping,
        warranty_available=source_item.warranty_available,
        warranty_period=source_item.warranty_period,
        warranty_type=source_item.warranty_type,
        warranty_description=source_item.warranty_description,
        description_features=source_item.description_features,
        specifications=source_item.specifications,
    )
    
    # ✅ Create ALL variants from source item with 0 stock
    for source_variant in source_item.variants.all():
        # ✅ Calculate branch price
        branch_price = source_variant.branchPrice or source_variant.salesPrice or 0
        
        ItemVariants.objects.create(
            item=dest_item,
            purchasePrice=branch_price,  # ✅ PURCHASE PRICE = BRANCH PRICE
            salesPrice=source_variant.salesPrice,
            mrp=source_variant.mrp,
            barcode=source_variant.barcode,
            opStock=0,
            current_stock=0,
            size=source_variant.size,
            color=source_variant.color,
            srno=source_variant.srno,
            warrantydate=source_variant.warrantydate,
            variant_image=source_variant.variant_image,
            branchPrice=branch_price,  # ✅ BRANCH PRICE bhi set karo
        )
    
    print(f"   ✅ Item created with {source_item.variants.count()} variants (all 0 stock)")
    return dest_item

class TransferItemCreateSerializer(serializers.Serializer):
    from_variant_id = serializers.IntegerField()
    quantity        = serializers.IntegerField(min_value=1)
    rate            = serializers.FloatField(default=0)



class TransferItemDetailSerializer(serializers.ModelSerializer):
    from_item_detail = serializers.SerializerMethodField()

    class Meta:
        model  = StockTransferItem
        fields = '__all__'

    def get_from_item_detail(self, obj):
        return {
            'item_id':      obj.from_item_id,
            'item_name':    obj.from_item_name,
            'variant_id':   obj.from_variant_id,
            'variant_info': obj.from_variant_info,
            'barcode':      obj.from_barcode,
        }


class StockTransferCreateSerializer(serializers.Serializer):
    to_branch_id = serializers.IntegerField()
    transfer_date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True)
    items = TransferItemCreateSerializer(many=True)
    transfer_type = serializers.CharField(required=False, default='manual')

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        items_data = validated_data.pop('items')
        transfer_type = validated_data.pop('transfer_type', 'manual')

        try:
            from_branch = Branch.objects.get(user=user)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Super Admin branch not found.")

        try:
            to_branch = Branch.objects.get(id=validated_data['to_branch_id'])
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Destination branch not found.")

        if from_branch.id == to_branch.id:
            raise serializers.ValidationError("Cannot transfer to the same branch.")

        transfer = StockTransfer.objects.create(
            from_branch=from_branch,
            to_branch=to_branch,
            transfer_date=validated_data['transfer_date'],
            note=validated_data.get('note', ''),
            created_by=user,
            status='pending',
            transfer_type=transfer_type,
        )

        created_items_cache = {}

        for item_data in items_data:
            from_variant = ItemVariants.objects.select_related('item').get(
                id=item_data['from_variant_id'],
                item__branch=from_branch
            )
            from_item = from_variant.item

            # Validate sufficient stock
            available = from_variant.current_stock or 0
            if available < item_data['quantity']:
                transfer.delete()
                raise serializers.ValidationError(
                    f"Insufficient stock for '{from_item.itemName} ({variant_info_str(from_variant)})'. "
                    f"Available: {available}, Requested: {item_data['quantity']}"
                )

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

            # ✅ SIRF BRANCH PRICE - NO SALES PRICE FALLBACK
            branch_price = from_variant.branchPrice or 0

            StockTransferItem.objects.create(
                transfer=transfer,
                from_item=from_item,
                from_variant=from_variant,
                from_item_name=from_item.itemName,
                from_variant_info=variant_info_str(from_variant),
                from_barcode=from_variant.barcode,
                quantity=item_data['quantity'],
                rate=branch_price,  # ✅ Sirf branch price
            )

        return transfer



class StockTransferDetailSerializer(serializers.ModelSerializer):
    items            = TransferItemDetailSerializer(many=True, read_only=True)
    from_branch_name = serializers.CharField(source='from_branch.branch_name', read_only=True)
    to_branch_name   = serializers.CharField(source='to_branch.branch_name', read_only=True)
    created_by_name  = serializers.SerializerMethodField()

    class Meta:
        model  = StockTransfer
        fields = '__all__'

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None


class StockTransferListSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source='from_branch.branch_name', read_only=True)
    to_branch_name   = serializers.CharField(source='to_branch.branch_name', read_only=True)
    item_count       = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model  = StockTransfer
        fields = ['id', 'transfer_no', 'from_branch_name', 'to_branch_name',
                  'transfer_date', 'status', 'item_count', 'created_at']
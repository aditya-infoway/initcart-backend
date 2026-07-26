# pos/serializers/b2b_sales_serializers.py
from rest_framework import serializers
from django.db import transaction

from pos.models.b2b_sales import B2BSale, B2BSaleItem
from pos.models.branch import Branch
from pos.models.items import itemvariants as ItemVariants
from pos.utils.gst_calc import calculate_gst_split
from pos.models.settings import setting
from pos.serializers.stock_transfer_serializers import (
    variant_info_str,
    create_full_item_in_destination,   # ✅ NEW — same function jo Stock Transfer use karta hai
)
#  Reuse existing helpers — no duplication
from pos.serializers.stock_transfer_serializers import variant_info_str



class B2BSaleItemCreateSerializer(serializers.Serializer):
    from_variant_id = serializers.IntegerField()
    quantity        = serializers.IntegerField(min_value=1)
    rate            = serializers.FloatField(default=0)


class B2BSaleItemDetailSerializer(serializers.ModelSerializer):
    from_item_detail = serializers.SerializerMethodField()

    class Meta:
        model  = B2BSaleItem
        fields = '__all__'

    def get_from_item_detail(self, obj):
        return {
            'item_id':      obj.from_item_id,
            'item_name':    obj.from_item_name,
            'variant_id':   obj.from_variant_id,
            'variant_info': obj.from_variant_info,
            'barcode':      obj.from_barcode,
        }

            
class B2BSaleCreateSerializer(serializers.Serializer):
    to_branch_id = serializers.IntegerField()
    sale_date    = serializers.DateField()
    note         = serializers.CharField(required=False, allow_blank=True)
    items        = B2BSaleItemCreateSerializer(many=True)

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        items_data = validated_data.pop('items')

        try:
            from_branch = Branch.objects.get(user=user)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Super Admin branch not found.")

        try:
            to_branch = Branch.objects.get(id=validated_data['to_branch_id'])
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Destination branch not found.")

        # ✅ CRITICAL — sirf Franchise branches hi B2B Sale receive kar sakti hain
        if to_branch.ownership_type != 'franchise':
            raise serializers.ValidationError(
                "B2B Sale only for Franchise-ownership ."
            )

        if from_branch.id == to_branch.id:
            raise serializers.ValidationError("Cannot sell to the same branch.")

        if not items_data:
            raise serializers.ValidationError("At least one item is required.")

        with transaction.atomic():
            sale = B2BSale.objects.create(
                from_branch=from_branch,
                to_branch=to_branch,
                sale_date=validated_data['sale_date'],
                note=validated_data.get('note', ''),
                created_by=user,
                status='pending',
            )

            settings_obj = setting.objects.filter(branch=from_branch).first()
            gst_toggle = getattr(settings_obj, 'stock_transfer_gst_toggle', False)
            same_state = (from_branch.state or "") == (to_branch.state or "")

            # ✅ NEW — ek hi item ke liye baar baar destination creation na ho, isliye cache
            created_items_cache = {}

            for item_data in items_data:
                from_variant = ItemVariants.objects.select_related('item').get(
                    id=item_data['from_variant_id'],
                    item__branch=from_branch
                )
                from_item = from_variant.item
                qty = item_data['quantity']

                # ✅ Stock check
                available = from_variant.current_stock or 0
                if available <= 0:
                    available = from_variant.opStock or 0

                if available < qty:
                    raise serializers.ValidationError(
                        f"Insufficient stock for '{from_item.itemName} "
                        f"({variant_info_str(from_variant)})'. Available: {available}, Requested: {qty}"
                    )

                # ✅✅ IMMEDIATE STOCK DEDUCTION — B2B Sale = Sale hi hai, isliye turant deduct
                if (from_variant.current_stock or 0) >= qty:
                    from_variant.current_stock = (from_variant.current_stock or 0) - qty
                else:
                    remaining = qty - (from_variant.current_stock or 0)
                    from_variant.current_stock = 0
                    from_variant.opStock = (from_variant.opStock or 0) - remaining
                from_variant.save(update_fields=['current_stock', 'opStock'])

                # ✅✅ NEW — Destination branch me item + SAARE variants (0 stock, barcode ke saath)
                # abhi hi bana do — Stock Transfer jaisa hi pattern. Isse verify time pe
                # sirf ADD hoga, koi naya item/variant NAHI banega → duplicate bug fix.
                cache_key = from_item.id
                if cache_key not in created_items_cache:
                    created_items_cache[cache_key] = create_full_item_in_destination(from_item, to_branch)

                branch_price = from_variant.branchPrice or 0
                tax_percent = from_item.taxSlab or "0"
                gst_result = calculate_gst_split(branch_price, qty, tax_percent, gst_toggle, same_state)

                B2BSaleItem.objects.create(
                    sale=sale,
                    from_item=from_item,
                    from_variant=from_variant,
                    from_item_name=from_item.itemName,
                    from_variant_info=variant_info_str(from_variant),
                    from_barcode=from_variant.barcode,
                    quantity=qty,
                    rate=branch_price,
                    tax_percent=tax_percent,
                    basic_amount=gst_result["basic_amount"],
                    tax_amount=gst_result["tax_amount"],
                    cgst=gst_result["cgst"],
                    sgst=gst_result["sgst"],
                    igst=gst_result["igst"],
                    net_amount=gst_result["net_amount"],
                )

        return sale
    
    
class B2BSaleDetailSerializer(serializers.ModelSerializer):
    items            = B2BSaleItemDetailSerializer(many=True, read_only=True)
    from_branch_name = serializers.CharField(source='from_branch.branch_name', read_only=True)
    to_branch_name   = serializers.CharField(source='to_branch.branch_name', read_only=True)
    created_by_name  = serializers.SerializerMethodField()

    class Meta:
        model  = B2BSale
        fields = '__all__'

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None


class B2BSaleListSerializer(serializers.ModelSerializer):
    from_branch_name = serializers.CharField(source='from_branch.branch_name', read_only=True)
    to_branch_name   = serializers.CharField(source='to_branch.branch_name', read_only=True)
    item_count       = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model  = B2BSale
        fields = ['id', 'sale_no', 'from_branch_name', 'to_branch_name',
                  'sale_date', 'status', 'item_count', 'created_at']
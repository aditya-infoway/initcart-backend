# pos/serializers/stock_transfer_serializers.py
# SIMPLIFIED - No matching logic
#
# CHANGES vs previous version (Excel import ke liye zaroori the):
#   1) from_branch ab user.get_effective_branch() se aata hai (pehle
#      Branch.objects.get(user=user) tha) -> Employee bhi transfer create kar sakta hai.
#   2) discount_percent ab ACTUALLY apply + save hota hai. Pehle serializer isse
#      ignore kar raha tha, jabki UI (preview API) discounted price par GST
#      dikha raha tha. Ab GST = (branch_price - discount) par, wahi formula jo
#      StockTransferItemTaxAPIView me hai -> UI preview == saved value.
#   3) Poora create() ek transaction.atomic() me hai. Insufficient stock / koi bhi
#      error par transfer + destination me bane items sab rollback ho jayenge
#      (pehle transfer.delete() hota tha aur destination items leak ho jate the).
#   4) Variant na mile to 500 ki jagah clean ValidationError.
#   5) quantity ab DECIMAL (max 2 places) — Excel import me 2.5 jaisi qty ke liye.
#      StockTransferItem.quantity bhi DecimalField hona chahiye (model updated).

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants
from pos.utils.gst_calc import calculate_gst_split
from pos.models.settings import setting
from pos.utils.variant_mapping import get_or_create_dest_variant


def variant_info_str(variant):
    """e.g. 'Red / XL' or 'Default'"""
    parts = [p for p in [variant.color, variant.size] if p]
    return " / ".join(parts) if parts else "Default"


def _fmt_qty(q):
    """Decimal qty readable: 2.00 -> '2', 2.50 -> '2.5'."""
    s = f"{Decimal(str(q)):f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def create_full_item_in_destination(source_item, destination_branch):
    """
    Item ke saare variants ke liye mapping ensure karo (0 stock ke saath),
    lekin fields sync mat karo — wo sirf actual transfer/verify ke time hoga.
    """
    for source_variant in source_item.variants.all():
        get_or_create_dest_variant(source_variant, destination_branch, sync_fields=False)

    # dest_item return karna ho toh:
    return Items.objects.filter(
        branch=destination_branch, itemName=source_item.itemName, created_by_superadmin=True
    ).first()

class TransferItemCreateSerializer(serializers.Serializer):
    from_variant_id   = serializers.IntegerField()
    quantity          = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    rate              = serializers.FloatField(default=0)
    discount_percent  = serializers.FloatField(default=0, required=False, min_value=0, max_value=100)



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

        # ✅ CHANGED — superadmin + employee dono ke liye sahi branch
        from_branch = user.get_effective_branch()
        if not from_branch:
            raise serializers.ValidationError("Your branch not found.")

        try:
            to_branch = Branch.objects.get(id=validated_data['to_branch_id'])
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Destination branch not found.")

        if from_branch.id == to_branch.id:
            raise serializers.ValidationError("Cannot transfer to the same branch.")

        if not items_data:
            raise serializers.ValidationError("At least one item is required.")

        # GST settings — poore transfer ke liye ek hi baar
        settings_obj = setting.objects.filter(branch=from_branch).first()
        gst_toggle = getattr(settings_obj, 'stock_transfer_gst_toggle', False)
        same_state = (from_branch.state or "") == (to_branch.state or "")

        with transaction.atomic():
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
                try:
                    from_variant = ItemVariants.objects.select_related('item').get(
                        id=item_data['from_variant_id'],
                        item__branch=from_branch
                    )
                except ItemVariants.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Item variant (id={item_data['from_variant_id']}) not found in your branch stock."
                    )
                from_item = from_variant.item

                qty = item_data['quantity']   # Decimal

                # Validate sufficient stock
                available = from_variant.current_stock or 0
                if available <= 0:
                    available = from_variant.opStock or 0

                if Decimal(str(available)) < qty:
                    raise serializers.ValidationError(
                        f"Insufficient stock for '{from_item.itemName} ({variant_info_str(from_variant)})'. "
                        f"Available: {_fmt_qty(available)}, Requested: {_fmt_qty(qty)}"
                    )

                item_cache_key = from_item.id
                if item_cache_key not in created_items_cache:
                    dest_item = create_full_item_in_destination(from_item, to_branch)
                    created_items_cache[item_cache_key] = dest_item
                else:
                    dest_item = created_items_cache[item_cache_key]

                dest_variant, _created = get_or_create_dest_variant(from_variant, to_branch, sync_fields=False)

                # ✅ SIRF BRANCH PRICE - NO SALES PRICE FALLBACK
                branch_price = from_variant.branchPrice or 0
                tax_percent = from_item.taxSlab or "0"

                # ✅ NEW — discount: branch price se minus, GST isi discounted price par
                # (formula bilkul StockTransferItemTaxAPIView jaisa — UI preview se match)
                discount_percent = float(item_data.get('discount_percent') or 0)
                discount_percent = min(max(discount_percent, 0.0), 100.0)
                discount_per_unit = (branch_price * discount_percent) / 100
                discounted_rate = branch_price - discount_per_unit
                discount_amount = round(discount_per_unit * float(qty), 2)   # float * Decimal error se bachne ke liye float(qty)

                gst_result = calculate_gst_split(
                    discounted_rate, float(qty), tax_percent, gst_toggle, same_state
                )

                StockTransferItem.objects.create(
                    transfer=transfer,
                    from_item=from_item,
                    from_variant=from_variant,
                    from_item_name=from_item.itemName,
                    from_variant_info=variant_info_str(from_variant),
                    from_barcode=from_variant.barcode,
                    quantity=qty,
                    rate=branch_price,  # ✅ Sirf branch price (discount alag se stored)
                    discount_percent=round(discount_percent, 2),
                    discount_amount=discount_amount,
                    tax_percent=tax_percent,
                    basic_amount=gst_result["basic_amount"],
                    tax_amount=gst_result["tax_amount"],
                    cgst=gst_result["cgst"],
                    sgst=gst_result["sgst"],
                    igst=gst_result["igst"],
                    net_amount=gst_result["net_amount"],
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
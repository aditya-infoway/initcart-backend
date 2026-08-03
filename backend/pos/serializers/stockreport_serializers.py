# pos/serializers/stockreport_serializers.py
from rest_framework import serializers
from django.db.models import Sum, F, DecimalField
from decimal import Decimal

from pos.models.items import itemvariants
from pos.models.purchaseentry import PurchaseItem
from pos.models.salesentry import SalesItem
from pos.models.purchasereturn import PurchaseReturnItem
from pos.models.salesreturn import SalesReturnItem
from pos.models.stock_return import StockReturnItem  
from pos.models.stock_transfer import StockTransferItem  
from pos.models.b2b_transfer import B2BStockTransferItem
from pos.models.b2b_stock_return import B2BStockReturnItem
from pos.models.b2b_sales import B2BSaleItem
from django.db.models import Q


class StockReportSerializer(serializers.ModelSerializer):
    # ---------- Item basic fields ----------
    variantId = serializers.IntegerField(source="id", read_only=True)
    id = serializers.IntegerField(source='item.id', read_only=True)
    itemName = serializers.CharField(source='item.itemName', read_only=True)
    unit = serializers.CharField(source='item.unit', read_only=True)
    hsnCode = serializers.CharField(source='item.hsnCode', read_only=True)

    brand = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    subCategory = serializers.SerializerMethodField()
    subSubCategory = serializers.SerializerMethodField()

    current_stock = serializers.SerializerMethodField()
    purchasePrice = serializers.SerializerMethodField()
    salesPrice = serializers.SerializerMethodField()

    class Meta:
        model = itemvariants
        fields = [
            "variantId", 
            'id',
            'itemName',
            'hsnCode',
            'unit',
            'brand',
            'category',
            'subCategory',
            'subSubCategory',
            'size',
            'color',
            'srno',
            'warrantydate',
            'current_stock',
            'purchasePrice',
            'salesPrice',
        ]

    # ---------- Brand / Category ----------
    def get_brand(self, obj):
        item = obj.item
        if getattr(item, 'c_brand', None):
            return {"id": item.c_brand.id, "name": item.c_brand.brand_name}
        return {"id": None, "name": getattr(item, 'brand', None)}

    def get_category(self, obj):
        item = obj.item
        if getattr(item, 'c_category', None):
            return {"id": item.c_category.id, "name": item.c_category.name}
        return {"id": None, "name": getattr(item, 'category', None)}

    def get_subCategory(self, obj):
        item = obj.item
        if getattr(item, 'c_subCategory', None):
            return {"id": item.c_subCategory.id, "name": item.c_subCategory.name}
        return {"id": None, "name": getattr(item, 'subCategory', None)}

    def get_subSubCategory(self, obj):
        item = obj.item
        if getattr(item, 'c_subSubCategory', None):
            return {"id": item.c_subSubCategory.id, "name": item.c_subSubCategory.name}
        return {"id": None, "name": getattr(item, 'subSubCategory', None)}

    # ---------- FINAL STOCK CALCULATION (VARIANT-WISE) ----------
    def get_current_stock(self, obj):
            opening_stock = Decimal(str(getattr(obj, 'opStock', 0)))
            barcode = obj.barcode   # ✅ zaroori hai neeche B2B sale ke liye

            # ---- Superadmin branch check (pehle karo, sabse neeche use hota hai) ----
            from pos.models.branch import Branch
            from django.contrib.auth import get_user_model
            User = get_user_model()
            is_superadmin_branch = False
            superadmin_user = User.objects.filter(role='superadmin').first()
            if superadmin_user:
                try:
                    superadmin_branch = Branch.objects.get(user=superadmin_user)
                    if obj.item.branch == superadmin_branch:
                        is_superadmin_branch = True
                except Branch.DoesNotExist:
                    pass

            total_purchased = PurchaseItem.objects.filter(
                variant=obj
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_purchase_returns = PurchaseReturnItem.objects.filter(
                variant=obj
            ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')

            # ✅ FIXED — barcode ki jagah to_variant FK se direct match (Stock Transfer jaisa hi)
            total_transfer_received = StockTransferItem.objects.filter(
                to_variant=obj,
                transfer__to_branch=obj.item.branch,
                is_stock_updated=True
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_transfer_sent = Decimal('0')
            if is_superadmin_branch:
                total_transfer_sent = StockTransferItem.objects.filter(
                    from_variant=obj,
                    transfer__from_branch=obj.item.branch,
                    is_stock_updated=True
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_stock_return_packaged = Decimal('0')
            if not is_superadmin_branch:
                total_stock_return_packaged = StockReturnItem.objects.filter(
                    branch_variant=obj,
                    return_request__branch=obj.item.branch,
                    is_packaging_ready=True,
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_stock_return_received = Decimal('0')
            if is_superadmin_branch:
                total_stock_return_received = StockReturnItem.objects.filter(
                    company_variant=obj,
                    return_request__to_branch=obj.item.branch,
                    is_returned_to_company=True
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_b2b_return_packaged = Decimal('0')
            if not is_superadmin_branch:
                total_b2b_return_packaged = B2BStockReturnItem.objects.filter(
                    branch_variant=obj,
                    return_request__branch=obj.item.branch,
                    is_packaging_ready=True,
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_b2b_return_received = Decimal('0')
            if is_superadmin_branch:
                total_b2b_return_received = B2BStockReturnItem.objects.filter(
                    company_variant=obj,
                    return_request__to_branch=obj.item.branch,
                    is_returned_to_company=True,
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # to_variant direct FK hai, barcode match ki zaroorat nahi
            total_b2b_received = B2BStockTransferItem.objects.filter(
                to_variant=obj,
                transfer__to_branch=obj.item.branch,
                is_received=True,
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_b2b_sent = B2BStockTransferItem.objects.filter(
                from_variant=obj,
                transfer__from_branch=obj.item.branch,
                is_packaged=True,
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_b2bsale_sent = Decimal('0')
            if is_superadmin_branch:
                total_b2bsale_sent = B2BSaleItem.objects.filter(
                    from_variant=obj,
                    sale__from_branch=obj.item.branch,
                ).exclude(
                    Q(sale__status='cancelled') & Q(is_stock_updated=False)
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # ✅ Ye barcode-based hi rehta hai — B2BSaleItem mein to_variant destination
            # branch ka variant hai, from_variant__barcode se dhoondhna hi sahi tareeka hai
            # kyunki verify hone se pehle koi FK exist hi nahi karti destination side.
            total_b2bsale_received = Decimal('0')
            if barcode:
                total_b2bsale_received = B2BSaleItem.objects.filter(
                    from_variant__barcode=barcode,
                    sale__to_branch=obj.item.branch,
                    is_stock_updated=True,
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_sold_pos = SalesItem.objects.filter(
                variant=obj
            ).aggregate(total=Sum('qty'))['total'] or Decimal('0')

            from ecommerce.models.order import OrderItem
            total_sold_website = OrderItem.objects.filter(
                product_stock=obj
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_sold = total_sold_pos + total_sold_website

            total_sales_returns = SalesReturnItem.objects.filter(
                variant=obj
            ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')

            calculated_stock = (
                opening_stock
                + total_purchased
                - total_purchase_returns
                + total_transfer_received
                - total_transfer_sent
                - total_stock_return_packaged
                + total_stock_return_received
                - total_b2b_return_packaged
                + total_b2b_return_received
                + total_b2b_received
                - total_b2b_sent
                - total_sold
                + total_sales_returns
                - total_b2bsale_sent
                
            )

            if calculated_stock < 0:
                calculated_stock = Decimal('0')

            if obj.current_stock != calculated_stock:
                obj.current_stock = calculated_stock
                obj.save(update_fields=['current_stock'])

            return float(calculated_stock)

    # ---------- Prices ----------
    def get_purchasePrice(self, obj):
        last_purchase = PurchaseItem.objects.filter(
            variant=obj
        ).order_by('-id').first()
        return float(last_purchase.price) if last_purchase else float(obj.purchasePrice or 0)

    def get_salesPrice(self, obj):
        return float(getattr(obj, 'salesPrice', 0))
    
    
    
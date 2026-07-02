# pos/serializers/stockreport_serializers.py
from rest_framework import serializers
from django.db.models import Sum, F, DecimalField
from decimal import Decimal

from pos.models.items import itemvariants
from pos.models.purchaseentry import PurchaseItem
from pos.models.salesentry import SalesItem
from pos.models.purchasereturn import PurchaseReturnItem
from pos.models.salesreturn import SalesReturnItem
from pos.models.stock_return import StockReturnItem  # ✅ ADD THIS IMPORT
from pos.models.stock_transfer import StockTransferItem  # ✅ ADD THIS IMPORT


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
        """
        Current Stock Formula:
        = Opening Stock
        + Total Purchases
        - Total Purchase Returns
        + Transfer Received
        - Transfer Sent
        - Stock Return (Packaged)      # ✅ NEW
        + Stock Return (Received)       # ✅ NEW
        - Total Sales
        + Total Sales Returns
        """

        opening_stock = Decimal(str(getattr(obj, 'opStock', 0)))

        # Total Purchases
        total_purchased = PurchaseItem.objects.filter(
            variant=obj
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

        # Total Purchase Returns (stock increases when purchase is returned)
        total_purchase_returns = PurchaseReturnItem.objects.filter(
            variant=obj
        ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')

        # ✅ Transfer Received - by barcode
        barcode = obj.barcode
        total_transfer_received = Decimal('0')
        if barcode:
            total_transfer_received = StockTransferItem.objects.filter(
                from_variant__barcode=barcode,
                transfer__to_branch=obj.item.branch,
                transfer__status='completed',
                is_stock_updated=True
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

        # ✅ Transfer Sent (only if superadmin branch)
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

        total_transfer_sent = Decimal('0')
        if is_superadmin_branch:
            total_transfer_sent = StockTransferItem.objects.filter(
                from_variant=obj,
                transfer__from_branch=obj.item.branch,
                transfer__status='completed',
                is_stock_updated=True
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

        # ✅ STOCK RETURN PACKAGED - Branch stock deduction
        total_stock_return_packaged = Decimal('0')
        if not is_superadmin_branch:
            # Normal branch - stock deducted when packaged
            total_stock_return_packaged = StockReturnItem.objects.filter(
                branch_variant=obj,
                return_request__branch=obj.item.branch,
                is_packaging_ready=True,
                # is_returned_to_company=False
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

        # ✅ STOCK RETURN RECEIVED - Company stock increase
        total_stock_return_received = Decimal('0')
        if is_superadmin_branch:
            # Superadmin branch - stock increased when received
            total_stock_return_received = StockReturnItem.objects.filter(
                company_variant=obj,
                return_request__to_branch=obj.item.branch,
                is_returned_to_company=True
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

        # Total Sales (from POS + Website orders via OrderItem)
        total_sold_pos = SalesItem.objects.filter(
            variant=obj
        ).aggregate(total=Sum('qty'))['total'] or Decimal('0')
        
        # Sales from Website Orders (OrderItem table)
        from ecommerce.models.order import OrderItem
        total_sold_website = OrderItem.objects.filter(
            product_stock=obj
        ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        
        total_sold = total_sold_pos + total_sold_website

        # Total Sales Returns (stock increases when sale is returned)
        total_sales_returns = SalesReturnItem.objects.filter(
            variant=obj
        ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')

        # ✅ Final stock calculation with ALL transactions
        calculated_stock = (
            opening_stock 
            + total_purchased 
            - total_purchase_returns
            + total_transfer_received
            - total_transfer_sent
            - total_stock_return_packaged      # ✅ NEW - Branch deduction
            + total_stock_return_received       # ✅ NEW - Company increase
            - total_sold 
            + total_sales_returns
        )

        # Update variant's current_stock in database
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
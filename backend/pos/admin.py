from django.contrib import admin
from pos.models.items import items
from pos.models.branch import Branch
from pos.models.purchaseentry import PurchaseMaster,PurchaseItem
from pos.models.purchasereturn import PurchaseReturnItem, PurchaseReturnMaster
from pos.models.salesreturn import SalesReturnItem, SalesReturnMaster
from ecommerce.models.category import Category,SubCategory,SubSubCategory
from pos.models.group_unit import ItemUnit, ItemGroup
from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.models.branch_order import BranchOrder,BranchOrderItem

# Register your models here.
admin.site.register(items)
admin.site.register(Branch)
admin.site.register(PurchaseMaster) 
admin.site.register(PurchaseItem)
admin.site.register(PurchaseReturnMaster) 
admin.site.register(PurchaseReturnItem)
admin.site.register(SalesReturnMaster)  
admin.site.register(SalesReturnItem)
admin.site.register(Category)
admin.site.register(SubCategory)
admin.site.register(ItemGroup)
admin.site.register(ItemUnit)
admin.site.register(StockTransferItem)
admin.site.register(StockTransfer)
admin.site.register(BranchOrder)
# pos/urls.py - Add order URLs at the end

from django.urls import path
from pos.views.item_views import (
    ItemCreate, Itemdelete, Itemupdate, BranchFieldConfig,
    UserBranchTypeView, Itemview, Itemvariantview, Itemvariantdelete,
    CategoryListAPI, SubCategoryListAPI, SubSubCategoryListAPI,
    BrandListAPI, ItemDetailAPIView,ItemWithVariantsDetailAPIView,
    ItemFilterOptionsAPI, CheckBranchBarcodeView
)
from pos.views.website_item_views import (
    WebsiteItemsListAPI, WebsiteItemDetailAPI, UpdateWebsiteItemAPI,
    DeleteWebsiteItemAPI, AdminWebsiteItemsListAPI, AdminApproveWebsiteItemAPI,
    ManualSyncItemToProductAPI, WebsiteItemsDashboardAPI,
)
#  Import order views for branch
from pos.views.branch_order_views import (
    BranchOrderListAPIView, BranchOrderDetailAPIView,
    BranchOrderStatsAPIView, BranchOrderStatusUpdateAPIView,
)
from pos.views.branch_delivery_views import (
    BranchDeliveryInfoAPIView,
    BranchInvoiceAPIView,
)

from pos.views.group_unit_views import (
    GroupListCreateAPI, GroupDetailAPI,
    UnitListCreateAPI, UnitDetailAPI,
    AllGroupsListAPI, AllUnitsListAPI,
)

from pos.views.excel_views import (
    ExportItemsToExcel, DownloadExcelTemplate, ImportItemsFromExcel
)

from pos.views.manualexcel_views import (
    ManualDownloadExcelTemplate,
    ManualImportItemsFromExcel,
    ManualExportItemsToExcel,
)   

from pos.views.barcode_views import (
    PendingBarcodesListView,
    GenerateSingleBarcodeView,
    BulkGenerateBarcodeView,
    UpdateVariantStockView,
    CheckBarcodeAvailabilityView,
    GeneratedBarcodesListView,
    UpdateExistingBarcodeView,
    BulkUpdateBarcodesView,
)

from pos.views.unit_calculation_views import UnitPriceCalculationAPI, GetUnitsByTypeAPI

from pos.views.sales_profit_report_views import SalesBillWiseProfitReportAPIView


urlpatterns = [
    # Original POS item URLs
    path('item-create/', ItemCreate.as_view()),
    path('user-branch/', UserBranchTypeView.as_view()),
    path('branch-field/', BranchFieldConfig.as_view()),
    path('item-delete/<int:id>/', Itemdelete.as_view()),
    path('item-update/<int:id>/', Itemupdate.as_view()),    
    path('items/', Itemview.as_view()),
    path('items/<int:pk>/', ItemDetailAPIView.as_view()),
    path("items-variantes/", Itemvariantview.as_view()),
    path("variant-delete/<int:pk>/", Itemvariantdelete.as_view()),
    path("categories/", CategoryListAPI.as_view()),
    path("subcategories/", SubCategoryListAPI.as_view()),
    path("subsubcategories/", SubSubCategoryListAPI.as_view()),
    path("brands/", BrandListAPI.as_view()),
    path('items/<int:pk>/with-variants/', ItemWithVariantsDetailAPIView.as_view(), name='item-with-variants'),
    path('items/filter-options/', ItemFilterOptionsAPI.as_view(), name='item-filter-options'),
    path('barcodes/check-branch-barcode/', CheckBranchBarcodeView.as_view(), name='barcode-check-branch'),
    
    # Website items URLs
    path('website-items/', WebsiteItemsListAPI.as_view()),
    path('website-items/<int:pk>/', WebsiteItemDetailAPI.as_view()),
    path('website-items/<int:pk>/update/', UpdateWebsiteItemAPI.as_view()),
    path('website-items/<int:pk>/delete/', DeleteWebsiteItemAPI.as_view()),
    
    # Admin URLs
    path('admin/website-items/', AdminWebsiteItemsListAPI.as_view()),
    path('admin/website-items/<int:pk>/approve/', AdminApproveWebsiteItemAPI.as_view()),
    path('admin/website-items/<int:pk>/sync/', ManualSyncItemToProductAPI.as_view()),
    
    # Dashboard
    path('website-items/dashboard/', WebsiteItemsDashboardAPI.as_view()),
    
    #  Branch Order URLs
    path('branch/orders/', BranchOrderListAPIView.as_view(), name='branch-order-list'),
    path('branch/orders/stats/', BranchOrderStatsAPIView.as_view(), name='branch-order-stats'),
    path('branch/orders/<int:order_id>/', BranchOrderDetailAPIView.as_view(), name='branch-order-detail'),
    path('branch/orders/status/update/', BranchOrderStatusUpdateAPIView.as_view(), name='branch-order-status-update'),
    path('branch/orders/<int:order_id>/delivery/', BranchDeliveryInfoAPIView.as_view(), name='branch-order-delivery'),
    path('branch/orders/<int:order_id>/invoice/', BranchInvoiceAPIView.as_view(), name='branch-order-invoice'),
    
        # Group and Unit URLs
    path('groups/', GroupListCreateAPI.as_view(), name='group-list-create'),
    path('groups/<int:pk>/', GroupDetailAPI.as_view(), name='group-detail'),
    path('units/', UnitListCreateAPI.as_view(), name='unit-list-create'),
    path('units/<int:pk>/', UnitDetailAPI.as_view(), name='unit-detail'),
    path('all-groups/', AllGroupsListAPI.as_view(), name='all-groups'),
    path('all-units/', AllUnitsListAPI.as_view(), name='all-units'),
    path('units/calculate-price/', UnitPriceCalculationAPI.as_view(), name='unit-price-calculation'),
    path('units/by-type/', GetUnitsByTypeAPI.as_view(), name='units-by-type'),
    
     # Excel Export/Import URLs
    path('items/export/', ExportItemsToExcel.as_view(), name='export-items'),
    path('items/export-template/', DownloadExcelTemplate.as_view(), name='export-template'),
    path('items/import/', ImportItemsFromExcel.as_view(), name='import-items'),
    
    path('manual/template/download/', ManualDownloadExcelTemplate.as_view()),
    path('manual/template/import/',   ManualImportItemsFromExcel.as_view()),
    path('manual/items/export/',      ManualExportItemsToExcel.as_view()),
    
    # List all variants that still need a barcode
    path('barcodes/pending/', PendingBarcodesListView.as_view(),       name='barcode-pending-list'),
 
    # Auto-generate OR save manual barcode for ONE variant
    path('barcodes/generate/<int:variant_id>/',GenerateSingleBarcodeView.as_view(),    name='barcode-generate-single'),
 
    # Bulk-generate barcodes for many variants at once
    path('barcodes/bulk-generate/',BulkGenerateBarcodeView.as_view(),      name='barcode-bulk-generate'),
 
    # Update stock for a variant
    path('barcodes/update-stock/<int:variant_id>/',UpdateVariantStockView.as_view(),   name='barcode-update-stock'),
 
    # Check whether a barcode is already taken (for inline validation)
    path('barcodes/check/',CheckBarcodeAvailabilityView.as_view(),  name='barcode-check'),
    
    path('barcodes/generated/', GeneratedBarcodesListView.as_view(), name='barcode-generated-list'),
    
    path('barcodes/update/<int:variant_id>/', UpdateExistingBarcodeView.as_view(), name='barcode-update'),
    
    # Bulk update multiple barcodes
    path('barcodes/bulk-update/', BulkUpdateBarcodesView.as_view(), name='barcode-bulk-update'),
    
    path('sales-bill-wise-profit/', SalesBillWiseProfitReportAPIView.as_view(), name='sales-bill-wise-profit'),
]
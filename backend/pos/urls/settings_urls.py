from django.urls import path
from pos.views.settings_views import SettingCreateView,GenerateVoucherView, SettingUpdateView, TaxApplyUpdateView, SalesTaxApplyUpdateView, StockTransferTaxApplyUpdateView
from pos.views.settings_views import SalesBillDisplaySettingView

urlpatterns = [
    # urls.py
    path("settings/", SettingCreateView.as_view()),
    path("settings-update/", SettingUpdateView.as_view()),
    path("tax-apply-update/", TaxApplyUpdateView.as_view()),
    path("voucher/generate/", GenerateVoucherView.as_view(), name="voucher-generate"),
    path('sales-tax-apply-update/', SalesTaxApplyUpdateView.as_view()),
    path('stock-transfer-tax-apply-update/', StockTransferTaxApplyUpdateView.as_view()),
    path("sales-bill-display-setting/", SalesBillDisplaySettingView.as_view(), name="sales-bill-display-setting"),

]

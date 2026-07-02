from django.urls import path
from pos.views.settings_views import SettingCreateView,GenerateVoucherView, SettingUpdateView, TaxApplyUpdateView, SalesTaxApplyUpdateView

urlpatterns = [
    # urls.py
    path("settings/", SettingCreateView.as_view()),
    path("settings-update/", SettingUpdateView.as_view()),
    path("tax-apply-update/", TaxApplyUpdateView.as_view()),
    path("voucher/generate/", GenerateVoucherView.as_view(), name="voucher-generate"),
    path('sales-tax-apply-update/', SalesTaxApplyUpdateView.as_view()),

]

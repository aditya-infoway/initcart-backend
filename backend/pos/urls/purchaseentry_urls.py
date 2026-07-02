from django.urls import path
from pos.views.purchaseentry_views import (
    PurchaseCreateView,
    #PurchaseItemCreateView,
    PurchaseItemDelete,
    PurchaseentryUpdate,
    BranchItemsAPIView,
    PurchaseItemListAPIView,
    PurchaseItemTaxAPIView,
    PurchaseItemSearchAPIView,
    AccountCheckView,
    PurchaseItemListAllAPIView, 
    GstToggleAPIView,
    PurchaseCreditBillsAPIView,
    PayPurchaseCreditBillBankAPIView,
    PayPurchaseCreditBillCashAPIView,
)

urlpatterns = [
    path('purchase-create/',PurchaseCreateView.as_view(),name="purchase-create"),
    path('account-check/<int:pk>/',AccountCheckView.as_view()),
    path('purchse-item-search/',PurchaseItemSearchAPIView.as_view()),
    path('purchase-item/',BranchItemsAPIView.as_view()),
    path('purchse-items/',PurchaseItemListAPIView.as_view()),
    path('purchase-item-all/', PurchaseItemListAllAPIView.as_view(), name='purchase-item-all'),
    path('purchase-item-tax/', PurchaseItemTaxAPIView.as_view(), name='purchase-item-tax'),
    path('settings/gst-toggle/', GstToggleAPIView.as_view(), name='purchase-item-tax'),
    path('purchase-delete/<int:id>/',PurchaseItemDelete.as_view(),name="purchase-delete"),
    path('purchase-update/<int:id>/',PurchaseentryUpdate.as_view(),name="purchase-update"),
    path('purchase-credit-bills/', PurchaseCreditBillsAPIView.as_view(), name='purchase-credit-bills'),
    path('pay-purchase-credit-bill-cash/', PayPurchaseCreditBillCashAPIView.as_view(), name='pay-purchase-credit-bill-cash'),
    path('pay-purchase-credit-bill-bank/', PayPurchaseCreditBillBankAPIView.as_view(), name='pay-purchase-credit-bill-bank'),
]

# urls.py - Add sales URLs

from django.urls import path
from pos.views.salesentry_views import ( 
    SalesEntryCreateAPIView, 
    SalesItemTaxAPIView, 
    CustomerListAPIView,
    SaleItemSearchAPIView,
    SalesEntryListAPIView,
    SaleReceiptView,
    DefaultCustomerAPIView,
    SalesCreditBillsAPIView,
    ReceiveSalesCreditBillCashAPIView,
    ReceiveSalesCreditBillBankAPIView,
    
)

urlpatterns = [
    # Sales URLs
    path("salesentry-create/", SalesEntryCreateAPIView.as_view(), name="salesentry-create"),
    path("sale-search-item/", SaleItemSearchAPIView.as_view(), name="sale-search-item"),
    path("customers/", CustomerListAPIView.as_view(), name="customers"),
    path("default-customer/", DefaultCustomerAPIView.as_view(), name="customers"),
    path("salesentry-list/", SalesEntryListAPIView.as_view(), name="salesentry-list"),
    path("sale-item-tax/", SalesItemTaxAPIView.as_view(), name="sale-item-tax"),
    path("sale-receipt/<int:sale_id>/", SaleReceiptView.as_view(), name="sale-receipt"),
    path('sales-credit-bills/', SalesCreditBillsAPIView.as_view(), name='sales-credit-bills'),
    path('receive-sales-credit-bill-cash/', ReceiveSalesCreditBillCashAPIView.as_view(), name='receive-sales-credit-bill-cash'),
    path('receive-sales-credit-bill-bank/', ReceiveSalesCreditBillBankAPIView.as_view(), name='receive-sales-credit-bill-bank'),
]   
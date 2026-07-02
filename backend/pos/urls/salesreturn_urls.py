from django.urls import path
from pos.views.salesreturn_views import (
    SalesReturnCreateAPIView,
    SalesReturnListAPIView,
    SalesReturnDetailAPIView,
    SalesReturnDeleteAPIView,
    SalesBillDetailsAPIView,
    GenerateSalesReturnVoucherAPIView,
    OriginalBillSearchAPIView,
    SalesReturnCreditBillsAPIView,
    SettleCreditBillAPIView,
    SettleCreditBillBankAPIView,
)

urlpatterns = [

    # Sales Return URLs 
    path('sales-return-create/', SalesReturnCreateAPIView.as_view(), name='sales-return-create'),
    path('sales-return-list/', SalesReturnListAPIView.as_view(), name='sales-return-list'),
    path('sales-return/<int:return_id>/', SalesReturnDetailAPIView.as_view(), name='sales-return-detail'),
    path('sales-return-delete/<int:return_id>/', SalesReturnDeleteAPIView.as_view(), name='sales-return-delete'),
    path('sales-bill-details/<path:bill_no>/', SalesBillDetailsAPIView.as_view(), name='sales-bill-details'),
    path('sales-return-voucher/', GenerateSalesReturnVoucherAPIView.as_view(), name='sales-return-voucher'),
    path('sales-bill-search/', OriginalBillSearchAPIView.as_view(), name='original-bill-search'),
    path('sales-return-credit-bills/', SalesReturnCreditBillsAPIView.as_view(), name='sales-return-credit-bills'),
    path('settle-credit-bill/', SettleCreditBillAPIView.as_view(), name='settle-credit-bill'),
    path('settle-credit-bill-bank/', SettleCreditBillBankAPIView.as_view(), name='settle-credit-bill-bank'),
]

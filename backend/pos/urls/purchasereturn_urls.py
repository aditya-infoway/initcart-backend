from django.urls import path
from pos.views.purchasereturn_views import (
    PurchaseReturnCreateAPIView,
    PurchaseReturnListAPIView,
    PurchaseReturnDetailAPIView,
    PurchaseReturnDeleteAPIView,
    PurchaseBillDetailsAPIView,
    GeneratePurchaseReturnVoucherAPIView,
    OriginalBillSearchAPIView,
    ReceivePurchaseReturnCreditBillCashAPIView,
    PurchaseReturnCreditBillsAPIView,
    ReceivePurchaseReturnCreditBillBankAPIView,
    
)

urlpatterns = [
    # Purchase Return URLs
    path('purchase-return-create/', PurchaseReturnCreateAPIView.as_view(), name='purchase-return-create'),
    path('purchase-return-list/', PurchaseReturnListAPIView.as_view(), name='purchase-return-list'),
    path('purchase-return/<int:return_id>/', PurchaseReturnDetailAPIView.as_view(), name='purchase-return-detail'),
    path('purchase-return-delete/<int:return_id>/', PurchaseReturnDeleteAPIView.as_view(), name='purchase-return-delete'),
    path('purchase-bill-details/<path:bill_no>/', PurchaseBillDetailsAPIView.as_view(), name='purchase-bill-details'), 
    path('purchase-return-voucher/', GeneratePurchaseReturnVoucherAPIView.as_view(), name='purchase-return-voucher'),
    path('original-bill-search/', OriginalBillSearchAPIView.as_view(), name='original-bill-search'),
    path('receive-purchase-return-credit-bill-cash/', ReceivePurchaseReturnCreditBillCashAPIView.as_view(), name='receive-purchase-return-credit-bill-cash'),
    path('purchase-return-credit-bills/', PurchaseReturnCreditBillsAPIView.as_view(), name='purchase-return-credit-bills'),
    path('receive-purchase-return-credit-bill-bank/', ReceivePurchaseReturnCreditBillBankAPIView.as_view(), name='receive-purchase-return-credit-bill-bank'),    
]

    
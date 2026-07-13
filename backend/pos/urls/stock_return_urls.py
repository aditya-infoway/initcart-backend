from django.urls import path 
from pos.views.stock_return_views import (
    EligibleTransfersForReturnView,
    StockReturnCreateView,
    StockReturnListView,
    StockReturnDetailView,
    ReturnPackagingUpdateView,
    ReturnApproveRejectView,
    ReturnReceiveView,
    ReturnCancelView,
    AdminReturnListView,
    VerifiedItemsForReturnView,
    StockReturnCreateFromItemsView,
    NextReturnNumberPreviewView,

)

from pos.views.stock_return_receipt_views import (
     StockReturnCreditBillsView,
     ReceiveStockReturnBillBankView,
     ReceiveStockReturnBillCashView,
)

from pos.views.stock_return_refund_views import (
     StockReturnRefundBillsView,
     PayStockReturnBillBankView,
     PayStockReturnBillCashView
)

urlpatterns = [

    
    # Branch: Get eligible transfers
    path('stock-returns/eligible-transfers/', 
         EligibleTransfersForReturnView.as_view(), 
         name='eligible-transfers'),
    
    # Branch: Create return
    path('stock-returns/create/', 
         StockReturnCreateView.as_view(), 
         name='return-create'),
    
    # Branch: List returns
    path('stock-returns/', 
         StockReturnListView.as_view(), 
         name='return-list'),
    
    # Branch: Return detail
    path('stock-returns/<int:return_id>/', 
         StockReturnDetailView.as_view(), 
         name='return-detail'),
    
    # Branch: Update packaging status
    path('stock-returns/<int:return_id>/packaging/', 
         ReturnPackagingUpdateView.as_view(), 
         name='return-packaging'),
    
    # Branch: Cancel return
    path('stock-returns/<int:return_id>/cancel/', 
         ReturnCancelView.as_view(), 
         name='return-cancel'),
    
    # Superadmin: Approve/Reject
    path('admin/stock-returns/<int:return_id>/process/', 
         ReturnApproveRejectView.as_view(), 
         name='admin-return-process'),
    
    # Superadmin: Receive return (stock increase)
    path('admin/stock-returns/<int:return_id>/receive/', 
         ReturnReceiveView.as_view(), 
         name='admin-return-receive'),
    
    # Superadmin: List all returns
    path('admin/stock-returns/', 
         AdminReturnListView.as_view(), 
         name='admin-return-list'),
    
    path('stock-returns/verified-items/', VerifiedItemsForReturnView.as_view(), name='verified-items'),
    
    path('stock-returns/create-from-items/', StockReturnCreateFromItemsView.as_view(), name='return-create-from-items'),
    
    path('stock-returns/next-number-preview/', NextReturnNumberPreviewView.as_view(), name='next-return-number-preview'),
    
    path('stock-return-credit-bills/', StockReturnCreditBillsView.as_view()),
    path('receive-stock-return-bill-cash/', ReceiveStockReturnBillCashView.as_view()),
    path('receive-stock-return-bill-bank/', ReceiveStockReturnBillBankView.as_view()),

    path('stock-return-refund-bills/', StockReturnRefundBillsView.as_view(), name='stock-return-refund-bills'),
    path('pay-stock-return-bill-cash/', PayStockReturnBillCashView.as_view(), name='pay-stock-return-bill-cash'),
    path('pay-stock-return-bill-bank/', PayStockReturnBillBankView.as_view(), name='pay-stock-return-bill-bank'),
]

from django.urls import path
from pos.views.cashreceipt_views import CashReceiptCreateView

urlpatterns = [
    
    # Cash Receipt URLs
    path('cash-receipts/', CashReceiptCreateView.as_view(), name='cash-receipts'),
    path('cash-receipts/create/', CashReceiptCreateView.as_view(), name='cash-receipt-create'),

]

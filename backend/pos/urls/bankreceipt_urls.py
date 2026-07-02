from django.urls import path
from pos.views.bankreceipt_views import BankReceiptCreateView

urlpatterns = [
    # Bank Receipt URLs
    path('bank-receipts/', BankReceiptCreateView.as_view(), name='bank-receipts'),
    path('bank-receipts/create/', BankReceiptCreateView.as_view(), name='bank-receipt-create'),

]

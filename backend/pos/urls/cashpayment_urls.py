from django.urls import path
from pos.views.cashpayment_views import CashPaymentCreateView
from pos.views.purchase_cash_payment_views import PurchaseCashPaymentCreateView, PurchaseCashPaymentListView

urlpatterns = [
    # urls.py
    path("cash-payments/", CashPaymentCreateView.as_view()),
        # Purchase Cash Payment URLs
    path('purchase-cash-payments/', PurchaseCashPaymentListView.as_view(), name='purchase-cash-payments'),
    path('purchase-cash-payment-create/', PurchaseCashPaymentCreateView.as_view(), name='purchase-cash-payment-create'),
]

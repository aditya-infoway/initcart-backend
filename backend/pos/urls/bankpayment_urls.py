from django.urls import path
from pos.views.bankpayment_views import BankPaymentCreateView

urlpatterns = [

    path("bank-payments/", BankPaymentCreateView.as_view()),

]

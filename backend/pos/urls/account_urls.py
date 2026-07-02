from django.urls import path

from pos.views.account_views import (
    AccountCreateView,
    SupplierListAPIView, 
    AccountListAPIView, 
    AccountUpdateAPIView,
    AccountsByTermsAPIView,
    AccountTypeAPIView,
    AccountAPIView,
    CustomerCreateView,
    
)
from pos.views.outstanding_views import OutstandingReportAPIView
from pos.views.due_payment_report_views import DuePaymentReportAPIView

urlpatterns = [
    path("account-create/",AccountCreateView.as_view()),
    path("account-type/",SupplierListAPIView.as_view()),
    path("all-account/",AccountAPIView.as_view()),
    path("account/",AccountListAPIView.as_view()),
    path("account-terms-type/",AccountsByTermsAPIView.as_view()),
    path("account/<int:id>/", AccountUpdateAPIView.as_view(), name="account-update"),
    path("account-list/", AccountListAPIView.as_view(), name="account-list"),
    path('customer-create/', CustomerCreateView.as_view(), name='customer-create'),
    path('outstanding-report/', OutstandingReportAPIView.as_view(), name='outstanding-report'),
        path(
        'due-payment-report/',
        DuePaymentReportAPIView.as_view(),
        name='due-payment-report'
    ),
]

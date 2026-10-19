# urls.py mein add karo

from django.urls import path
from ecommerce.views.payment_request_views import (
    VendorPaymentRequestFormDataAPIView, VendorPaymentRequestCreateAPIView,
    VendorPaymentRequestListAPIView,
    AdminPaymentRequestListAPIView, AdminPaymentRequestDetailAPIView,
    AdminPaymentRequestApproveAPIView, AdminPaymentRequestRejectAPIView,
    AdminPaymentRequestMarkPaidAPIView, VendorPaymentRequestDetailAPIView,
    VendorOrderReportAPIView, AdminAllVendorsOrderReportAPIView,
)

# Add these imports near your other view imports in ecommerce/urls.py
from ecommerce.views.refund_views import (
    AdminRefundListAPIView,
    AdminRefundProcessAPIView,
    VendorRefundListAPIView,
)

urlpatterns = [
    # Vendor
    path('vendor/payment-request/form-data/', VendorPaymentRequestFormDataAPIView.as_view()),
    path('vendor/payment-request/create/', VendorPaymentRequestCreateAPIView.as_view()),
    path('vendor/payment-request/list/', VendorPaymentRequestListAPIView.as_view()),
    path('vendor/payment-request/<int:pk>/', VendorPaymentRequestDetailAPIView.as_view()),
    path('vendor/order-report/', VendorOrderReportAPIView.as_view()),

    # Superadmin
    path('admin/payment-requests/', AdminPaymentRequestListAPIView.as_view()),
    path('admin/payment-requests/<int:pk>/', AdminPaymentRequestDetailAPIView.as_view()),
    path('admin/payment-requests/<int:pk>/approve/', AdminPaymentRequestApproveAPIView.as_view()),
    path('admin/payment-requests/<int:pk>/reject/', AdminPaymentRequestRejectAPIView.as_view()),
    path('admin/payment-requests/<int:pk>/mark-paid/', AdminPaymentRequestMarkPaidAPIView.as_view()),
    path('admin/order-report/', AdminAllVendorsOrderReportAPIView.as_view()),
]


from ecommerce.views.return_views import (
    CustomerCreateReturnAPIView, CustomerReturnListAPIView, CustomerRequestAgainAPIView,
    VendorReturnListAPIView, VendorReturnActionAPIView,
    AdminReturnListAPIView, AdminReturnActionAPIView,
)

urlpatterns += [
    # Customer
    path('public/returns/create/', CustomerCreateReturnAPIView.as_view()),
    path('public/returns/', CustomerReturnListAPIView.as_view()),
    path('public/returns/<int:pk>/request-again/', CustomerRequestAgainAPIView.as_view()),

    # Vendor
    path('vendor/returns/', VendorReturnListAPIView.as_view()),
    path('vendor/returns/<int:pk>/action/', VendorReturnActionAPIView.as_view()),

    # Admin
    path('admin/returns/', AdminReturnListAPIView.as_view()),
    path('admin/returns/<int:pk>/action/', AdminReturnActionAPIView.as_view()),
]


urlpatterns += [
    # Vendor — read-only visibility
    path('vendor/refunds/', VendorRefundListAPIView.as_view(), name='vendor-refund-list'),

    # Superadmin
    path('admin/refunds/', AdminRefundListAPIView.as_view(), name='admin-refund-list'),
    path('admin/refunds/<int:pk>/process/', AdminRefundProcessAPIView.as_view(), name='admin-refund-process'),
]


from ecommerce.views.refund_views import (
    AdminCODRefundPayableListAPIView,
    AdminCODRefundDetailAPIView,
    AdminCODRefundPayAPIView,
    AdminRefundBankAccountListCreateAPIView,
    AdminRefundBankAccountDetailAPIView,
    AdminRefundBankLedgerAPIView,
    CustomerReturnBankDetailsAPIView,
)

urlpatterns += [
    # Customer — add/fix bank details for a COD return
    path('public/returns/<int:pk>/bank-details/', CustomerReturnBankDetailsAPIView.as_view(),
         name='customer-return-bank-details'),

    # Superadmin — COD refunds
    path('admin/cod-refunds/payable/', AdminCODRefundPayableListAPIView.as_view(), name='admin-cod-refund-payable'),
    path('admin/cod-refunds/<int:pk>/', AdminCODRefundDetailAPIView.as_view(), name='admin-cod-refund-detail'),
    path('admin/cod-refunds/<int:pk>/pay/', AdminCODRefundPayAPIView.as_view(), name='admin-cod-refund-pay'),

    # Superadmin — refund bank accounts + ledger
    path('admin/refund-bank-accounts/', AdminRefundBankAccountListCreateAPIView.as_view(),
         name='admin-refund-bank-accounts'),
    path('admin/refund-bank-accounts/<int:pk>/', AdminRefundBankAccountDetailAPIView.as_view(),
         name='admin-refund-bank-account-detail'),
    path('admin/refund-bank-accounts/<int:pk>/ledger/', AdminRefundBankLedgerAPIView.as_view(),
         name='admin-refund-bank-ledger'),
]
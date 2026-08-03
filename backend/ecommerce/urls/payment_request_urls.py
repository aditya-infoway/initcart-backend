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
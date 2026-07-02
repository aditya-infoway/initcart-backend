# ecommerce/urls/vendor_order_urls.py

from django.urls import path
from ecommerce.views.vendor_order_views import (
    VendorOrderListAPIView,
    VendorOrderDetailAPIView,
    VendorOrderStatusUpdateAPIView,
    VendorDeliveryInfoAPIView,
    VendorOrderStatsAPIView,
    VendorInvoiceAPIView,
    VendorSendInvoiceEmailAPIView
)

urlpatterns = [
    path('vendor/orders/', VendorOrderListAPIView.as_view(), name='vendor-order-list'),
    path('vendor/orders/stats/', VendorOrderStatsAPIView.as_view(), name='vendor-order-stats'),
    path('vendor/orders/<int:order_id>/', VendorOrderDetailAPIView.as_view(), name='vendor-order-detail'),
    path('vendor/orders/status/update/', VendorOrderStatusUpdateAPIView.as_view(), name='vendor-order-status-update'),
    path('vendor/orders/<int:order_id>/delivery/', VendorDeliveryInfoAPIView.as_view(), name='vendor-order-delivery'),
    path('vendor/orders/<int:order_id>/invoice/', VendorInvoiceAPIView.as_view(), name='vendor-order-invoice'),
    path('vendor/orders/<int:order_id>/send-email/', VendorSendInvoiceEmailAPIView.as_view(), name='vendor-order-send-email'),
]
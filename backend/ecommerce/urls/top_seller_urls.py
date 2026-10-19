from django.urls import path
from ecommerce.views.top_seller_views import (
    VendorTopSellerListAPIView, VendorTopSellerCreateAPIView,
    AdminTopSellerListAPIView, AdminTopSellerDetailAPIView,
    AdminTopSellerApproveAPIView, AdminTopSellerRejectAPIView,
    AdminTopSellerToggleAPIView, AdminTopSellerOrderAPIView,
    AdminTopSellerBannerAPIView,
    PublicTopSellersAPIView,
)

urlpatterns = [
    # Vendor
    path('vendor/top-seller/list/', VendorTopSellerListAPIView.as_view()),
    path('vendor/top-seller/create/', VendorTopSellerCreateAPIView.as_view()),

    # Superadmin
    path('admin/top-seller-requests/', AdminTopSellerListAPIView.as_view()),
    path('admin/top-seller-requests/<int:pk>/', AdminTopSellerDetailAPIView.as_view()),
    path('admin/top-seller-requests/<int:pk>/approve/', AdminTopSellerApproveAPIView.as_view()),
    path('admin/top-seller-requests/<int:pk>/reject/', AdminTopSellerRejectAPIView.as_view()),
    path('admin/top-seller-requests/<int:pk>/toggle/', AdminTopSellerToggleAPIView.as_view()),
    path('admin/top-seller-requests/<int:pk>/order/', AdminTopSellerOrderAPIView.as_view()),
    path('admin/top-seller-requests/<int:pk>/banner/', AdminTopSellerBannerAPIView.as_view()),

    # Public
    path('public/top-sellers/', PublicTopSellersAPIView.as_view()),
]
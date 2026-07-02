# ecommerce/urls/product_urls.py
from django.urls import path
from ecommerce.views.product_views import (
    VendorAddProductAPI,
    VendorProductListAPI,
    VendorProductUpdateDeleteAPI,
    AdminProductListAPI,
    AdminApproveProductAPI,
)

urlpatterns = [
    # Vendor product management
    path("vendor/create/", VendorAddProductAPI.as_view(), name="vendor-product-create"),
    path("vendor/products/", VendorProductListAPI.as_view(), name="vendor-product-list"),
    path("vendor/products/<int:pk>/", VendorProductUpdateDeleteAPI.as_view(), name="vendor-product-detail"),
    
    # Admin product management  
    path("admin/products/", AdminProductListAPI.as_view(), name="admin-product-list"),
    path("admin/products/<int:pk>/approve/", AdminApproveProductAPI.as_view(), name="admin-product-approve"),
]


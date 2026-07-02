# ecommerce/urls/coupon_urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ecommerce.views.coupon_views import (
    VendorCouponViewSet,
    CouponCheckoutAPIView,
    PublicCouponAPIView,
    CustomerCouponUsageViewSet,
    VendorCouponDataAPIView,    
    CouponProductsView,
    VendorCouponUsageDetailsView,
)

router = DefaultRouter()
router.register(r'vendor/coupons', VendorCouponViewSet, basename='vendor-coupons')
router.register(r'my-coupon-usages', CustomerCouponUsageViewSet, basename='my-coupon-usages')

urlpatterns = [
    path('', include(router.urls)),
    
    path('checkout/coupons/', CouponCheckoutAPIView.as_view(), name='checkout-coupons'),
    path('validate-coupon/', PublicCouponAPIView.as_view(), name='validate-coupon'),
    
    # Keep this for backward compatibility
    path('vendor/coupons/vendor_data/', 
         VendorCouponViewSet.as_view({'get': 'vendor_data'}), 
         name='vendor-coupons-data'),
    
    # New dedicated endpoint
    path('vendor/coupon-data/', 
         VendorCouponDataAPIView.as_view(), 
         name='vendor-coupon-data'),

             #  NEW: Coupon products view endpoint
    path('vendor/coupons/<int:coupon_id>/products/', 
         CouponProductsView.as_view(), 
         name='coupon-products'),
    
    #  NEW: Vendor coupon usage details
    path('vendor/coupons/<int:coupon_id>/usage-details/', 
         VendorCouponUsageDetailsView.as_view(), 
         name='vendor-coupon-usage-details'),
]
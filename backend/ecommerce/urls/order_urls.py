#ecommerce/urls/order_urls.py 
from django.urls import path, include
from ecommerce.views.order_views import OrderDetailAPIView, OrderListAPIView
from rest_framework.routers import DefaultRouter
from ecommerce.views.cart_views import (
    CartViewSet, CustomerAddressViewSet, CheckoutAPIView,
 LoyaltyPointsAPIView, CreateRazorpayOrderAPIView
)

router = DefaultRouter()
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'customer/addresses', CustomerAddressViewSet, basename='customer-address')


urlpatterns = [
    path('', include(router.urls)),
    path('checkout/', CheckoutAPIView.as_view(), name='checkout'),
    path('loyalty/points/', LoyaltyPointsAPIView.as_view(), name='loyalty-points'),
    path('create-razorpay-order/', CreateRazorpayOrderAPIView.as_view(), name='create-razorpay-order'), 
    path('orders/', OrderListAPIView.as_view(), name='order-list'),
    path('orders/detail/', OrderDetailAPIView.as_view(), name='order-detail'),
]                                                     
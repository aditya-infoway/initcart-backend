# ecommerce/urls/loyalty_urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ecommerce.views.loyalty_views import (
    LoyaltyPointsConfigViewSet,
    LoyaltyPointsTransactionViewSet,
    LoyaltyPointsAPIView
)

router = DefaultRouter()
router.register(r'loyalty/config', LoyaltyPointsConfigViewSet, basename='loyalty-config')
router.register(r'loyalty/transactions', LoyaltyPointsTransactionViewSet, basename='loyalty-transactions')

urlpatterns = [
    path('', include(router.urls)),
    path('public/loyalty/points/', LoyaltyPointsAPIView.as_view(), name='loyalty-points'),
]
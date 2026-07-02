from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ecommerce.views.superadmin_order_views import SuperAdminOrderViewSet
from ecommerce.views.admin_order_profit_views import (
    AdminOrderProfitBreakdownAPIView,
    AdminOrderProfitStatsAPIView,
)

router = DefaultRouter()
router.register(r'superadmin/orders', SuperAdminOrderViewSet, basename='superadmin-orders')

urlpatterns = [
    
    path("admin/order-profit/<str:order_number>/", AdminOrderProfitBreakdownAPIView.as_view(), name="admin-order-profit"),
    path("admin/order-profit-stats/",              AdminOrderProfitStatsAPIView.as_view(),     name="admin-order-profit-stats"),
    path('', include(router.urls)),
    
]
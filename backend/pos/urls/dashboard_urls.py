from django.urls import path
from pos.views.dashboard_views import DashboardSummaryView, ProductStatisticsAPIView, SalesDashboardAPIView

urlpatterns = [
    path("dashboard-summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("product-stats/", ProductStatisticsAPIView.as_view()),
     path('sales-dashboard/', SalesDashboardAPIView.as_view()),
]
    
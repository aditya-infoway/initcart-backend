#mlm/urls/profit_distribution_urls.py
from django.urls import path
from mlm.views.profit_distribution_views import (
    ProfitDistributionCreateAPIView,
    ProfitDistributionUpdateAPIView,
    ProfitDistributionAPIView
)

urlpatterns = [

    path(
        "profit-distribution/create/",
        ProfitDistributionCreateAPIView.as_view(),
    ),

    path(
        "profit-distribution/",
        ProfitDistributionAPIView.as_view(),
    ),

    path(
        "profit-distribution/update/",
        ProfitDistributionUpdateAPIView.as_view(),
    ),

]
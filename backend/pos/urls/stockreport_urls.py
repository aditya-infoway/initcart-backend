# urls.py
from django.urls import path
from pos.views.stockreport_views import StockReportAPIView,StockHistoryAPIView

urlpatterns = [
    path('stock-report/', StockReportAPIView.as_view(), name='stock-report'),
    path("stock-history/<int:item_id>/", StockHistoryAPIView.as_view()),
]

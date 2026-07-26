from django.urls import path
from pos.views.b2b_stock_return_views import (
    EligibleB2BItemsForReturnView,
    B2BStockReturnCreateView,
    B2BStockReturnListView,
    B2BStockReturnDetailView,
    B2BReturnPackagingUpdateView,
    B2BReturnApproveRejectView,
    B2BReturnReceiveView,
    B2BReturnCancelView,
    AdminB2BReturnListView,
    NextB2BReturnNumberPreviewView,
)

urlpatterns = [
    path('b2b-stock-returns/eligible-items/', EligibleB2BItemsForReturnView.as_view()),
    path('b2b-stock-returns/create/', B2BStockReturnCreateView.as_view()),
    path('b2b-stock-returns/', B2BStockReturnListView.as_view()),
    path('b2b-stock-returns/<int:return_id>/', B2BStockReturnDetailView.as_view()),
    path('b2b-stock-returns/<int:return_id>/packaging/', B2BReturnPackagingUpdateView.as_view()),
    path('b2b-stock-returns/<int:return_id>/process/', B2BReturnApproveRejectView.as_view()),
    path('b2b-stock-returns/<int:return_id>/receive/', B2BReturnReceiveView.as_view()),
    path('b2b-stock-returns/<int:return_id>/cancel/', B2BReturnCancelView.as_view()),
    path('admin/b2b-stock-returns/', AdminB2BReturnListView.as_view()),
    path('b2b-stock-returns/next-number-preview/', NextB2BReturnNumberPreviewView.as_view()),
]
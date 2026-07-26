# pos/urls.py — add these imports + paths
from django.urls import path
from pos.views.b2b_transfer_views import (
    B2BSourceBranchListView, B2BSourceBranchItemsView,
    B2BOrderListCreateView, B2BOrderDetailView,
    B2BIncomingOrderListView, B2BProcessOrderView, B2BCancelOrderView,
    B2BIncomingTransferListView, B2BOutgoingTransferListView, B2BTransferDetailView,
    B2BConfirmTransferView, B2BPackagingReadyView, B2BReceiveTransferView, B2BCancelTransferView,
    B2BPackagingStartView, B2BNextOrderNumberPreviewView,B2BReceiveTransferItemView
)

urlpatterns = [
    path('b2b-source-branches/', B2BSourceBranchListView.as_view()),
    path('b2b-source-branch-items/<int:branch_id>/', B2BSourceBranchItemsView.as_view()),

    path('b2b-orders/', B2BOrderListCreateView.as_view()),
    path('b2b-orders/<int:order_id>/', B2BOrderDetailView.as_view()),
    path('b2b-orders/incoming/', B2BIncomingOrderListView.as_view()),
    path('b2b-orders/<int:order_id>/process/', B2BProcessOrderView.as_view()),
    path('b2b-orders/<int:order_id>/cancel/', B2BCancelOrderView.as_view()),

    path('b2b-transfers/incoming/', B2BIncomingTransferListView.as_view()),
    path('b2b-transfers/outgoing/', B2BOutgoingTransferListView.as_view()),
    path('b2b-transfers/<int:transfer_id>/', B2BTransferDetailView.as_view()),
    path('b2b-transfers/<int:transfer_id>/confirm/', B2BConfirmTransferView.as_view()),
    path('b2b-transfers/<int:transfer_id>/packaging-ready/', B2BPackagingReadyView.as_view()),
    path('b2b-transfers/<int:transfer_id>/receive/', B2BReceiveTransferView.as_view()),
    path('b2b-transfers/<int:transfer_id>/cancel/', B2BCancelTransferView.as_view()),
    path('b2b-transfers/<int:transfer_id>/packaging-start/', B2BPackagingStartView.as_view()),
    path('b2b-orders/next-number-preview/', B2BNextOrderNumberPreviewView.as_view()),
    path('b2b-transfers/<int:transfer_id>/items/<int:item_id>/receive/', B2BReceiveTransferItemView.as_view()),
]
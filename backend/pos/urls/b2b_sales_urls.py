from django.urls import path
from pos.views.b2b_sales_views import (
    B2BSaleViewSet,
    FranchiseBranchListView,
    B2BSaleItemTaxAPIView,
    PendingB2BSaleView,
    B2BSaleItemDetailView,
    VerifyB2BSaleItemView,
    VerifyAllB2BSaleItemsView,
    B2BSaleNextNumberView,
)

from pos.views.b2b_sales_receipt_views import (
    B2BSaleCreditBillsView,
    ReceiveB2BSaleBillCashView,
    ReceiveB2BSaleBillBankView,
)
from pos.views.stock_transfer_views import MyBranchItemsView

urlpatterns = [
    # Main CRUD endpoints
    path('b2b-sales/', B2BSaleViewSet.as_view({'get': 'list', 'post': 'create'}), name='b2b-sales-list'),
    path('b2b-sales/<int:pk>/', B2BSaleViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='b2b-sales-detail'),
    
    # Custom endpoints
    path('b2b-sales/franchise-branches/', FranchiseBranchListView.as_view(), name='b2b-franchise-branches'),
    path('b2b-sales/item-tax/', B2BSaleItemTaxAPIView.as_view(), name='b2b-item-tax'),
    path('b2b-sales/my-branch-items/', MyBranchItemsView.as_view(), name='b2b-my-branch-items'),
    path('b2b-sales/pending-verification/', PendingB2BSaleView.as_view(), name='b2b-pending-verification'),
    path('b2b-sales/<int:sale_id>/items/', B2BSaleItemDetailView.as_view(), name='b2b-sale-items'),
    path('b2b-sales/<int:sale_id>/verify-item/<int:item_id>/', VerifyB2BSaleItemView.as_view(), name='b2b-verify-item'),
    path('b2b-sales/<int:sale_id>/verify-all/', VerifyAllB2BSaleItemsView.as_view(), name='b2b-verify-all'),
    path('b2b-sales/next-number/', B2BSaleNextNumberView.as_view()),
    
    # ladger endpoints
    path('b2b-sale-credit-bills/', B2BSaleCreditBillsView.as_view()),
    path('receive-b2b-sale-bill-cash/', ReceiveB2BSaleBillCashView.as_view()),
    path('receive-b2b-sale-bill-bank/', ReceiveB2BSaleBillBankView.as_view()),
]
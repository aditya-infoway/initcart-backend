# pos/urls/branch_order_urls.py  (ya main pos/urls.py mein include karo)
# NEW FILE

from django.urls import path
from pos.views.branch_orders_views import (
    CompanyItemsForOrderView,
    BranchOrderListCreateView,
    BranchOrderDetailView,
    AdminOrderListView,
    AdminProcessOrderView,
    AdminCancelOrderView,
)

urlpatterns = [
    # Branch: Company items list for ordering
    path('branch-orders/company-items/', CompanyItemsForOrderView.as_view(), name='company-items-for-order'),

    # Branch: Order create + list
    path('branch-orders/', BranchOrderListCreateView.as_view(), name='branch-order-list-create'),

    # Branch/Admin: Order detail
    path('branch-orders/<int:order_id>/', BranchOrderDetailView.as_view(), name='branch-order-detail'),

    # Superadmin: All orders list (Order Tracking tab)
    path('branch-orders/admin/list/', AdminOrderListView.as_view(), name='admin-order-list'),

    # Superadmin: Process order → create transfer
    path('branch-orders/<int:order_id>/process/', AdminProcessOrderView.as_view(), name='admin-process-order'),

    # Superadmin: Cancel order
    path('branch-orders/<int:order_id>/cancel/', AdminCancelOrderView.as_view(), name='admin-cancel-order'),
]


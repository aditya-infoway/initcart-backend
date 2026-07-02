# pos/urls/stock_transfer_urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from pos.views.stock_transfer_views import (
    StockTransferViewSet,
    StockTransferPreviewView,
    PendingStockTransferView,
    VerifyStockTransferItemView,
    VerifyAllStockTransferItemsView,
    TransferItemDetailView,
    BranchItemsWithVariantsView,
    MyBranchItemsView,
    MyBranchVariantsView,   
)

router = DefaultRouter()
router.register(r'stock-transfers', StockTransferViewSet, basename='stock-transfer')

urlpatterns = [
    # Preview and sync endpoints
    path('stock-transfers/preview/', StockTransferPreviewView.as_view(), name='preview'),
    path('stock-transfers/my-items/', MyBranchItemsView.as_view(), name='my-items'),
    path('stock-transfers/branch-variants/my/', MyBranchVariantsView.as_view(), name='my-branch-variants'),
    path('stock-transfers/branch-items/<int:branch_id>/', BranchItemsWithVariantsView.as_view(), name='branch-items'),
    
    # Branch verification endpoints
    path('stock-transfers/pending-verification/', PendingStockTransferView.as_view(), name='pending-verification'),
    path('stock-transfers/<int:transfer_id>/items/', TransferItemDetailView.as_view(), name='transfer-items'),
    path('stock-transfers/<int:transfer_id>/verify-item/<int:item_id>/', VerifyStockTransferItemView.as_view(), name='verify-item'),
    path('stock-transfers/<int:transfer_id>/verify-all/', VerifyAllStockTransferItemsView.as_view(), name='verify-all'),
    
    # Router URLs (list, create, retrieve, complete, cancel)
    path('', include(router.urls)),
]

# ─────────────────────────────────────────────────────────
# Add to your main pos/urls/__init__.py or project urls.py:
#
#   from django.urls import path, include
#   urlpatterns += [
#       path('api/pos/', include('pos.urls.stock_transfer_urls')),
#   ]
# ─────────────────────────────────────────────────────────

# ENDPOINTS GENERATED:
# GET    /api/pos/stock-transfers/                         → list all transfers
# POST   /api/pos/stock-transfers/                         → create transfer
# GET    /api/pos/stock-transfers/{id}/                    → detail
# PATCH  /api/pos/stock-transfers/{id}/                    → update (note/date only)
# DELETE /api/pos/stock-transfers/{id}/                    → delete (if pending)
# POST   /api/pos/stock-transfers/{id}/complete/           → complete & move stock
# POST   /api/pos/stock-transfers/{id}/cancel/             → cancel
# POST   /api/pos/stock-transfers/{id}/map-item/           → manually map unmatched item
# GET    /api/pos/stock-transfers/branch-items/{branch_id}/→ items of a branch
# POST   /api/pos/stock-transfers/preview/                 → preview before creating

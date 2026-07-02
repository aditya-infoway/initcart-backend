# Add these two lines to your existing urls.py
# (inside the urlpatterns list — replaces any old ledger entries)

from pos.views.LedgerReport_views import LedgerAccountListView, LedgerHistoryAPIView
from django.urls import path

urlpatterns = [
    # ── Ledger ──────────────────────────────────────────────────────────────
    # List all accounts for the branch  (paginated, ?search=, ?group=)
    path("ledger-report/", LedgerAccountListView.as_view(), name="ledger-account-list"),

    # Full ledger for one account  (?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD optional)
    path("ledger-history/<int:account_id>/", LedgerHistoryAPIView.as_view(), name="ledger-history"),
]


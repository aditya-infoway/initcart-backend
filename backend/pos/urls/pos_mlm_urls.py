#pos/urls/pos_mlm_urls.py
from django.urls import path
from pos.views.pos_profit_settings_views import (
    POSProfitSettingsView,
    POSCommissionReportView,
    AdminPOSCommissionOverview,
)
from pos.views.referral_lookup import ReferralLookupAPIView

urlpatterns = [

    # POS Profit Settings (superadmin toggle)
    path(
        "pos-profit-settings/",
        POSProfitSettingsView.as_view(),
        name="pos-profit-settings",
    ),
 
    # Agent ka POS commission report
    path(
        "pos-commission-report/",
        POSCommissionReportView.as_view(),
        name="pos-commission-report",
    ),
 
    # Superadmin overview
    path(
        "admin-pos-commission/",
        AdminPOSCommissionOverview.as_view(),
        name="admin-pos-commission",
    ),
    
    path("referral-lookup/", ReferralLookupAPIView.as_view(), name="referral-lookup"),
]


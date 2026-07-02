# ecommerce/urls/campaign_urls.py
from django.urls import path
from ecommerce.views.campaign_views import (
    CampaignListCreateAPI, CampaignDetailAPI,
    VendorCampaignListAPI, VendorCampaignDetailAPI, ParticipateInCampaignAPI,
    AddProductsToCampaignAPI, VendorCampaignParticipationListAPI, RemoveProductFromCampaignAPI,
    ActiveCampaignsAPI, CampaignProductsAPI, VendorCampaignParticipationDetailAPI,
    VendorProductDetailsAPI, debug_vendor_info,
    SuperAdminCampaignParticipationDetailAPI,
    CampaignDashboardAPI,UpdateDealOfDayPlacementAPI,
    VendorUpdateCampaignProductAPI,
    # NEW VIEWS
    UpcomingDealsCountAPI,
    CampaignVendorSelectionAPI,
    CampaignAvailableVendorsAPI,
    DealOfDayProductsAPI,
    SetDealOfDayPlacementAPI,
    VendorDailyParticipationCheckAPI,
    # Product Approval Views
    ApproveCampaignProductAPI,
    RejectCampaignProductAPI,
    ApproveCampaignProductBulkAPI,
    RejectCampaignProductBulkAPI,
    ApproveParticipationWithProductsAPI,
    CampaignParticipationProductsAPI,
    ApproveCampaignParticipationAPI,
    RejectCampaignParticipationAPI,
    CampaignParticipationsListAPI,
    SaveBannerDetailsAPI,
    DealOfDayMainProductsAPI,
    DealOfDayAdminProductsAPI,
    DealOfDayAllProductsAPI,
)

urlpatterns = [
    # Super Admin URLs
    path('admin/campaigns/', CampaignListCreateAPI.as_view(), name='admin-campaigns'),
    path('admin/campaigns/<int:pk>/', CampaignDetailAPI.as_view(), name='admin-campaign-detail'),
    path('admin/campaign-participations/<int:pk>/', SuperAdminCampaignParticipationDetailAPI.as_view(), name='admin-campaign-participation-detail'),
    
    # Vendor Selection Management
    path('admin/campaigns/<int:campaign_id>/vendors/selection/', CampaignVendorSelectionAPI.as_view(), name='campaign-vendor-selection'),
    path('admin/campaigns/<int:campaign_id>/vendors/available/', CampaignAvailableVendorsAPI.as_view(), name='campaign-available-vendors'),
    
    # Product Approval URLs
    path('admin/approve-product/<int:product_id>/', ApproveCampaignProductAPI.as_view(), name='approve-campaign-product'),
    path('admin/reject-product/<int:product_id>/', RejectCampaignProductAPI.as_view(), name='reject-campaign-product'),
    path('admin/approve-products-bulk/<int:participation_id>/', ApproveCampaignProductBulkAPI.as_view(), name='approve-campaign-products-bulk'),
    path('admin/reject-products-bulk/<int:participation_id>/', RejectCampaignProductBulkAPI.as_view(), name='reject-campaign-products-bulk'),
    path('admin/approve-with-products/<int:participation_id>/', ApproveParticipationWithProductsAPI.as_view(), name='approve-participation-with-products'),
    
    # Participation Products
    path('admin/participation-products/<int:participation_id>/', CampaignParticipationProductsAPI.as_view(), name='campaign-participation-products'),
    
    # Participation Approval
    path('admin/approve-participation/<int:participation_id>/', ApproveCampaignParticipationAPI.as_view(), name='approve-campaign-participation'),
    path('admin/reject-participation/<int:participation_id>/', RejectCampaignParticipationAPI.as_view(), name='reject-campaign-participation'),
    
    # Dashboard
    path('admin/campaign-dashboard/', CampaignDashboardAPI.as_view(), name='campaign-dashboard'),
    
    # Vendor URLs
    path('vendor/campaigns/', VendorCampaignListAPI.as_view(), name='vendor-campaigns'),
    path('vendor/campaigns/<int:pk>/', VendorCampaignDetailAPI.as_view(), name='vendor-campaign-detail'),
    path('vendor/campaign-participations/', VendorCampaignParticipationListAPI.as_view(), name='vendor-campaign-participations'),
    path('vendor/campaign-participations/<int:pk>/', VendorCampaignParticipationDetailAPI.as_view(), name='vendor-campaign-participation-detail'),
    path('vendor/participate/<int:campaign_id>/', ParticipateInCampaignAPI.as_view(), name='participate-campaign'),
    path('vendor/add-products/<int:participation_id>/', AddProductsToCampaignAPI.as_view(), name='add-campaign-products'),
    path('vendor/remove-product/<int:product_id>/', RemoveProductFromCampaignAPI.as_view(), name='remove-campaign-product'),
    path('vendor/product-details/<int:product_id>/', VendorProductDetailsAPI.as_view(), name='vendor-product-details'),
        # Vendor Product Updates
    path('vendor/update-campaign-product/<int:product_id>/', 
         VendorUpdateCampaignProductAPI.as_view(), name='vendor-update-campaign-product'),
    
    path('vendor/update-deal-placement/<int:product_id>/', 
         UpdateDealOfDayPlacementAPI.as_view(), name='vendor-update-deal-placement'),
    
    # Deal of the Day specific
    path('vendor/set-deal-placement/<int:product_id>/', SetDealOfDayPlacementAPI.as_view(), name='set-deal-placement'),
    
    # Public URLs
    path('public/campaigns/', ActiveCampaignsAPI.as_view(), name='active-campaigns'),
    path('public/campaigns/<int:campaign_id>/products/', CampaignProductsAPI.as_view(), name='campaign-products'),
    path('public/deal-of-day/', DealOfDayProductsAPI.as_view(), name='deal-of-day-products'),
    path('public/deal-of-day/all-products/', DealOfDayAllProductsAPI.as_view(), name='deal-of-day-all-products'),
    
    # Upcoming Deals
    path('public/upcoming-deals/', UpcomingDealsCountAPI.as_view(), name='upcoming-deals'),
    
    # Vendor Daily Check
    path('vendor/daily-participation-check/<int:campaign_id>/', VendorDailyParticipationCheckAPI.as_view(), name='vendor-daily-participation-check'),

    # Debug
    path('debug/vendor-info/', debug_vendor_info, name='debug-vendor-info'),
    
        path('admin/campaigns/', CampaignListCreateAPI.as_view(), name='admin-campaigns'),
    path('admin/campaigns/<int:pk>/', CampaignDetailAPI.as_view(), name='admin-campaign-detail'),
    
    #  NEW: vendor vendor Vendor availability endpoint (works with or without campaign_id)
    path('admin/campaigns/vendors/available/', CampaignAvailableVendorsAPI.as_view(), name='global-available-vendors'),
    path('admin/campaigns/<int:campaign_id>/vendors/available/', CampaignAvailableVendorsAPI.as_view(), name='campaign-available-vendors'),
    path('admin/campaign-participations/', CampaignParticipationsListAPI.as_view(), name='admin-campaign-participations-list'),
    path('admin/campaign-participations/<int:pk>/', SuperAdminCampaignParticipationDetailAPI.as_view(), name='admin-campaign-participation-detail'),
    # Super Admin Banner Management
    path('admin/save-banner-details/', SaveBannerDetailsAPI.as_view(), name='save-banner-details'),
    path('public/deal-of-day/main-products/', DealOfDayMainProductsAPI.as_view(),name='deal-of-day-main-products'),
    path('admin/deal-of-day-products/', DealOfDayAdminProductsAPI.as_view(), name='admin-deal-of-day-products'),
]
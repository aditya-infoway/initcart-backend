# urls.py
from django.urls import path
from .views import (SliderImageUploadView,
                    SliderImageDeleteView,
                    BigAdView,
                    SmallAdView,
                    SliderImageView,
                    initBigAdView,
                    initSmallAdsView,
                    DashboardStatsAPI,
                    SuperAdminProfileAPI,
                    initAdminDetailsView,
                      CombinedBannersAPI, 
                      MobileBannerListView,
                      MobileCategoryCardAPIView,
                      MobileDealCardAPIView,  
                      MobileBannerManageView,
                      
                    )

urlpatterns = [
    path("slider/", SliderImageUploadView.as_view()),
    path("slider/<int:pk>/", SliderImageDeleteView.as_view()),
    path("big-ad/", BigAdView.as_view()),
    path("small-ad/", SmallAdView.as_view()),
    path("init-slider/", SliderImageView.as_view()),
    path("init-bigad/",initBigAdView.as_view()),
    path("init-smallads/",initSmallAdsView.as_view()),
    path("dashboard-stats/", DashboardStatsAPI.as_view()),
    path("admin-profile/", SuperAdminProfileAPI.as_view()),
    path("init-admin-footer/", initAdminDetailsView.as_view()),
    path("combined-banners/", CombinedBannersAPI.as_view(), name="combined-banners"),
    path('mobile/banners/', MobileBannerListView.as_view(), name='mobile-banners-list'),  # Public - for mobile app
    path('admin/mobile-banners/', MobileBannerManageView.as_view(), name='admin-mobile-banners-list'),  # Admin - get all
    path('admin/mobile-banners/<int:pk>/', MobileBannerManageView.as_view(), name='admin-mobile-banners-detail'), 
    path('mobile/category-cards/', MobileCategoryCardAPIView.as_view(), name='mobile-category-cards'),
    path('mobile/deal-cards/', MobileDealCardAPIView.as_view(), name='mobile-deal-cards'),

]

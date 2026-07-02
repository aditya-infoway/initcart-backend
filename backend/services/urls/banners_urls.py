from django.urls import path
from services.views.banners_views import (
    GymBigAdView, initGymBigAdView,
    initGymSmallAdsView, initSaloonBigAdView,
    initSaloonSmallAdsView, GymSmallAdView,
    SaloonBigAdView, SaloonSmallAdView,
    TravelAgencySmallAdView,TravelAgencyBigAdView,
    initTravelAgencyBigAdView, initTravelAgencySmallAdsView,
    RealEstateSmallAdView, RealEstateBigAdView,
    initRealEstateBigAdView, initRealEstateSmallAdsView,
    TechIndustryBigAdView,TechIndustrySmallAdView,
    initTechIndustryBigAdView,initTechIndustrySmallAdsView,
    ProfessionalBigAdView, initProfessionalBigAdView,
    ProfessionalSmallAdView, initProfessionalSmallAdsView,
    FinanceBigAdView, initFinanceBigAdView,
    FinanceSmallAdView, initFinanceSmallAdsView,
    HealthcareBigAdView, initHealthcareBigAdView,
    HealthcareSmallAdView, initHealthcareSmallAdsView,
    EducationBigAdView, initEducationBigAdView,
    EducationSmallAdView, initEducationSmallAdsView,
    RestaurantBigAdView, initRestaurantBigAdView,
    RestaurantSmallAdView, initRestaurantSmallAdsView,
    HotelBigAdView,initHotelBigAdView,
    HotelSmallAdView, initHotelSmallAdsView,
)
urlpatterns = [
    
    path("gym-big-ad/", GymBigAdView.as_view()),
    path("gym-small-ad/", GymSmallAdView.as_view()),
    path("init-gym-bigad/",initGymBigAdView.as_view()),
    path("init-gym-smallads/",initGymSmallAdsView.as_view()),
    path("saloon-big-ad/", SaloonBigAdView.as_view()),
    path("saloon-small-ad/", SaloonSmallAdView.as_view()),
    path("init-saloon-bigad/",initSaloonBigAdView.as_view()),
    path("init-saloon-smallads/",initSaloonSmallAdsView.as_view()),
    path("travelagency-big-ad/", TravelAgencyBigAdView.as_view()),
    path("travelagency-small-ad/", TravelAgencySmallAdView.as_view()),
    path("init-travelagency-bigad/",initTravelAgencyBigAdView.as_view()),
    path("init-travelagency-smallads/",initTravelAgencySmallAdsView.as_view()),
     path("realestate-big-ad/", RealEstateBigAdView.as_view()),
    path("realestate-small-ad/", RealEstateSmallAdView.as_view()),
    path("init-realestate-bigad/",initRealEstateBigAdView.as_view()),
    path("init-realestate-smallads/",initRealEstateSmallAdsView.as_view()),
    
    # Tech Industry Ads
    path('tech-industry-big-ad/', TechIndustryBigAdView.as_view(), name='tech-industry-big-ad'),    
    path('tech-industry-small-ad/', TechIndustrySmallAdView.as_view(), name='tech-industry-small-ad'),
    path('init-techindustry-bigad/', initTechIndustryBigAdView.as_view(), name='init-techindustry-bigad'),
    path('init-techindustry-smallads/', initTechIndustrySmallAdsView.as_view(), name='init-techindustry-smallads'),
    
    
    path("professional-big-ad/", ProfessionalBigAdView.as_view()),
    path("professional-small-ad/", ProfessionalSmallAdView.as_view()),
    path("init-professional-bigad/", initProfessionalBigAdView.as_view()),
    path("init-professional-smallads/", initProfessionalSmallAdsView.as_view()),
    
    path("finance-big-ad/", FinanceBigAdView.as_view()),
    path("finance-small-ad/", FinanceSmallAdView.as_view()),
    path("init-finance-bigad/", initFinanceBigAdView.as_view()),
    path("init-finance-smallads/", initFinanceSmallAdsView.as_view()),   
    
        # Healthcare Ads URLs
    path("healthcare-big-ad/", HealthcareBigAdView.as_view()),
    path("healthcare-small-ad/", HealthcareSmallAdView.as_view()),
    path("init-healthcare-bigad/", initHealthcareBigAdView.as_view()),
    path("init-healthcare-smallads/", initHealthcareSmallAdsView.as_view()),   
    
        # Education Ads URLs
    path("education-big-ad/", EducationBigAdView.as_view()),
    path("education-small-ad/", EducationSmallAdView.as_view()),
    path("init-education-bigad/", initEducationBigAdView.as_view()),
    path("init-education-smallads/", initEducationSmallAdsView.as_view()),
    
    path("restaurant-big-ad/", RestaurantBigAdView.as_view()),
    path("restaurant-small-ad/", RestaurantSmallAdView.as_view()),
    path("init-restaurant-bigad/", initRestaurantBigAdView.as_view()),
    path("init-restaurant-smallads/", initRestaurantSmallAdsView.as_view()),
    
    path("hotel-big-ad/", HotelBigAdView.as_view()),
    path("hotel-small-ad/", HotelSmallAdView.as_view()),
    path("init-hotel-bigad/", initHotelBigAdView.as_view()),
    path("init-hotel-smallads/", initHotelSmallAdsView.as_view()),
]
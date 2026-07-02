# services/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from services.views.real_estate_views import (
    VendorPropertyViewSet, PublicPropertyViewSet, AdminPropertyViewSet
)
from services.views.inquiry_views import (
    PublicServiceInquiryViewSet,
    VendorServiceInquiryViewSet,
    AdminServiceInquiryViewSet
)
from services.views.subcategory_views import ServiceSubcategoryViewSet
from services.views.gym_views import (
     VendorSubcategoryListAPI, 
     GymServiceListCreateView, 
     GymServiceUpdateAPIView, 
     AllGymServiceApprovalList,
     GymServiceApprovalAPIView,
     GymApprovalFilterAPI,
     PublicGymListView,
     PublicGymDetailView,
     GymApprovalStatsAPI,
     VendorApprovedServices,
     ServiceDetailBySubcategoryAPIView,
     )
from services.views.saloon_views import (
    SaloonServiceListCreateView, 
    SaloonServiceUpdateAPIView, 
    PublicSalonDetailView,
    PublicSalonListView  
)
from services.views.travel_agency_views import (
    TravelAgencyServiceListCreateView,
    TravelAgencyServiceUpdateAPIView,
    PublicTravelAgencyListView,
    PublicTravelAgencyDetailView,
)
from services.views.tech_industry_views import (
    TechIndustryServiceListCreateView,
    TechIndustryServiceUpdateAPIView,
    PublicTechIndustryListView,
    PublicTechIndustryDetailView,
)
from services.views.professional_views import (
    ProfessionalServiceListCreateView,
    ProfessionalServiceUpdateAPIView,
    PublicProfessionalListView,
    ProfessionalServiceDetailView,
    PublicProfessionalDetailView,
)
from services.views.finance_views import (
    FinanceServiceListCreateView,
    FinanceServiceDetailView,
    PublicFinanceListView,
    PublicFinanceDetailView,
    FinanceServiceApprovalAPIView,
)

from services.views.healthcare_views import (
    HealthcareServiceListCreateView,
    HealthcareServiceDetailView,
    PublicHealthcareListView,
    PublicHealthcareDetailView,
    HealthcareServiceApprovalAPIView,
)

from services.views.education_views import (
    EducationServiceListCreateView,
    EducationServiceDetailView,
    PublicEducationListView,
    PublicEducationDetailView,
    EducationServiceApprovalAPIView,
)

from services.views.restaurant_views import (
    RestaurantServiceListCreateView,
    RestaurantServiceDetailView,
    PublicRestaurantListView,
    PublicRestaurantDetailView,
    RestaurantServiceApprovalAPIView,
    RestaurantApprovalFilterAPI,
    RestaurantApprovalStatsAPI,
    RestaurantCitiesView,
)


from services.views.hotel_views import (
    HotelServiceListCreateView,
    HotelServiceDetailView,
    PublicHotelListView,
    PublicHotelDetailView,
    HotelServiceApprovalAPIView,
    HotelApprovalFilterAPI,
    HotelApprovalStatsAPI,
    HotelCitiesView,
)


router = DefaultRouter()
router.register(r'real-estate/vendor/properties', VendorPropertyViewSet, basename='vendor-property')
router.register(r'real-estate/admin/properties', AdminPropertyViewSet, basename='admin-property')
router.register(r'real-estate/public', PublicPropertyViewSet, basename='public-property')

# Service Inquiry Router
inquiry_router = DefaultRouter()
inquiry_router.register(r'public/inquiries', PublicServiceInquiryViewSet, basename='public-inquiry')
inquiry_router.register(r'vendor/inquiries', VendorServiceInquiryViewSet, basename='vendor-inquiry')
inquiry_router.register(r'admin/inquiries', AdminServiceInquiryViewSet, basename='admin-inquiry')

# NEW: Subcategory Router
subcategory_router = DefaultRouter()
subcategory_router.register(r'service-subcategories', ServiceSubcategoryViewSet, basename='service-subcategory')

# Add these URL patterns for admin
urlpatterns = [
    path('services/', include(router.urls)),
    
    # Admin specific endpoints(services)[REAL ESTATE]
    path('services/real-estate/admin/properties/pending/', 
         AdminPropertyViewSet.as_view({'get': 'pending'}), 
         name='pending-properties'),
    path('services/real-estate/admin/properties/stats/', 
         AdminPropertyViewSet.as_view({'get': 'stats'}), 
         name='admin-property-stats'),

        # Additional inquiry endpoints(INQUIRIES)
    path('services/', include(inquiry_router.urls)),   
    path('services/vendor/inquiries/dashboard/', 
         VendorServiceInquiryViewSet.as_view({'get': 'dashboard'}), 
         name='vendor-inquiry-dashboard'),
    path('services/vendor/inquiries/stats/', 
         VendorServiceInquiryViewSet.as_view({'get': 'stats'}), 
         name='vendor-inquiry-stats'),


    path('services/admin/inquiries/dashboard/', 
         AdminServiceInquiryViewSet.as_view({'get': 'dashboard'}), 
         name='admin-inquiry-dashboard'),
    path('services/admin/inquiries/vendor-stats/', 
         AdminServiceInquiryViewSet.as_view({'get': 'vendor_stats'}), 
         name='admin-vendor-inquiry-stats'),
     path('services/admin/inquiries/super-admin-list/', 
     AdminServiceInquiryViewSet.as_view({'get': 'super_admin_list'}), 
     name='admin-super-admin-inquiry-list'),
    


    path('public/inquiries/', 
         PublicServiceInquiryViewSet.as_view({'post': 'create'}), 
         name='public-inquiry-create'),
    path('public/inquiries/service_categories/', 
         PublicServiceInquiryViewSet.as_view({'get': 'service_categories'}), 
         name='service-categories'),
    path('public/inquiries/inquiry_types/', 
         PublicServiceInquiryViewSet.as_view({'get': 'inquiry_types'}), 
         name='inquiry-types'),
         # Add this new endpoint
    path('services/real-estate/public/property_types/', 
         PublicPropertyViewSet.as_view({'get': 'property_types'}), 
         name='property-types'),


       # NEW: Additional subcategory endpoints
    path('services/', include(subcategory_router.urls)), 
    path('service-subcategories/service_categories/', 
         ServiceSubcategoryViewSet.as_view({'get': 'service_categories'}), 
         name='service-categories-list'),
    path('service-subcategories/by_service/', 
         ServiceSubcategoryViewSet.as_view({'get': 'by_service'}), 
         name='subcategories-by-service'),
    #All subcategory 
    path('service-subcategories/services-type/', VendorSubcategoryListAPI.as_view()),
    
    #Gym Services urls
    path('gym-services/', GymServiceListCreateView.as_view(), name='gym-services'),
    path('gym-services/<int:pk>/', GymServiceUpdateAPIView.as_view(), name='gym-service-update'),
    
    #admin panel all services 
     path("gym-approval-list/", AllGymServiceApprovalList.as_view()),
     path("gym-service-approve/<int:pk>/", GymServiceApprovalAPIView.as_view()),
     path("gym-approval-filter/",GymApprovalFilterAPI.as_view()),
     path("gym-approval-status/", GymApprovalStatsAPI.as_view()),
     path('public/gym-service/<int:id>/', PublicGymDetailView.as_view(), name='public-gym-detail'),
     path('public/gym-services/', PublicGymListView.as_view(), name='public-gym-list'),

     #approval, reject and pandding views api for vendor panel
     path("all-services/", VendorApprovedServices.as_view()),
     path("service-detail/", ServiceDetailBySubcategoryAPIView.as_view()),
     
     #saloon Services Urls
     path('saloon-services/', SaloonServiceListCreateView.as_view()),
     path('saloon-services/<int:pk>/', SaloonServiceUpdateAPIView.as_view()),
     path('public/salon-service/<int:id>/', PublicSalonDetailView.as_view(), name='public-salon-detail'),
     # Public Salon List (for service list page)
     path('public/salon-services/', PublicSalonListView.as_view(), name='pubalic-salon-list'),
     
     #Travel Agency Services Urls
     path('travelagency-services/', TravelAgencyServiceListCreateView.as_view()),
     path('travelagency-services/<int:pk>/', TravelAgencyServiceUpdateAPIView.as_view()),
     path('public/travel-services/', PublicTravelAgencyListView.as_view(), name='public-travel-list'),
     path('public/travel-services/<int:pk>/', PublicTravelAgencyDetailView.as_view(), name='public-travel-detail'),
     
          # Tech Industry Services Urls (Vendor)
     path('tech-services/', TechIndustryServiceListCreateView.as_view()),
     path('tech-services/<int:pk>/', TechIndustryServiceUpdateAPIView.as_view()),

     # Tech Industry Public Urls
     path('public/tech-services/', PublicTechIndustryListView.as_view(), name='public-tech-list'),
     path('public/tech-service/<int:id>/', PublicTechIndustryDetailView.as_view(), name='public-tech-detail'),

    path('professional-services/', ProfessionalServiceListCreateView.as_view(), name='professional-services-list-create'),
    path('professional-services/<int:pk>/', ProfessionalServiceDetailView.as_view(), name='professional-services-detail'),  # This handles GET, PUT, DELETE
    
    # OR if you want to keep both (optional)
    # path('professional-services/<int:pk>/update/', ProfessionalServiceUpdateAPIView.as_view(), name='professional-services-update'),
 
    # Public endpoints
    path('public/professional-services/', PublicProfessionalListView.as_view(), name='public-professional-list'),
    path('public/professional-service/<int:id>/', PublicProfessionalDetailView.as_view(), name='public-professional-detail'),
    
   
    path('finance-services/', FinanceServiceListCreateView.as_view(), name='finance-services-list-create'),
    path('finance-services/<int:pk>/', FinanceServiceDetailView.as_view(), name='finance-services-detail'),

     # Finance Services - Public URLs
    path('public/finance-services/', PublicFinanceListView.as_view(), name='public-finance-list'),
    path('public/finance-service/<int:id>/', PublicFinanceDetailView.as_view(), name='public-finance-detail'),

     # Finance Services - Admin Approval URL
     path('finance-service-approve/<int:pk>/', FinanceServiceApprovalAPIView.as_view(), name='finance-service-approve'),
     
    path('healthcare-services/', HealthcareServiceListCreateView.as_view(), name='healthcare-services-list-create'),
    path('healthcare-services/<int:pk>/', HealthcareServiceDetailView.as_view(), name='healthcare-services-detail'),
    path('public/healthcare-services/', PublicHealthcareListView.as_view(), name='public-healthcare-list'),
    path('public/healthcare-service/<int:id>/', PublicHealthcareDetailView.as_view(), name='public-healthcare-detail'),
    path('healthcare-service-approve/<int:pk>/', HealthcareServiceApprovalAPIView.as_view(), name='healthcare-service-approve'),
    
         # Education Services URLs
    path('education-services/', EducationServiceListCreateView.as_view(), name='education-services-list-create'),
    path('education-services/<int:pk>/', EducationServiceDetailView.as_view(), name='education-services-detail'),
    path('public/education-services/', PublicEducationListView.as_view(), name='public-education-list'),
    path('public/education-service/<int:id>/', PublicEducationDetailView.as_view(), name='public-education-detail'),
    path('education-service-approve/<int:pk>/', EducationServiceApprovalAPIView.as_view(), name='education-service-approve'),
    
        # Restaurant Service URLs
    path('restaurant-services/', RestaurantServiceListCreateView.as_view(), name='restaurant-list-create'),
    path('restaurant-services/<int:pk>/', RestaurantServiceDetailView.as_view(), name='restaurant-detail'),
    path('public/restaurant-services/', PublicRestaurantListView.as_view(), name='public-restaurant-list'),
    path('public/restaurant-service/<int:id>/', PublicRestaurantDetailView.as_view(), name='public-restaurant-detail'),
    path('restaurant-service-approve/<int:pk>/', RestaurantServiceApprovalAPIView.as_view(), name='restaurant-approve'),
    path('restaurant-approval-filter/', RestaurantApprovalFilterAPI.as_view(), name='restaurant-approval-filter'),
    path('restaurant-approval-stats/', RestaurantApprovalStatsAPI.as_view(), name='restaurant-approval-stats'),
    path('restaurant-cities/', RestaurantCitiesView.as_view(), name='restaurant-cities'),
    
        # Hotel Service URLs
    path('hotel-services/', HotelServiceListCreateView.as_view(), name='hotel-list-create'),
    path('hotel-services/<int:pk>/', HotelServiceDetailView.as_view(), name='hotel-detail'),
    path('public/hotel-services/', PublicHotelListView.as_view(), name='public-hotel-list'),
    path('public/hotel-service/<int:id>/', PublicHotelDetailView.as_view(), name='public-hotel-detail'),
    path('hotel-service-approve/<int:pk>/', HotelServiceApprovalAPIView.as_view(), name='hotel-approve'),
    path('hotel-approval-filter/', HotelApprovalFilterAPI.as_view(), name='hotel-approval-filter'),
    path('hotel-approval-stats/', HotelApprovalStatsAPI.as_view(), name='hotel-approval-stats'),
    path('hotel-cities/', HotelCitiesView.as_view(), name='hotel-cities'),
]
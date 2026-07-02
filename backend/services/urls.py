# # services/urls.py
# from django.urls import path, include
# from rest_framework.routers import DefaultRouter
# from services.views.real_estate_views import (
#     VendorPropertyViewSet, PublicPropertyViewSet, AdminPropertyViewSet
# )
# from services.views.inquiry_views import (
#     PublicServiceInquiryViewSet,
#     VendorServiceInquiryViewSet,
#     AdminServiceInquiryViewSet
# )
# from services.views.subcategory_views import ServiceSubcategoryViewSet
# from services.views.gym_views import (
#      VendorSubcategoryListAPI, 
#      GymServiceListCreateView, 
#      GymServiceUpdateAPIView, 
#      AllGymServiceApprovalList,
#      GymServiceApprovalAPIView,
#      GymApprovalFilterAPI,
#      GymApprovalStatsAPI,
#      VendorApprovedServices,
#      CountryListAPI,CityListAPI,StateListAPI
#      )
# from services.views.saloon_views import SaloonServiceListCreateView,SaloonServiceUpdateAPIView
# from services.views.travel_agency_views import TravelAgencyServiceListCreateView,TravelAgencyServiceUpdateAPIView
# from services.views.review_views import AddServiceReview, ServiceReviewList

# router = DefaultRouter()
# router.register(r'real-estate/vendor/properties', VendorPropertyViewSet, basename='vendor-property')
# router.register(r'real-estate/admin/properties', AdminPropertyViewSet, basename='admin-property')
# router.register(r'real-estate/public', PublicPropertyViewSet, basename='public-property')

# # Service Inquiry Router
# inquiry_router = DefaultRouter()
# inquiry_router.register(r'public/inquiries', PublicServiceInquiryViewSet, basename='public-inquiry')
# inquiry_router.register(r'vendor/inquiries', VendorServiceInquiryViewSet, basename='vendor-inquiry')
# inquiry_router.register(r'admin/inquiries', AdminServiceInquiryViewSet, basename='admin-inquiry')

# # NEW: Subcategory Router
# subcategory_router = DefaultRouter()
# subcategory_router.register(r'service-subcategories', ServiceSubcategoryViewSet, basename='service-subcategory')

# # Add these URL patterns for admin
# urlpatterns = [
#     path('services/', include(router.urls)),
    
#     # Admin specific endpoints(services)[REAL ESTATE]
#     path('services/real-estate/admin/properties/pending/', 
#          AdminPropertyViewSet.as_view({'get': 'pending'}), 
#          name='pending-properties'),
#     path('services/real-estate/admin/properties/stats/', 
#          AdminPropertyViewSet.as_view({'get': 'stats'}), 
#          name='admin-property-stats'),

#         # Additional inquiry endpoints(INQUIRIES)
#     path('services/', include(inquiry_router.urls)),   
#     path('services/vendor/inquiries/dashboard/', 
#          VendorServiceInquiryViewSet.as_view({'get': 'dashboard'}), 
#          name='vendor-inquiry-dashboard'),
#     path('services/vendor/inquiries/stats/', 
#          VendorServiceInquiryViewSet.as_view({'get': 'stats'}), 
#          name='vendor-inquiry-stats'),


#     path('services/admin/inquiries/dashboard/', 
#          AdminServiceInquiryViewSet.as_view({'get': 'dashboard'}), 
#          name='admin-inquiry-dashboard'),
#     path('services/admin/inquiries/vendor-stats/', 
#          AdminServiceInquiryViewSet.as_view({'get': 'vendor_stats'}), 
#          name='admin-vendor-inquiry-stats'),
#      path('services/admin/inquiries/super-admin-list/', 
#      AdminServiceInquiryViewSet.as_view({'get': 'super_admin_list'}), 
#      name='admin-super-admin-inquiry-list'),
    


#     path('public/inquiries/', 
#          PublicServiceInquiryViewSet.as_view({'post': 'create'}), 
#          name='public-inquiry-create'),
#     path('public/inquiries/service_categories/', 
#          PublicServiceInquiryViewSet.as_view({'get': 'service_categories'}), 
#          name='service-categories'),
#     path('public/inquiries/inquiry_types/', 
#          PublicServiceInquiryViewSet.as_view({'get': 'inquiry_types'}), 
#          name='inquiry-types'),
#          # Add this new endpoint
#     path('services/real-estate/public/property_types/', 
#          PublicPropertyViewSet.as_view({'get': 'property_types'}), 
#          name='property-types'),


#        # NEW: Additional subcategory endpoints
#     path('services/', include(subcategory_router.urls)), 
#     path('service-subcategories/service_categories/', 
#          ServiceSubcategoryViewSet.as_view({'get': 'service_categories'}), 
#          name='service-categories-list'),
#     path('service-subcategories/by_service/', 
#          ServiceSubcategoryViewSet.as_view({'get': 'by_service'}), 
#          name='subcategories-by-service'),
#     #All subcategory 
#     path('service-subcategories/services-type/', VendorSubcategoryListAPI.as_view()),
    
#     #Gym Services urls
#     path('gym-services/', GymServiceListCreateView.as_view(), name='gym-services'),
#     path('gym-services/<int:pk>/', GymServiceUpdateAPIView.as_view(), name='gym-service-update'),
    
#     #admin panel all services 
#      path("gym-approval-list/", AllGymServiceApprovalList.as_view()),
#      path("gym-service-approve/<int:pk>/", GymServiceApprovalAPIView.as_view()),
#      path("gym-approval-filter/",GymApprovalFilterAPI.as_view()),
#      path("gym-approval-status/", GymApprovalStatsAPI.as_view()),

#      #approval, reject and pandding views api for vendor panel
#      path("all-services/", VendorApprovedServices.as_view()),
#      path('countries/', CountryListAPI.as_view(), name='countries-list'),
#      path('states/', StateListAPI.as_view(), name='states-list'),
#      path('cities/', CityListAPI.as_view(), name='cities-list'),\
     
#      #saloon Services Urls
#      path('saloon-services/', SaloonServiceListCreateView.as_view()),
#      path('saloon-services/<int:pk>/', SaloonServiceUpdateAPIView.as_view()),
     
#      #Travel Agency Services Urls
#      path('travelagency-services/', TravelAgencyServiceListCreateView.as_view()),
#      path('travelagency-services/<int:pk>/', TravelAgencyServiceUpdateAPIView.as_view()),
     
#      #services review Urls
#      path('add-review/', AddServiceReview.as_view()),
#      path('reviews/', ServiceReviewList.as_view()),
# ]
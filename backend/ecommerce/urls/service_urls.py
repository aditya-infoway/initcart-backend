""" from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Import all service views (You'll create these for each service)
from ecommerce.views.education_service_views import EducationServiceViewSet
# Import other service views as you create them
# from ecommerce.views.healthcare_service_views import HealthcareServiceViewSet
# from ecommerce.views.gym_service_views import GymServiceViewSet
# from ecommerce.views.salon_service_views import SalonServiceViewSet
# from ecommerce.views.real_estate_service_views import RealEstateServiceViewSet
# from ecommerce.views.travel_service_views import TravelServiceViewSet
# from ecommerce.views.finance_service_views import FinanceServiceViewSet
# from ecommerce.views.tech_service_views import TechServiceViewSet
# from ecommerce.views.hotel_service_views import HotelServiceViewSet
# from ecommerce.views.professional_service_views import ProfessionalServiceViewSet
# from ecommerce.views.workplace_service_views import WorkplaceServiceViewSet

# Create routers for each service
education_router = DefaultRouter()
education_router.register(r'education-services', EducationServiceViewSet, basename='education-services')

# Create routers for other services as you implement them
# healthcare_router = DefaultRouter()
# healthcare_router.register(r'healthcare-services', HealthcareServiceViewSet, basename='healthcare-services')

# gym_router = DefaultRouter()
# gym_router.register(r'gym-services', GymServiceViewSet, basename='gym-services')

# salon_router = DefaultRouter()
# salon_router.register(r'salon-services', SalonServiceViewSet, basename='salon-services')

# real_estate_router = DefaultRouter()
# real_estate_router.register(r'real-estate-services', RealEstateServiceViewSet, basename='real-estate-services')

# travel_router = DefaultRouter()
# travel_router.register(r'travel-services', TravelServiceViewSet, basename='travel-services')

# finance_router = DefaultRouter()
# finance_router.register(r'finance-services', FinanceServiceViewSet, basename='finance-services')

# tech_router = DefaultRouter()
# tech_router.register(r'tech-services', TechServiceViewSet, basename='tech-services')

# hotel_router = DefaultRouter()
# hotel_router.register(r'hotel-services', HotelServiceViewSet, basename='hotel-services')

# professional_router = DefaultRouter()
# professional_router.register(r'professional-services', ProfessionalServiceViewSet, basename='professional-services')

# workplace_router = DefaultRouter()
# workplace_router.register(r'workplace-services', WorkplaceServiceViewSet, basename='workplace-services')

urlpatterns = [
    # Education Service URLs
    path('education/', include(education_router.urls)),
    
    # Add other service URLs as you create them
    # path('healthcare/', include(healthcare_router.urls)),
    # path('gym/', include(gym_router.urls)),
    # path('salon/', include(salon_router.urls)),
    # path('real-estate/', include(real_estate_router.urls)),
    # path('travel/', include(travel_router.urls)),
    # path('finance/', include(finance_router.urls)),
    # path('tech/', include(tech_router.urls)),
    # path('hotel/', include(hotel_router.urls)),
    # path('professional/', include(professional_router.urls)),
    # path('workplace/', include(workplace_router.urls)),
    
    # Common service endpoints (if needed)
    path('vendor/my-services/', VendorMyServicesView.as_view(), name='vendor-all-services'),
    path('admin/pending-services/', AdminPendingServicesView.as_view(), name='admin-all-pending-services'),
]

 """

from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Import service views
from ecommerce.views.education_service_views import EducationServiceViewSet
# Import other service views as you create them

# Import common views
from ecommerce.views.service_common_views import VendorMyServicesView, AdminPendingServicesView

# Create routers for each service
education_router = DefaultRouter()
education_router.register(r'education-services', EducationServiceViewSet, basename='education-services')

# Add routers for other services as you create them
# healthcare_router = DefaultRouter()
# healthcare_router.register(r'healthcare-services', HealthcareServiceViewSet, basename='healthcare-services')
# ... etc for all 11 services

urlpatterns = [
    # Education Service URLs
    path('education/', include(education_router.urls)),
    
    # Add URLs for other services (uncomment as you create them)
    # path('healthcare/', include(healthcare_router.urls)),
    # path('gym/', include(gym_router.urls)),
    # path('salon/', include(salon_router.urls)),
    # path('real-estate/', include(real_estate_router.urls)),
    # path('travel/', include(travel_router.urls)),
    # path('finance/', include(finance_router.urls)),
    # path('tech/', include(tech_router.urls)),
    # path('hotel/', include(hotel_router.urls)),
    # path('professional/', include(professional_router.urls)),
    # path('workplace/', include(workplace_router.urls)),
    
    # Common service endpoints
    path('vendor/my-services/', VendorMyServicesView.as_view(), name='vendor-all-services'),
    path('admin/pending-services/', AdminPendingServicesView.as_view(), name='admin-all-pending-services'),
    
    # Service type endpoints
    #path('types/', ServiceTypesView.as_view(), name='service-types'),
]
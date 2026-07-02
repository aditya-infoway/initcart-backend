from django.urls import path
from services.views.public_views import (
    VendorSubcategoryListAPI,
    GymCitiesView,
    AdvancedServiceSearchAPIView,
    ApprovedServicesBySubcategory,
    MultiCategorySearchAPIView,
    SubcategoryCityAPIView,
    ServiceDetailAPIView,
    AllServicesFilterAPIView
)

urlpatterns = [
    path('service-subcategory/', VendorSubcategoryListAPI.as_view()),
    path('service-city/', GymCitiesView.as_view()),
    path('services/', ApprovedServicesBySubcategory.as_view()),
    path('services-detail/<int:pk>/<str:subcategory_id>/', ServiceDetailAPIView.as_view(), name='service-detail'),
    path('search-service/', MultiCategorySearchAPIView.as_view()),
    path('filter-service/', SubcategoryCityAPIView.as_view()),
    path('advanced-filter-service/', AdvancedServiceSearchAPIView.as_view()),
    path("subcategory-filter/", AllServicesFilterAPIView.as_view()),
]
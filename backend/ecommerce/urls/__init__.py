from django.urls import path, include

urlpatterns = [
    path('api/ecommerce/', include('ecommerce.urls.vendor_urls')),
        path('', include('ecommerce.urls.customer_urls')),
]
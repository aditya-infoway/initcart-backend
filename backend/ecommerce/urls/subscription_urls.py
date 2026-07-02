from django.urls import path
from ecommerce.views.subscription_views import (
    SubscriptionPlanListCreateAPI,
    SubscriptionPlanRetrieveUpdateDestroyAPI,
    VendorSubscriptionCheckAPI,
    ActiveSubscriptionPlansAPI,
    CreateRazorpayOrderAPI,
    VerifyPaymentAPI,
    FreeTrialAPI,
    CurrentSubscriptionAPI,
    ServiceSpecificPlansAPI,
)

urlpatterns = [
    # Admin subscription management
    path('subscriptions/', SubscriptionPlanListCreateAPI.as_view(), name='subscription-list-create'),
    path('subscriptions/<int:id>/', SubscriptionPlanRetrieveUpdateDestroyAPI.as_view(), name='subscription-detail'),
    
    # Vendor subscription endpoints
    path('vendor-subscriptions/check/', VendorSubscriptionCheckAPI.as_view(), name='vendor-subscription-check'),
    path('vendor-subscriptions/current/', CurrentSubscriptionAPI.as_view(), name='current-subscription'),
    path('active-plans/', ActiveSubscriptionPlansAPI.as_view(), name='active-plans'),
    path('create-razorpay-order/', CreateRazorpayOrderAPI.as_view(), name='create-razorpay-order'),
    path('verify-payment/', VerifyPaymentAPI.as_view(), name='verify-payment'),
    path('free-trial/', FreeTrialAPI.as_view(), name='free-trial'),
    path('service-plans/', ServiceSpecificPlansAPI.as_view(), name='service-plans'),
    

]
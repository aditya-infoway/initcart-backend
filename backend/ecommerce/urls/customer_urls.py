from django.urls import path
from ecommerce.views.customer_views import (
    CustomerRegistrationView,
    CustomerLoginView,
    CustomerLogoutView,
    CustomerProfileView,
    CustomerStatsView,
    BranchCustomerActivateView,
    ForgotPasswordView,
    ResetPasswordView,
    ChangePasswordView,
    VerifyResetTokenView,
    TestEmailView,
    ApplyForAgentView
)

urlpatterns = [
    # Authentication
    path('customer/register/', CustomerRegistrationView.as_view(), name='customer-register'),
    path('customer/login/', CustomerLoginView.as_view(), name='customer-login'),
    path('customer/logout/', CustomerLogoutView.as_view(), name='customer-logout'),
    
    # Profile
    path('customer/profile/', CustomerProfileView.as_view(), name='customer-profile'),
    path('customer/stats/', CustomerStatsView.as_view(), name='customer-stats'),
    path('customers/apply-agent/', ApplyForAgentView.as_view(), name='apply-agent'),
    
    # Password Management
    path('customer/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('customer/reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('customer/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('customer/verify-reset-token/', VerifyResetTokenView.as_view(), name='verify-reset-token'),
    
    path(
        "customer/activate-branch-customer/",
        BranchCustomerActivateView.as_view(),
        name="activate-branch-customer",
    ),
    
    # Testing
    path('customer/test-email/', TestEmailView.as_view(), name='test-email'),
]
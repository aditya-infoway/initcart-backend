from django.urls import path
from .views import LoginView, LogoutView , SuperAdminLoginView, SuperAdminChangeCredentialsView
from .views import AgentReferralLinkAPIView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path('superadmin/login/', SuperAdminLoginView.as_view(), name='superadmin-login'),
    path("logout/", LogoutView.as_view(), name="logout"),
    path('agent/referral-link/', AgentReferralLinkAPIView.as_view()),
    path("superadmin/change-credentials/", SuperAdminChangeCredentialsView.as_view()),

]
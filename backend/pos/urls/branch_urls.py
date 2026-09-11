# pos/urls/branch_urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from pos.views.branch_views import (
    BranchViewSet,
    BranchLoginViewset,
    BranchMeView,
    BranchLogoutViewset,
    BranchHeartbeatView,
    SuperadminTaxDetailsView,

)
from pos.views.franchise_branch_views import MyBranchesViewSet

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branches")
router.register(r'my-branches', MyBranchesViewSet, basename='my-branches')

urlpatterns = [
    # Authentication
    path("auth/login/", BranchLoginViewset.as_view(), name="branch-login"),
    path("auth/me/", BranchMeView.as_view(), name="branch-me"),
    path("auth/logout/", BranchLogoutViewset.as_view(), name="branch-logout"),
    path("heartbeat/", BranchHeartbeatView.as_view()),
    path("superadmin-tax-details/", SuperadminTaxDetailsView.as_view(), name='superadmin-tax-details'),
    
    # Router URLs
    path("", include(router.urls)),
]
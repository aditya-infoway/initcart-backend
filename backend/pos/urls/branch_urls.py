# pos/urls/branch_urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from pos.views.branch_views import (
    BranchViewSet,
    BranchLoginViewset,
    BranchMeView,
    BranchLogoutViewset,
    BranchHeartbeatView,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branches")

urlpatterns = [
    # Authentication
    path("auth/login/", BranchLoginViewset.as_view(), name="branch-login"),
    path("auth/me/", BranchMeView.as_view(), name="branch-me"),
    path("auth/logout/", BranchLogoutViewset.as_view(), name="branch-logout"),
    path("heartbeat/", BranchHeartbeatView.as_view()),

    
    # Router URLs
    path("", include(router.urls)),
]
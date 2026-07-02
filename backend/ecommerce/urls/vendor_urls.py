from django.urls import path, include
from rest_framework.routers import DefaultRouter
from ecommerce.views.vendor_views import (
    VendorViewSet,
    VendorApprovalViewSet,
    VendorWalletViewSet,
    VendorWithdrawalViewSet,
    BrandViewSet,
    VendorLoginViewset,
    VendorMeView,
    ServiceVendorLoginViewset,
)

router = DefaultRouter()
router.register("vendors", VendorViewSet, basename="vendors")
router.register("vendor-approvals", VendorApprovalViewSet)
router.register("vendor-wallets", VendorWalletViewSet)
router.register("vendor-withdrawals", VendorWithdrawalViewSet)
router.register("brands", BrandViewSet)

urlpatterns = [


path("auth/login/", VendorLoginViewset.as_view(), name="vendor-login"),
path("auth/service-login/", ServiceVendorLoginViewset.as_view(), name="Svendor-login"),


    
    # Router last
    path("", include(router.urls)),
    path("auth/me/", VendorMeView.as_view()),

]

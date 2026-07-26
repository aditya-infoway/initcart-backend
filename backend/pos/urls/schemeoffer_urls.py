from django.urls import path
from pos.views.schemeoffer_views import (
    SchemeOfferListCreateAPIView,
    SchemeOfferDetailAPIView,
    SchemeOfferReportAPIView,
    BranchSchemeListAPIView,
)

urlpatterns = [
    path("scheme-offers/", SchemeOfferListCreateAPIView.as_view()),
    path("scheme-offers/<int:pk>/", SchemeOfferDetailAPIView.as_view()),
    path("scheme-offers/<int:pk>/report/", SchemeOfferReportAPIView.as_view()),
    path("my-branch-schemes/", BranchSchemeListAPIView.as_view()),
]
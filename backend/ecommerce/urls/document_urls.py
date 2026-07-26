from django.urls import path
from ecommerce.views.document_views import SiteDocumentAPI, PublicSiteDocumentAPI

urlpatterns = [
    path("superadmin-documents/", SiteDocumentAPI.as_view(), name="superadmin-documents"),
    path("public-documents/", PublicSiteDocumentAPI.as_view(), name="public-documents"),
]
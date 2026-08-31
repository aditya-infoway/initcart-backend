# ecommerce/urls/qrcard_urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter

from ecommerce.views.qrcard_views import QRCardViewSet, QRCardPublicView

router = DefaultRouter()
router.register("qrcards", QRCardViewSet, basename="qrcard")

urlpatterns = [
    # public scan endpoint pehle rakho taaki router se clash na ho
    path("public/qrcards/<slug:slug>/", QRCardPublicView.as_view(), name="qrcard-public"),
]

urlpatterns += router.urls


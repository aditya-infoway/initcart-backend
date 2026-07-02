#mlm/urls/mlm_settings_urls.py
from django.urls import path
from mlm.views.mlm_settings_views import (
    MLMSettingsAPIView,
    UpdateMLMSettingsAPIView
)

urlpatterns = [

    path("settings/", MLMSettingsAPIView.as_view()),

    path("settings/update/", UpdateMLMSettingsAPIView.as_view()),

]
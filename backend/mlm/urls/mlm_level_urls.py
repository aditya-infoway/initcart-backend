from django.urls import path
from mlm.views.mlm_level_views import *

urlpatterns = [

    path("levels/", MLMLevelListCreateView.as_view()),

    path("levels/update/<int:id>/", MLMLevelUpdateView.as_view()),

    path("levels/delete/<int:id>/", MLMLevelDeleteView.as_view()),
]
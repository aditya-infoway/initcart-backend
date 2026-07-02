from django.urls import path
from pos.views.contra_views import ContraCreateView

urlpatterns = [
    # urls.py
    path("contra/", ContraCreateView.as_view()),

]

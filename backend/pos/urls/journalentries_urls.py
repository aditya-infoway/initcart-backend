from django.urls import path
from pos.views.journalentries_views import JournalCreateAPIView

urlpatterns = [
    # urls.py
    path("journal-entries/", JournalCreateAPIView.as_view()),

]

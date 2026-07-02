from django.urls import path
from services.views.review_views import AddServiceReview, ServiceReviewList, SearchServiceReviewList, ServiceReviewListAPIView, RealEstateReviewAPIView

urlpatterns = [
    #services review Urls
     path('add-review/', AddServiceReview.as_view()),
     path('reviews/', ServiceReviewList.as_view()),
     path('search-reviews/', SearchServiceReviewList.as_view()),
     path('all-review/', ServiceReviewListAPIView.as_view()),
     path("real-estate-reviews/", RealEstateReviewAPIView.as_view()),
]

from django.urls import path
from ecommerce.views.category_views import (
    CategoryListCreateAPIView, CategoryDetailAPIView,
    SubCategoryListCreateAPIView, SubCategoryDetailAPIView,
    SubSubCategoryListCreateAPIView, SubSubCategoryDetailAPIView,
     PublicCategoryListAPIView, PublicSubCategoryListAPIView, PublicSubSubCategoryListAPIView,
     FeaturedCategoryAPIView,
)

urlpatterns = [
    path("category/", CategoryListCreateAPIView.as_view()),
    path("category/<int:pk>/", CategoryDetailAPIView.as_view()),

    path("subcategory/", SubCategoryListCreateAPIView.as_view()),
    path("subcategory/<int:pk>/", SubCategoryDetailAPIView.as_view()),

    path("subsubcategory/", SubSubCategoryListCreateAPIView.as_view()),
    path("subsubcategory/<int:pk>/", SubSubCategoryDetailAPIView.as_view()),
    path("category/<int:pk>/feature/", FeaturedCategoryAPIView.as_view()),
    

        # Public APIs for vendors - ADD THESE
    path("public/categories/", PublicCategoryListAPIView.as_view(), name="public-categories"),
    path("public/subcategories/", PublicSubCategoryListAPIView.as_view(), name="public-subcategories"),
    path("public/subsubcategories/", PublicSubSubCategoryListAPIView.as_view(), name="public-subsubcategories"),

]   

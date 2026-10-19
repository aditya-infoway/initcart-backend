from django.urls import path
from ecommerce.views.category_views import (
    CategoryListCreateAPIView, CategoryDetailAPIView,
    SubCategoryListCreateAPIView, SubCategoryDetailAPIView,
    SubSubCategoryListCreateAPIView, SubSubCategoryDetailAPIView,
     PublicCategoryListAPIView, PublicSubCategoryListAPIView, PublicSubSubCategoryListAPIView,
     FeaturedCategoryAPIView, CategorySectionSettingAPIView, PublicCategorySectionSettingAPIView,
     SubCategorySectionSettingAPIView, PublicSubCategorySectionSettingAPIView
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

    path("category-section/", CategorySectionSettingAPIView.as_view()),
    path("public/category-section/", PublicCategorySectionSettingAPIView.as_view()),

    path("subcategory-section/", SubCategorySectionSettingAPIView.as_view()),
    path("public/subcategory-section/", PublicSubCategorySectionSettingAPIView.as_view()), 

]   

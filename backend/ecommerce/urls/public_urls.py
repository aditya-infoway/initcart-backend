# ecommerce/urls/public_urls.py
from django.urls import path
from ecommerce.views.public_views import (
    PublicProductListAPI, PublicProductDetailAPI,
    PublicBrandListAPI, PublicCategoryListAPI,
    PublicSubCategoryListAPI, PublicSubSubCategoryListAPI ,PublicVendorListAPI,
    CategoryProductsAPI,    PublicCouponListView,
    ValidateCouponAPIView,
    ProductCouponsAPIView,
    CartCouponsAPIView,
    VendorCouponsAPIView,
    PublicFeaturedCategoryListAPI,
    WebHomeCategoriesAPIView,
    SubCategoryProductsAPIView,
    
    ProductSearchAPIView,
    ProductSortListAPIView,
    ProductConditionFilterAPIView,
    SearchProductsAPIView,
    VendorSearchAPIView,
    available_coupons_for_product,
    )

urlpatterns = [
    path('public/products/', PublicProductListAPI.as_view(), name='public-products'),
    path('public/products/<int:pk>/', PublicProductDetailAPI.as_view(), name='public-product-detail'),
    path('public/brands/', PublicBrandListAPI.as_view(), name='public-brands'),
    path('public/categories/', PublicCategoryListAPI.as_view(), name='public-categories'),
    path('public/subcategories/', PublicSubCategoryListAPI.as_view(), name='public-subcategories'),
    path('public/subsubcategories/', PublicSubSubCategoryListAPI.as_view(), name='public-subsubcategories'),
    path('public/vendors/', PublicVendorListAPI.as_view(), name='public-vendors'),
    path('public/category-products/', CategoryProductsAPI.as_view(), name='category-products'),
    path('public/subcategory-products/', SubCategoryProductsAPIView.as_view(), name='subcategory-products'),
    path('public/web-home-categories/',  WebHomeCategoriesAPIView.as_view(), name= 'web-home-categories'),
        # Public coupon URLs
    path('public/coupons/', PublicCouponListView.as_view(), name='public-coupons-list'),
    path('public/coupons/validate/', ValidateCouponAPIView.as_view(), name='validate-coupon'),
    path('public/coupons/product/<int:product_id>/', ProductCouponsAPIView.as_view(), name='product-coupons'),
    path('public/coupons/vendor/<int:vendor_id>/', VendorCouponsAPIView.as_view(), name='vendor-coupons'),
    # Cart coupons (requires authentication)
    path('public/coupons/cart/', CartCouponsAPIView.as_view(), name='cart-coupons'),
    path('public/categories/featured/', PublicFeaturedCategoryListAPI.as_view(), name='public-featured-categories'),
    
    # Function-based endpoint for compatibility
    path('public/coupons/for-product/<int:product_id>/', available_coupons_for_product, name='coupons-for-product'),
    
    
        #Search Bar Urls
    path('public/search/', ProductSearchAPIView.as_view(), name="public-search"),
    path('public/sort/', ProductSortListAPIView.as_view(), name="public-sort"),
    path("public/products-by-condition/",ProductConditionFilterAPIView.as_view()),
    path('public/search-product/', SearchProductsAPIView.as_view(), name="public-search-product"), 
    path("public/vendors/search/", VendorSearchAPIView.as_view(), name="vendor-search"),
]
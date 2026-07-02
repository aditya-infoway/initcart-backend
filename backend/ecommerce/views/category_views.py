
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser ,  AllowAny, IsAuthenticated 
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from rest_framework import permissions

from ecommerce.models.category import Category, SubCategory, SubSubCategory
from ecommerce.serializers.category_serializers import (
    CategorySerializer, SubCategorySerializer, SubSubCategorySerializer
)

# ------------------ CATEGORY ---------------------

class CategoryListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        qs = Category.objects.all().order_by("-id")
        serializer = CategorySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "Category created", "data": serializer.data})
        return Response(serializer.errors, status=400)


class CategoryDetailAPIView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request, pk):
        obj = get_object_or_404(Category, pk=pk)
        serializer = CategorySerializer(obj, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "Category updated", "data": serializer.data})
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        obj = get_object_or_404(Category, pk=pk)
        obj.delete()
        return Response({"success": True, "message": "Category deleted"})


# ------------------ SUB CATEGORY ---------------------

class SubCategoryListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        category_id = request.query_params.get("category")
        qs = SubCategory.objects.all().order_by("-id")
        if category_id:
            qs = qs.filter(category_id=category_id)

        serializer = SubCategorySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        serializer = SubCategorySerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "SubCategory created", "data": serializer.data})
        return Response(serializer.errors, status=400)


class SubCategoryDetailAPIView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request, pk):
        obj = get_object_or_404(SubCategory, pk=pk)
        serializer = SubCategorySerializer(obj, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "SubCategory updated", "data": serializer.data})
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        obj = get_object_or_404(SubCategory, pk=pk)
        obj.delete()
        return Response({"success": True, "message": "SubCategory deleted"})


# ------------------ SUB SUB CATEGORY ---------------------

class SubSubCategoryListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        subcat_id = request.query_params.get("subcategory")
        qs = SubSubCategory.objects.all().order_by("-id")
        if subcat_id:
            qs = qs.filter(subcategory_id=subcat_id)

        serializer = SubSubCategorySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        serializer = SubSubCategorySerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "SubSubCategory created", "data": serializer.data})
        return Response(serializer.errors, status=400)


class SubSubCategoryDetailAPIView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request, pk):
        obj = get_object_or_404(SubSubCategory, pk=pk)
        serializer = SubSubCategorySerializer(obj, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "SubSubCategory updated", "data": serializer.data})
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        obj = get_object_or_404(SubSubCategory, pk=pk)
        obj.delete()
        return Response({"success": True, "message": "SubSubCategory deleted"})




# ------------------ PUBLIC CATEGORY APIS (For Vendors) ---------------------

class PublicCategoryListAPIView(APIView):
    """
    Public API for vendors to fetch categories
    """
    permission_classes = [IsAuthenticated]  # Vendor can access
    # OR use [AllowAny] if you want even without authentication
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = Category.objects.filter(status=True).order_by("name")
        serializer = CategorySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)
    
        


class PublicSubCategoryListAPIView(APIView):
    """
    Public API for vendors to fetch subcategories
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        category_id = request.query_params.get("category")
        qs = SubCategory.objects.filter(status=True)
        
        if category_id:
            qs = qs.filter(category_id=category_id)
        
        qs = qs.order_by("name")
        serializer = SubCategorySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class PublicSubSubCategoryListAPIView(APIView):
    """
    Public API for vendors to fetch sub-subcategories
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        subcategory_id = request.query_params.get("subcategory")
        qs = SubSubCategory.objects.filter(status=True)
        
        if subcategory_id:
            qs = qs.filter(subcategory_id=subcategory_id)
        
        qs = qs.order_by("name")
        serializer = SubSubCategorySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

class FeaturedCategoryAPIView(APIView):
    """
    API to mark/unmark category as featured
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        # Toggle featured status
        category.is_featured = not category.is_featured
        category.save()
        
        message = "Category marked as featured" if category.is_featured else "Category removed from featured"
        serializer = CategorySerializer(category, context={"request": request})
        
        return Response({
            "success": True,
            "message": message,
            "data": serializer.data
        })   
         

        
# ecommerce/views/product_views.py
from rest_framework import generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from django.db import transaction
from ecommerce.models.product import Product
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.product_serializers import ProductSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from ecommerce.permissions import IsVendorAuthenticated, IsAdminUser, IsSuperAdmin

class VendorAddProductAPI(generics.CreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendorAuthenticated]

    def get_serializer_context(self):
        return {"request": self.request}

    @transaction.atomic
    def perform_create(self, serializer):
        try:
            serializer.save()
        except Exception as e:
            from rest_framework import serializers
            raise serializers.ValidationError({"error": str(e)})
    permissions_classes =  [JWTAuthentication,SessionAuthentication]
class VendorProductListAPI(generics.ListAPIView):
    serializer_class = ProductSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendorAuthenticated]

    def get_queryset(self):
        vendor = Vendor.objects.filter(user=self.request.user).first()
        if not vendor:
            return Product.objects.none()
        return Product.objects.filter(vendor=vendor).order_by('-created_at')

class VendorProductUpdateDeleteAPI(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated, IsVendorAuthenticated]

    def get_queryset(self):
        vendor = Vendor.objects.filter(user=self.request.user).first()
        if not vendor:
            return Product.objects.none()
        return Product.objects.filter(vendor=vendor)

    def get_serializer_context(self):
        return {"request": self.request}

    @transaction.atomic
    def perform_update(self, serializer):
        try:
            product = self.get_object()
            
            #  NEW: If approved product is edited, set status to pending
            # This is now handled in the serializer's update method
            print(f" Updating product: {product.id} with status: {product.status}")
            
            serializer.save()
            
        except Exception as e:
            from rest_framework import serializers
            raise serializers.ValidationError({"error": str(e)})

    def perform_destroy(self, instance):
        # NEW: Allow delete for all products
        print(f" Deleting product {instance.id} with status: {instance.status}")
        instance.delete()

class AdminProductListAPI(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return Product.objects.all().order_by("-created_at")

class AdminApproveProductAPI(generics.UpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin] 
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def patch(self, request, *args, **kwargs):
        product = self.get_object()
        status_val = request.data.get("status")
        
        if status_val not in ["approved", "rejected"]:
            return Response(
                {"error": "Invalid status. Use 'approved' or 'rejected'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        product.status = status_val
        product.save()
        
        return Response({
            "message": f"Product {status_val} successfully",
            "product_id": product.id,
            "product_name": product.product_name,
            "status": product.status
        }, status=status.HTTP_200_OK)
        
        
        
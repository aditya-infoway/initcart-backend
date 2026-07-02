# services/views/professional_views.py

import json
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError

from ecommerce.models.vendor import Vendor
from services.models.professional import ProfessionalService, ProfessionalServiceImage
from services.models.subcategory import ServiceSubcategory
from services.serializers.professional_serializers import ProfessionalServiceSerializer


# -----------------------------------------------
# Vendor: List + Create
# -----------------------------------------------
class ProfessionalServiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = ProfessionalService.objects.filter(vendor=vendor)
        serializer = ProfessionalServiceSerializer(
            services, many=True, context={'request': request}
        )
        return Response(serializer.data)

    def post(self, request):
        vendor = request.user.vendor
        data = request.data

        subcategory_id = data.get("subcategory")
        if not subcategory_id:
            raise ValidationError({"subcategory": "Subcategory is required"})
        try:
            ServiceSubcategory.objects.get(id=subcategory_id)
        except ServiceSubcategory.DoesNotExist:
            raise ValidationError({"subcategory": "Invalid Subcategory ID"})

        service = ProfessionalService.objects.create(
            vendor=vendor,
            subcategory_id=subcategory_id,
            business_name=data.get('business_name'),
            address=data.get('address'),
            location=data.get('location', ''),
            country=data.get('country', ''),
            state=data.get('state', ''),
            city=data.get('city', ''),
            contact_no=data.get('contact_no'),
            whatsapp_no=data.get('whatsapp_no', ''),
            gmail_id=data.get('gmail_id', ''),
            description=data.get('description'),
            main_image=request.FILES.get('main_image'),
        )

        for img_file in request.FILES.getlist('multi_images'):
            img_instance = ProfessionalServiceImage.objects.create(image=img_file)
            service.multi_images.add(img_instance)

        serializer = ProfessionalServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=201)


# -----------------------------------------------
# Vendor: Retrieve, Update, Delete (NEW)
# -----------------------------------------------
class ProfessionalServiceDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk, vendor):
        return get_object_or_404(ProfessionalService, pk=pk, vendor=vendor)

    def get(self, request, pk):
        """Get a single professional service by ID"""
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        serializer = ProfessionalServiceSerializer(service, context={'request': request})
        return Response(serializer.data)

    def put(self, request, pk):
        """Update a professional service"""
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        data = request.data

        subcategory_id = data.get("subcategory")
        if subcategory_id:
            try:
                service.subcategory = ServiceSubcategory.objects.get(id=subcategory_id)
            except ServiceSubcategory.DoesNotExist:
                raise ValidationError({"subcategory": "Invalid Subcategory ID"})

        service.business_name = data.get("business_name", service.business_name)
        service.address = data.get("address", service.address)
        service.location = data.get("location", service.location)
        service.country = data.get("country", service.country)
        service.state = data.get("state", service.state)
        service.city = data.get("city", service.city)
        service.contact_no = data.get("contact_no", service.contact_no)
        service.whatsapp_no = data.get("whatsapp_no", service.whatsapp_no)
        service.gmail_id = data.get("gmail_id", service.gmail_id)
        service.description = data.get("description", service.description)

        if "main_image" in request.FILES:
            service.main_image = request.FILES["main_image"]

        service.save()

        # Handle multi images - only if new ones are uploaded
        if request.FILES.getlist("multi_images"):
            # Optional: Remove old images if you want to replace
            # service.multi_images.all().delete()
            for img in request.FILES.getlist("multi_images"):
                img_instance = ProfessionalServiceImage.objects.create(image=img)
                service.multi_images.add(img_instance)

        serializer = ProfessionalServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=200)

    def delete(self, request, pk):
        """Delete a professional service"""
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        
        # Delete associated images from storage
        if service.main_image:
            service.main_image.delete(save=False)
        
        # Delete multi images
        for img in service.multi_images.all():
            img.image.delete(save=False)
            img.delete()
        
        service.delete()
        return Response({"message": "Service deleted successfully"}, status=status.HTTP_204_NO_CONTENT)


# -----------------------------------------------
# Vendor: Update (OLD - Can be removed or kept for backward compatibility)
# -----------------------------------------------
class ProfessionalServiceUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk, vendor):
        return get_object_or_404(ProfessionalService, pk=pk, vendor=vendor)

    def put(self, request, pk):
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        data = request.data

        subcategory_id = data.get("subcategory")
        if subcategory_id:
            try:
                service.subcategory = ServiceSubcategory.objects.get(id=subcategory_id)
            except ServiceSubcategory.DoesNotExist:
                raise ValidationError({"subcategory": "Invalid Subcategory ID"})

        service.business_name = data.get("business_name", service.business_name)
        service.address = data.get("address", service.address)
        service.location = data.get("location", service.location)
        service.country = data.get("country", service.country)
        service.state = data.get("state", service.state)
        service.city = data.get("city", service.city)
        service.contact_no = data.get("contact_no", service.contact_no)
        service.whatsapp_no = data.get("whatsapp_no", service.whatsapp_no)
        service.gmail_id = data.get("gmail_id", service.gmail_id)
        service.description = data.get("description", service.description)

        if "main_image" in request.FILES:
            service.main_image = request.FILES["main_image"]

        service.save()

        if request.FILES.getlist("multi_images"):
            # Remove old and add new
            service.multi_images.all().delete()
            for img in request.FILES.getlist("multi_images"):
                img_instance = ProfessionalServiceImage.objects.create(image=img)
                service.multi_images.add(img_instance)

        serializer = ProfessionalServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=200)


# -----------------------------------------------
# Public: List (approved only)
# -----------------------------------------------
class PublicProfessionalListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProfessionalServiceSerializer

    def get_queryset(self):
        qs = ProfessionalService.objects.filter(status='approved', subcategory__status='Active')
        subcategory = self.request.query_params.get('subcategory')
        city = self.request.query_params.get('city')
        if subcategory:
            qs = qs.filter(subcategory__subcategory_name__icontains=subcategory)
        if city:
            qs = qs.filter(city__icontains=city)
        return qs.order_by('-created_at')


# -----------------------------------------------
# Public: Detail (approved only)
# -----------------------------------------------
class PublicProfessionalDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, id):
        try:
            service = ProfessionalService.objects.get(id=id, status='approved', subcategory__status='Active')
            serializer = ProfessionalServiceSerializer(service, context={'request': request})
            return Response(serializer.data)
        except ProfessionalService.DoesNotExist:
            return Response({"error": "Service not found"}, status=404)
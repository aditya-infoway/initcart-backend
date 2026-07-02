from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ecommerce.models.vendor import Vendor
from services.models.tech_industry import TechIndustryService, TechIndustryItem, TechIndustryImage
from services.serializers.tech_industry_serializers import TechIndustryServiceSerializer
import json
from services.models.subcategory import ServiceSubcategory


def parse_fk(value):
    if value in [None, "", "undefined", "null"]:
        return None
    if isinstance(value, dict) and "id" in value:
        value = value["id"]
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


# -------------------------------
# Create & List Tech Industry Services
# -------------------------------
class TechIndustryServiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = TechIndustryService.objects.filter(vendor=vendor)
        serializer = TechIndustryServiceSerializer(services, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        vendor = request.user.vendor
        data = request.data.copy()
        items_data = json.loads(data.get('items', '[]'))
        multi_images_files = request.FILES.getlist('multi_images')

        subcategory_id = request.data.get("subcategory")

        if not subcategory_id:
            raise ValidationError({"subcategory": "Subcategory ID is required"})

        try:
            ServiceSubcategory.objects.get(id=subcategory_id)
        except ServiceSubcategory.DoesNotExist:
            raise ValidationError({"subcategory": "Invalid Subcategory ID"})

        tech_service = TechIndustryService.objects.create(
            vendor=vendor,
            subcategory_id=subcategory_id,
            business_name=data.get('business_name'),
            address=data.get('address'),
            location=data.get('location'),
            country=data.get('country'),
            state=data.get('state'),
            city=data.get('city'),
            open_time=data.get('open_time'),
            close_time=data.get('close_time'),
            contact_no=data.get('contact_no'),
            whatsapp_no=data.get('whatsapp_no'),
            description=data.get('description'),
            main_image=request.FILES.get('main_image'),
            second_image=request.FILES.get('second_image'),
        )

        for item in items_data:
            TechIndustryItem.objects.create(
                service=tech_service,
                name=item.get('name', ''),
                description=item.get('description', ''),
                price=item.get('price', 0),
            )

        for img_file in multi_images_files:
            img_instance = TechIndustryImage.objects.create(image=img_file)
            tech_service.multi_images.add(img_instance)

        serializer = TechIndustryServiceSerializer(tech_service, context={'request': request})
        return Response(serializer.data, status=201)


# -------------------------------
# Update Tech Industry Service
# -------------------------------
class TechIndustryServiceUpdateAPIView(generics.RetrieveUpdateAPIView):
    queryset = TechIndustryService.objects.all()
    serializer_class = TechIndustryServiceSerializer
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request, *args, **kwargs):
        service = self.get_object()
        data = request.data

        subcategory_id = request.data.get("subcategory")
        if subcategory_id:
            try:
                subcategory = ServiceSubcategory.objects.get(id=subcategory_id)
                service.subcategory = subcategory
            except ServiceSubcategory.DoesNotExist:
                raise ValidationError({"subcategory": "Invalid Subcategory ID"})

        service.business_name = data.get("business_name", service.business_name)
        service.country = data.get("country", service.country)
        service.state = data.get("state", service.state)
        service.city = data.get("city", service.city)
        service.address = data.get("address", service.address)
        service.location = data.get("location", service.location)
        service.open_time = data.get("open_time", service.open_time)
        service.close_time = data.get("close_time", service.close_time)
        service.contact_no = data.get("contact_no", service.contact_no)
        service.whatsapp_no = data.get("whatsapp_no", service.whatsapp_no)
        service.description = data.get("description", service.description)

        if "main_image" in request.FILES:
            service.main_image = request.FILES["main_image"]
        if "second_image" in request.FILES:
            service.second_image = request.FILES["second_image"]

        service.save()

        if "multi_images" in request.FILES:
            TechIndustryImage.objects.filter(techindustryservice=service).delete()
            for img in request.FILES.getlist("multi_images"):
                TechIndustryImage.objects.create(techindustryservice=service, image=img)

        items_data = data.get("items")
        if items_data:
            items_list = json.loads(items_data)
            TechIndustryItem.objects.filter(service=service).delete()
            for item in items_list:
                TechIndustryItem.objects.create(
                    service=service,
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    price=item.get("price", 0)
                )

        serializer = self.get_serializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# -------------------------------
# Public List View
# -------------------------------
class PublicTechIndustryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TechIndustryServiceSerializer
    
    def get_queryset(self):
        queryset = TechIndustryService.objects.filter(status='approved', subcategory__status='Active')
        
        subcategory = self.request.query_params.get('subcategory', None)
        if subcategory:
            queryset = queryset.filter(subcategory__subcategory_name__icontains=subcategory)
        
        city = self.request.query_params.get('city', None)
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        return queryset.order_by('-created_at')


# -------------------------------
# Public Detail View
# -------------------------------
class PublicTechIndustryDetailView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request, id):
        try:
            service = TechIndustryService.objects.get(id=id, status='approved', subcategory__status='Active')
            serializer = TechIndustryServiceSerializer(service, context={'request': request})
            return Response(serializer.data)
        except TechIndustryService.DoesNotExist:
            return Response({"error": "Service not found"}, status=404)
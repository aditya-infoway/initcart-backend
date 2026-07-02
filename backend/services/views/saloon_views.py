from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from ecommerce.models.vendor import Vendor
from services.models.saloon import SaloonService, SaloonItem, SaloonImage
from services.serializers.saloon_serializers import SaloonServiceSerializer
import json
from services.models.subcategory import ServiceSubcategory
# from services.models.gym import Country, State, City


# services/views.py
# -------------------------------
# Helper for FK parsing
# -------------------------------
def parse_fk(value):
    """
    Safely parse ForeignKey values from frontend:
    - Returns None if value is None, empty, 'undefined', or 'null'
    - Returns int(value) if numeric
    - Handles dict like {"id": 3, "name": "..."} as well
    """
    if value in [None, "", "undefined", "null"]:
        return None
    if isinstance(value, dict) and "id" in value:
        value = value["id"]
    try:
        return int(value)
    except (ValueError, TypeError):
        return None




def update_fk_field(instance, field_name, model, value):
    """
    Update FK only if valid ID is provided.
    Ignore if None / empty string / 'null'
    """
    if value in [None, "", "null", "undefined"]:
        return   # ❌ Do NOT update, keep old value

    try:
        obj = model.objects.get(id=value)
        setattr(instance, field_name, obj)
    except model.DoesNotExist:
        raise ValidationError({
            field_name: f"Invalid {field_name} ID"
        })


# -------------------------------
# Create & List Gym Services
# -------------------------------
class SaloonServiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = SaloonService.objects.filter(vendor=vendor)
        serializer = SaloonServiceSerializer(services, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        print("SUBCATEGORY FROM FRONTEND =", request.data.get("subcategory"))
        print("TYPE =", type(request.data.get("subcategory")))
        vendor = request.user.vendor
        data = request.data.copy()
        items_data = json.loads(data.get('items', '[]'))
        multi_images_files = request.FILES.getlist('multi_images')

        # -------------------------------
        # Parse ForeignKeys
        # -------------------------------
        country_id = parse_fk(data.get("country"))
        state_id = parse_fk(data.get("state"))
        city_id = parse_fk(data.get("city"))  
        # subcategory_id = parse_fk(data.get("subcategory"))
        # subcategory = get_object_or_404(ServiceSubcategory, id=subcategory_id) if subcategory_id else None
        subcategory_id = request.data.get("subcategory")

        if not subcategory_id:
            raise ValidationError({
                "subcategory": "Subcategory ID is required"
            })

        # Optional but safe validation
        try:
            ServiceSubcategory.objects.get(id=subcategory_id)
        except ServiceSubcategory.DoesNotExist:
            raise ValidationError({
                "subcategory": "Invalid Subcategory ID"
            })


        # country = get_object_or_404(Country, id=country_id) if country_id else None
        # state = get_object_or_404(State, id=state_id) if state_id else None
        # city = get_object_or_404(City, id=city_id) if city_id else None
       
        # -------------------------------
        # Create GymService
        # -------------------------------
        Saloon_service = SaloonService.objects.create(
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

        # -------------------------------
        # Service Items
        # -------------------------------
        for item in items_data:
            SaloonItem.objects.create(
                service=Saloon_service,
                name=item.get('name', ''),
                description=item.get('description', ''),
                price=item.get('price', 0),
            )

        # -------------------------------
        # Multi Images
        # -------------------------------
        for img_file in multi_images_files:
            img_instance = SaloonImage.objects.create(
                image=img_file
            )
            Saloon_service.multi_images.add(img_instance)

        serializer = SaloonServiceSerializer(Saloon_service, context={'request': request})
        return Response(serializer.data, status=201)


# -------------------------------
# Update GymService
# -------------------------------
class SaloonServiceUpdateAPIView(generics.RetrieveUpdateAPIView):
    queryset = SaloonService.objects.all()
    serializer_class = SaloonServiceSerializer
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request, *args, **kwargs):
        service = self.get_object()
        data = request.data

        # -------------------------------
        # Update ForeignKeys safely
        # -------------------------------
        subcategory_id = request.data.get("subcategory")

        if subcategory_id:
            try:
                subcategory = ServiceSubcategory.objects.get(id=subcategory_id)
                service.subcategory = subcategory
            except ServiceSubcategory.DoesNotExist:
                raise ValidationError({
                    "subcategory": "Invalid Subcategory ID"
                })
        # update_fk_field(service, "country", Country, data.get("country"))
        # update_fk_field(service, "state", State, data.get("state"))
        # update_fk_field(service, "city", City, data.get("city"))

        # -------------------------------
        # Update simple fields
        # -------------------------------
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
        # -------------------------------
        # Update images
        # -------------------------------
        if "main_image" in request.FILES:
            service.main_image = request.FILES["main_image"]
        if "second_image" in request.FILES:
            service.second_image = request.FILES["second_image"]

        service.save()

        # -------------------------------
        # Update multi images
        # -------------------------------
        if "multi_images" in request.FILES:
            SaloonImage.objects.filter(saloonservice=service).delete()
            for img in request.FILES.getlist("multi_images"):
                SaloonImage.objects.create(saloonservice=service, image=img)

        # -------------------------------
        # Update Service Items
        # -------------------------------
        items_data = data.get("items")
        if items_data:
            items_list = json.loads(items_data)
            SaloonItem.objects.filter(service=service).delete()
            for item in items_list:
                SaloonItem.objects.create(
                    service=service,
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    price=item.get("price", 0)
                )

        serializer = self.get_serializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
       
    
from rest_framework.permissions import AllowAny

# Add this class at the bottom of the file
class PublicSalonDetailView(APIView):
    """Public endpoint for viewing approved salon services"""
    permission_classes = [AllowAny]
    
    def get(self, request, id):
        try:
            service = SaloonService.objects.get(id=id, status='approved', is_active=True, subcategory__status='Active')
            serializer = SaloonServiceSerializer(service, context={'request': request})
            return Response(serializer.data)
        except SaloonService.DoesNotExist:
            return Response({"error": "Service not found"}, status=404)   
        
        
from rest_framework.permissions import AllowAny
from rest_framework import generics

class PublicSalonListView(generics.ListAPIView):
    """Public endpoint for listing approved salon services"""
    permission_classes = [AllowAny]
    serializer_class = SaloonServiceSerializer
    
    def get_queryset(self):
        queryset = SaloonService.objects.filter(status='approved', is_active=True, subcategory__status='Active')
        
        # Filter by subcategory name if provided
        subcategory = self.request.query_params.get('subcategory', None)
        if subcategory:
            queryset = queryset.filter(subcategory__subcategory_name__icontains=subcategory)
        
        # Filter by city
        city = self.request.query_params.get('city', None)
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        # Search
        search = self.request.query_params.get('search', None)
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(business_name__icontains=search) |
                Q(description__icontains=search) |
                Q(address__icontains=search) |
                Q(city__icontains=search)
            )
        
        return queryset.order_by('-created_at')         
        
        
        
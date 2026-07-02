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
from services.models.travel_agency import TravelAgencyService, TravelAgencyItem, TravelAgencyImage
from services.serializers.travel_agency_serializers import TravelAgencyServiceSerializer
import json
from services.models.subcategory import ServiceSubcategory
from rest_framework.permissions import AllowAny
from rest_framework import generics


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
class TravelAgencyServiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = TravelAgencyService.objects.filter(vendor=vendor)
        serializer = TravelAgencyServiceSerializer(services, many=True, context={'request': request})
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
       
        # -------------------------------
        # Create GymService
        # -------------------------------
        TravelAgency_service = TravelAgencyService.objects.create(
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
            TravelAgencyItem.objects.create(
                service=TravelAgency_service,
                name=item.get('name', ''),
                description=item.get('description', ''),
                price=item.get('price', 0),
            )

        # -------------------------------
        # Multi Images
        # -------------------------------
        for img_file in multi_images_files:
            img_instance = TravelAgencyImage.objects.create(
                image=img_file
            )
            TravelAgency_service.multi_images.add(img_instance)

        serializer = TravelAgencyServiceSerializer(TravelAgency_service, context={'request': request})
        return Response(serializer.data, status=201)


# -------------------------------
# Update GymService
# -------------------------------
class TravelAgencyServiceUpdateAPIView(generics.RetrieveUpdateAPIView):
    queryset = TravelAgencyService.objects.all()
    serializer_class = TravelAgencyServiceSerializer
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
            TravelAgencyImage.objects.filter(service=service).delete()
            for img in request.FILES.getlist("multi_images"):
                TravelAgencyImage.objects.create(service=service, image=img)

        # -------------------------------
        # Update Service Items
        # -------------------------------
        items_data = data.get("items")
        if items_data:
            items_list = json.loads(items_data)
            TravelAgencyItem.objects.filter(service=service).delete()
            for item in items_list:
                TravelAgencyItem.objects.create(
                    service=service,
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    price=item.get("price", 0)
                )

        serializer = self.get_serializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class PublicTravelAgencyListView(generics.ListAPIView):
    """Public endpoint for listing approved travel agency services"""
    permission_classes = [AllowAny]
    serializer_class = TravelAgencyServiceSerializer
    
    def get_queryset(self):
        queryset = TravelAgencyService.objects.filter(status='approved',subcategory__status='Active')
        
        subcategory = self.request.query_params.get('subcategory', None)
        if subcategory:
            queryset = queryset.filter(subcategory__subcategory_name__icontains=subcategory)
        
        city = self.request.query_params.get('city', None)
        if city:
            queryset = queryset.filter(city__icontains=city)
        
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
    
# services/views/travel_agency_views.py

class PublicTravelAgencyDetailView(generics.RetrieveAPIView):
    """Public endpoint for viewing a single travel agency service detail"""
    permission_classes = [AllowAny]
    serializer_class = TravelAgencyServiceSerializer
    queryset = TravelAgencyService.objects.filter(status='approved', subcategory__status='Active')
    lookup_field = 'pk'
    
    def get_object(self):
        """Get service by ID, ensuring it's approved"""
        pk = self.kwargs.get('pk')
        try:
            service = TravelAgencyService.objects.get(pk=pk, status='approved')
            return service
        except TravelAgencyService.DoesNotExist:
            raise ValidationError("Service not found or not yet approved")    
    
    

    
     

# services/views/gym_views.py

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
from services.serializers.saloon_serializers import SaloonServiceSerializer
from services.models.gym import GymService, ServiceItem, ServiceImage
from services.models.saloon import SaloonService
from services.serializers.gym_serializers import GymServiceSerializer
import json
from services.models.subcategory import ServiceSubcategory
from services.serializers.subcategory_serializers import ServiceSubcategorySerializer
from services.serializers.travel_agency_serializers import TravelAgencyServiceSerializer
from services.models.travel_agency import TravelAgencyService
from services.models.tech_industry import TechIndustryService
from services.serializers.tech_industry_serializers import TechIndustryServiceSerializer
from services.models.professional import ProfessionalService
from services.serializers.professional_serializers import ProfessionalServiceSerializer
from services.models.finance import FinanceService
from services.serializers.finance_serializers import FinanceServiceSerializer
from services.models.healthcare import HealthcareService
from services.serializers.healthcare_serializers import HealthcareServiceSerializer
from services.models.education import EducationNewService
from services.serializers.education_serializers import EducationNewServiceSerializer
from services.models.restaurant import RestaurantService
from services.serializers.restaurant_serialisers import RestaurantServiceSerializer
from services.models.hotel import HotelService
from services.serializers.hotel_serializers import HotelServiceSerializer

class VendorSubcategoryListAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vendor = request.user.vendor
        vendor_service = vendor.service_type

        subcategories = [
            sub for sub in ServiceSubcategory.objects.filter(status="Active")
            if sub.service_type == vendor_service
        ]

        serializer = ServiceSubcategorySerializer(subcategories, many=True)
        return Response(serializer.data)


def parse_fk(value):
    if value in [None, "", "undefined", "null"]:
        return None
    if isinstance(value, dict) and "id" in value:
        value = value["id"]
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def update_fk_field(instance, field_name, model, value):
    if value in [None, "", "null", "undefined"]:
        return
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
class GymServiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = GymService.objects.filter(vendor=vendor)
        serializer = GymServiceSerializer(services, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        print("SUBCATEGORY FROM FRONTEND =", request.data.get("subcategory"))
        print("TYPE =", type(request.data.get("subcategory")))
        vendor = request.user.vendor
        data = request.data.copy()
        items_data = json.loads(data.get('items', '[]'))
        multi_images_files = request.FILES.getlist('multi_images')

        subcategory_id = request.data.get("subcategory")

        if not subcategory_id:
            raise ValidationError({
                "subcategory": "Subcategory ID is required"
            })

        try:
            ServiceSubcategory.objects.get(id=subcategory_id)
        except ServiceSubcategory.DoesNotExist:
            raise ValidationError({
                "subcategory": "Invalid Subcategory ID"
            })

        gym_service = GymService.objects.create(
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
            ServiceItem.objects.create(
                service=gym_service,
                name=item.get('name', ''),
                description=item.get('description', ''),
                price=item.get('price', 0),
            )

        for img_file in multi_images_files:
            img_instance = ServiceImage.objects.create(image=img_file)
            gym_service.multi_images.add(img_instance)

        serializer = GymServiceSerializer(gym_service, context={'request': request})
        return Response(serializer.data, status=201)


# -------------------------------
# Update GymService
# -------------------------------
class GymServiceUpdateAPIView(generics.RetrieveUpdateAPIView):
    queryset = GymService.objects.all()
    serializer_class = GymServiceSerializer
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
                raise ValidationError({
                    "subcategory": "Invalid Subcategory ID"
                })

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
            ServiceImage.objects.filter(gymservice=service).delete()
            for img in request.FILES.getlist("multi_images"):
                ServiceImage.objects.create(gymservice=service, image=img)

        items_data = data.get("items")
        if items_data:
            items_list = json.loads(items_data)
            ServiceItem.objects.filter(service=service).delete()
            for item in items_list:
                ServiceItem.objects.create(
                    service=service,
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    price=item.get("price", 0)
                )

        serializer = self.get_serializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# -------------------------------
# Admin Approval List - Includes ALL services
# -------------------------------
class AllGymServiceApprovalList(APIView):
    """
    Admin API: List all vendor services with optional category filter.
    Includes: Gym, Salon, Travel Agency, Tech Industry, Professional Services
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        category = request.query_params.get("category")
        services_list = []

        # Dictionary mapping category → (Model, Serializer)
        vendor_mapping = {
            "gym": (GymService, GymServiceSerializer),
            "salon": (SaloonService, SaloonServiceSerializer),
            "travel_agency": (TravelAgencyService, TravelAgencyServiceSerializer),
            "tech_industry": (TechIndustryService, TechIndustryServiceSerializer),
            "professional": (ProfessionalService, ProfessionalServiceSerializer),  # Added
            "finance": (FinanceService, FinanceServiceSerializer),
            "healthcare":(HealthcareService,HealthcareServiceSerializer),
            "education": (EducationNewService, EducationNewServiceSerializer), 
            "restaurant": (RestaurantService, RestaurantServiceSerializer), 
            "hotel" : (HotelService, HotelServiceSerializer),
        }

        if category:
            mapping = vendor_mapping.get(category.lower())
            if mapping:
                Model, Serializer = mapping
                qs = Model.objects.all().order_by("-id")
                services_list = Serializer(qs, many=True, context={'request': request}).data
                for s in services_list:
                    s["type"] = category.lower()
        else:
            combined = []
            for cat, (Model, Serializer) in vendor_mapping.items():
                qs = Model.objects.all().order_by("-id")
                serialized = Serializer(qs, many=True, context={'request': request}).data
                for s in serialized:
                    s["type"] = cat
                combined += serialized
            services_list = combined

        return Response(services_list)


# VENDOR_MODELS for approval status update
VENDOR_MODELS = {
    GymService, 
    SaloonService, 
    TravelAgencyService, 
    TechIndustryService,
    ProfessionalService,  # Added
    FinanceService,
    HealthcareService,
    EducationNewService,
    RestaurantService,
    HotelService,
}


class GymServiceApprovalAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        status_value = request.data.get("status")
        subcategory_id = request.data.get("subcategory")

        if status_value not in ["approved", "rejected"]:
            return Response({"error": "Invalid status"}, status=400)

        if not subcategory_id:
            return Response({"error": "subcategory_id is required"}, status=400)

        service = None
        vendor_type = None

        for Model in VENDOR_MODELS:
            try:
                service = Model.objects.get(
                    id=pk,
                    subcategory_id=subcategory_id
                )
                vendor_type = Model.__name__
                break
            except Model.DoesNotExist:
                continue

        if not service:
            return Response({
                "error": "Service not found with matching subcategory"
            }, status=404)

        service.status = status_value
        service.approved_by = request.user
        service.approved_date = (
            timezone.now() if status_value == "approved" else None
        )
        service.save()

        return Response({
            "message": f"{vendor_type} status updated successfully",
            "status": service.status,
            "approved_by": service.approved_by.id if service.approved_by else None
        })


# VENDOR_FILTER_MODELS for filter API
VENDOR_FILTER_MODELS = {
    "gym": (GymService, GymServiceSerializer),
    "salon": (SaloonService, SaloonServiceSerializer),
    "travel_agency": (TravelAgencyService, TravelAgencyServiceSerializer),
    "tech_industry": (TechIndustryService, TechIndustryServiceSerializer),
    "professional": (ProfessionalService, ProfessionalServiceSerializer),  # Added
    "finance" : (FinanceService, FinanceServiceSerializer),
    "healthcare" : (HealthcareService,HealthcareServiceSerializer),
    "education": (EducationNewService, EducationNewServiceSerializer),  
    "restaurant": (RestaurantService, RestaurantServiceSerializer),
    "hotel" : (HotelService, HotelServiceSerializer),
}


class GymApprovalFilterAPI(APIView):
    """
    Generic filter API for admin: category + status filters
    Includes all service types — newest first (created_at desc)
    """
 
    def get(self, request):
        category_filter = request.GET.get("category")
        status_filter = request.GET.get("status")
 
        services_list = []
 
        if category_filter and category_filter.lower() in VENDOR_FILTER_MODELS:
            Model, Serializer = VENDOR_FILTER_MODELS[category_filter.lower()]
            qs = Model.objects.select_related("vendor").all().order_by("-created_at")
            if status_filter and status_filter != "all":
                qs = qs.filter(status=status_filter)
            services_list = Serializer(qs, many=True, context={"request": request}).data
            for s in services_list:
                s["type"] = category_filter.lower()
        else:
            for vendor_type, (Model, Serializer) in VENDOR_FILTER_MODELS.items():
                qs = Model.objects.select_related("vendor").all().order_by("-created_at")
                if status_filter and status_filter != "all":
                    qs = qs.filter(status=status_filter)
                serialized = Serializer(qs, many=True, context={"request": request}).data
                for s in serialized:
                    s["type"] = vendor_type
                    if not s.get("business_name"):
                        s["business_name"] = s.get("restaurant_name") or s.get("hotel_name") or "—"
                services_list += serialized
 
            # "All categories" mode me bhi newest first chahiye
            # isliye combined list ko bhi created_at se sort karo
            services_list.sort(
                key=lambda x: x.get("created_at") or "",
                reverse=True
            )
 
        return Response(services_list)


class GymApprovalStatsAPI(APIView):
    def get(self, request):
        SERVICE_MODEL_MAP = {
            "gym": GymService,
            "salon": SaloonService,
            "travel_agency": TravelAgencyService,
            "tech_industry": TechIndustryService,
            "professional": ProfessionalService,  # Added
            "finance" : FinanceService,
            "healthcare" : HealthcareService,
            "education" : EducationNewService,
            "restaurant" : RestaurantService,
            "hotel" : HotelService,
        }

        final_data = {}

        for subtype, service_model in SERVICE_MODEL_MAP.items():
            vendors = Vendor.objects.filter(vendor_subtype__icontains=subtype)
            total_vendor = vendors.count()

            approved = service_model.objects.filter(
                vendor__in=vendors,
                status__iexact="approved"
            ).count()

            rejected = service_model.objects.filter(
                vendor__in=vendors,
                status__iexact="rejected"
            ).count()

            pending = service_model.objects.filter(
                vendor__in=vendors,
                status__iexact="pending"
            ).count()

            final_data[subtype] = {
                "total_vendor": total_vendor,
                "approved": approved,
                "pending": pending,
                "rejected": rejected
            }

        return Response({
            "status": True,
            "data": final_data
        })


class VendorApprovedServices(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vendor = get_object_or_404(Vendor, user=request.user)
        category = request.query_params.get("category")

        if category == "gym":
            services = GymService.objects.filter(vendor=vendor)
            serializer = GymServiceSerializer(services, many=True)
            return Response(serializer.data)
        elif category == "salon":
            services = SaloonService.objects.filter(vendor=vendor)
            serializer = SaloonServiceSerializer(services, many=True)
            return Response(serializer.data)
        elif category == "tech_industry":
            services = TechIndustryService.objects.filter(vendor=vendor)
            serializer = TechIndustryServiceSerializer(services, many=True)
            return Response(serializer.data)
        elif category == "travel_agency":
            services = TravelAgencyService.objects.filter(vendor=vendor)
            serializer = TravelAgencyServiceSerializer(services, many=True)
            return Response(serializer.data)
        elif category == "professional":
            services = ProfessionalService.objects.filter(vendor=vendor)
            serializer = ProfessionalServiceSerializer(services, many=True)
            return Response(serializer.data)
        elif category == "finance":
            services = FinanceService.objects.filter(vendor=vendor)
            serializer = FinanceServiceSerializer(services, many=True)
            return Response(serializer.data)
        elif category == "healthcare":
            services = HealthcareService.objects.filter(vendor=vendor)
            serializer = HealthcareServiceSerializer(services, many=True)
            return Response(serializer.data)
        elif category == "education":
            services = EducationNewService.objects.filter(vendor=vendor)
            serializer = EducationNewServiceSerializer(services, many=True)
            return Response(serializer.data)    
        elif category == "hotel":
            services =HotelService.objects.filter(vendor=vendor)
            serializer = HotelServiceSerializer(services, many=True)
            return Response(serializer.data)     
        else:
            gym_services = GymService.objects.filter(vendor=vendor)
            salon_services = SaloonService.objects.filter(vendor=vendor)
            travel_agency_services = TravelAgencyService.objects.filter(vendor=vendor)
            tech_services = TechIndustryService.objects.filter(vendor=vendor)
            professional_services = ProfessionalService.objects.filter(vendor=vendor)
            finance_services = FinanceService.objects.filter(vendor=vendor)
            healthcare_services = HealthcareService.objects.filter(vendor=vendor)
            education_services = EducationNewService.objects.filter(vendor=vendor)
            restaurant_services = RestaurantService.objects.filter(vendor=vendor)
            hotel_services = RestaurantService.objects.filter(vendor=vendor)
            
            combined_services = (
                list(GymServiceSerializer(gym_services, many=True).data) +
                list(SaloonServiceSerializer(salon_services, many=True).data) +
                list(TravelAgencyServiceSerializer(travel_agency_services, many=True).data) +
                list(TechIndustryServiceSerializer(tech_services, many=True).data) +
                list(ProfessionalServiceSerializer(professional_services, many=True).data)+
                list(FinanceServiceSerializer(finance_services, many=True).data)+
                list(HealthcareServiceSerializer(healthcare_services, many=True).data)+
                list(EducationNewServiceSerializer(education_services, many=True).data)+
                list(RestaurantServiceSerializer(restaurant_services, many=True).data)+
                list(HotelServiceSerializer(hotel_services, many=True).data)
                
            )
            return Response(combined_services)


class ServiceDetailBySubcategoryAPIView(APIView):
    def get(self, request):
        service_id = request.GET.get("service_id")
        subcategory_id = request.GET.get("subcategory_id")

        if not service_id or not subcategory_id:
            return Response(
                {"error": "service_id and subcategory_id required"},
                status=400
            )

        try:
            subcategory = ServiceSubcategory.objects.get(id=subcategory_id)
        except ServiceSubcategory.DoesNotExist:
            return Response(
                {"error": "Invalid subcategory_id"},
                status=404
            )

        parent = subcategory.parent_service.strip().lower()

        SERVICE_MAP = {
            "gym": (GymService, GymServiceSerializer),
            "salon": (SaloonService, SaloonServiceSerializer),
            "travel": (TravelAgencyService, TravelAgencyServiceSerializer),
            "tech industry": (TechIndustryService, TechIndustryServiceSerializer),
            "professional": (ProfessionalService, ProfessionalServiceSerializer),  # Added
            "finance" : (FinanceService, FinanceServiceSerializer),
            "healthcare" : (HealthcareService, HealthcareServiceSerializer),
            "education": (EducationNewService, EducationNewServiceSerializer),  
            "restaurant" : ( RestaurantService, RestaurantServiceSerializer),
            "hotel" : (HotelService, HotelServiceSerializer),
        }

        Model, Serializer = None, None

        if parent in SERVICE_MAP:
            Model, Serializer = SERVICE_MAP[parent]
        else:
            for key, (m, s) in SERVICE_MAP.items():
                if key in parent or parent in key:
                    Model, Serializer = m, s
                    break

        if not Model:
            return Response(
                {"error": f"Unsupported parent_service: {parent}"},
                status=400
            )

        try:
            service = Model.objects.get(
                id=service_id,
                subcategory_id=subcategory_id
            )   
        except Model.DoesNotExist:
            try:
                service = Model.objects.get(id=service_id)
            except Model.DoesNotExist:
                return Response(
                    {"error": f"Service not found in {Model.__name__} with id={service_id}"},
                    status=404
                )

        serializer = Serializer(service, context={"request": request})
        return Response(serializer.data)


from rest_framework.permissions import AllowAny

class PublicGymListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = GymServiceSerializer
    
    def get_queryset(self):
        queryset = GymService.objects.filter(status='approved',is_active=True, subcategory__status='Active')
        
        subcategory = self.request.query_params.get('subcategory', None)
        if subcategory:
            queryset = queryset.filter(subcategory__subcategory_name__icontains=subcategory)
        
        city = self.request.query_params.get('city', None)
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        return queryset.order_by('-created_at')


class PublicGymDetailView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request, id):
        try:
            service = GymService.objects.get(id=id, status='approved', is_active=True, subcategory__status='Active')
            serializer = GymServiceSerializer(service, context={'request': request})
            return Response(serializer.data)
        except GymService.DoesNotExist:
            return Response({"error": "Service not found"}, status=404) 
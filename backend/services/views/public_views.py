from services.models.professional import ProfessionalService
from services.models.tech_industry import TechIndustryService
from rest_framework import generics, filters
from django.db.models import Prefetch
from rest_framework.permissions import AllowAny
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, F, Avg, OuterRef, Subquery, FloatField
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from services.serializers.review_serializers import ServiceReviewSerializer
from services.models.review import ServiceReview
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from services.models.gym import GymService
from services.models.travel_agency import TravelAgencyService
from services.serializers.travel_agency_serializers import TravelAgencyServiceSerializer
from services.models.saloon import SaloonService
from services.serializers.saloon_serializers import SaloonServiceSerializer
from services.serializers.gym_serializers import GymServiceSerializer
from services.serializers.subcategory_serializers import ServiceSubcategory,ServiceSubcategorySerializer
from services.serializers.real_estate_serializers import PropertyDetailSerializer
from services.models.real_estate import Property
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
    permission_classes = [AllowAny]

    def get(self, request):
        subcategories = ServiceSubcategory.objects.filter(status="Active",)
        serializer = ServiceSubcategorySerializer(subcategories, many=True)
        return Response(serializer.data)

    
class GymCitiesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, format=None):
        try:
            VENDOR_MODELS = [
                (GymService, "gym_service"),
                (SaloonService, "saloon_service"),
                (TravelAgencyService, "travel_agency_service"),
                (TechIndustryService, "tech_industry_service"),
                (ProfessionalService, "professional_service"),
                (FinanceService,"finance_service"),
                (HealthcareService, "healthcare_service"),
                (EducationNewService,"education_service"),  
                (RestaurantService, "restaurant_service"),
                (HotelService, "hotel_service"),
            ]

            city_data = []

            for Model, type_label in VENDOR_MODELS:
                qs = Model.objects.filter(status__iexact="approved").exclude(city__isnull=True)
                city_names = qs.values_list("city", flat=True).distinct()

                for city_name in city_names:
                    subcategories = qs.filter(city=city_name).values(
                        "subcategory_id", "subcategory__subcategory_name"
                    ).distinct()

                    city_data.append({
                        "id": None,
                        "name": city_name,
                        "type": type_label,
                        "subcategories": [
                            {"id": s["subcategory_id"], "name": s["subcategory__subcategory_name"]}
                            for s in subcategories
                        ]
                    })

            return Response({"cities": city_data}, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

        
class ApprovedServicesBySubcategory(APIView):
    permission_classes = [AllowAny]

    def get_full_url(self, request, file_field):
        if not file_field:
            return None
        try:
            return request.build_absolute_uri(file_field.url)
        except Exception:
            return None

    def get(self, request, format=None):
        VENDOR_MODELS = [
            (GymService, "gym_service", GymServiceSerializer),
            (SaloonService, "saloon_service", SaloonServiceSerializer),
            (TravelAgencyService, "travel_agency_service", TravelAgencyServiceSerializer),
            (ProfessionalService, "professional_service"), 
            (FinanceService, "finance_service"), 
            (HealthcareService, "healthcare_service"),
            (EducationNewService, "education_service"),
            (RestaurantService,"restaurant_service"), 
            (HotelService, "hotel_service"),
        ]

        data = {}

        for Model, type_label, Serializer in VENDOR_MODELS:
            approved_services = Model.objects.filter(status__iexact="approved", is_active=True, subcategory__status='Active')

            for s in approved_services:
                subcategory_title = s.subcategory.subcategory_name if s.subcategory else "Other"

                if subcategory_title not in data:
                    data[subcategory_title] = []

                service_data = {
                    "id": s.id,
                    "type": type_label,
                    "subcategory": s.subcategory.id if s.subcategory else None,
                    "subcategory_name": subcategory_title,
                    "business_name": s.business_name,
                    "address": s.address,
                    "location": s.location,
                    "country": s.country,
                    "state": s.state,
                    "city": s.city,
                    "open_time": s.open_time,
                    "close_time": s.close_time,
                    "contact_no": s.contact_no,
                    "whatsapp_no": s.whatsapp_no,
                    "description": s.description,
                    "main_image": self.get_full_url(request, s.main_image),
                    "second_image": self.get_full_url(request, s.second_image),
                    "multi_images": [
                        {"id": m.id, "image": self.get_full_url(request, m.image)}
                        for m in s.multi_images.all()
                    ],
                    "status": s.status,
                    "items": [
                        {"id": i.id, "name": i.name, "description": i.description, "price": str(i.price)}
                        for i in s.items.all()
                    ],
                    "vendor": s.vendor.id if s.vendor else None,
                    "approved_by": s.approved_by.id if s.approved_by else None,
                    "approved_date": s.approved_date,
                }

                data[subcategory_title].append(service_data)

        response_data = [{"subcategory": sub, "services": services} for sub, services in data.items()]
        return Response({"data": response_data}, status=200)

    
class ServiceDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk, subcategory_id):

        VENDOR_MODELS = [GymService, SaloonService, TravelAgencyService, HealthcareService, EducationNewService, RestaurantService, HotelService]

        service = None
        vendor_type = None

        for Model in VENDOR_MODELS:
            try:
                service = Model.objects.get(
                    id=pk,
                    subcategory__id=subcategory_id
                )
                vendor_type = Model.__name__.lower()
                break
            except Model.DoesNotExist:
                continue

        if not service:
            return Response(
                {"error": "Service not found with matching subcategory"},
                status=404
            )

        if vendor_type == "gymservice":
            serializer = GymServiceSerializer(service)
        elif vendor_type == "saloonservice":
            serializer = SaloonServiceSerializer(service)
        elif vendor_type == "travelagencyservice":
            serializer = TravelAgencyServiceSerializer(service)
        elif vendor_type == "financeservice":
            serializer = FinanceServiceSerializer(service)   
        elif vendor_type == "healthcareservice":
            serializer = HealthcareServiceSerializer(service)
        elif vendor_type == "educationservice":
            serializer = EducationNewServiceSerializer(service)
        elif vendor_type == "restaurantservice":
            serializer = RestaurantServiceSerializer(service)   
        elif vendor_type == "hotelservice":
            serializer = HotelServiceSerializer(service)                               

        data = serializer.data
        data["type"] = vendor_type

        return Response(data)

    
class MultiCategorySearchAPIView(APIView):
    """
    Flexible search across all service types.
    Filters: subcategory, city, keyword
    Only shows services with status='approved'.
    """
    permission_classes = [AllowAny]

    def get(self, request):

        subcategory = request.GET.get("subcategory")
        city = request.GET.get("city")
        keyword = request.GET.get("keyword")

        if not subcategory and not city and not keyword:
            return Response({"services": []}, status=status.HTTP_200_OK)

        # ── Standard filter (models with business_name) ──────────────────────
        def filter_services(queryset, category_name):
            queryset = queryset.filter(
                status='approved',
                is_active=True,
                subcategory__status='Active'
            )
            if subcategory:
                queryset = queryset.filter(
                    subcategory__subcategory_name__icontains=subcategory
                )
            if city:
                queryset = queryset.filter(city__icontains=city)
            if keyword:
                queryset = queryset.filter(
                    Q(business_name__icontains=keyword) |
                    Q(description__icontains=keyword)
                )

            return [
                {
                    "id": s.id,
                    "business_name": s.business_name,
                    "subcategory": s.subcategory.id,
                    "vendor": s.vendor.id,
                    "subcategory_name": s.subcategory.subcategory_name if s.subcategory else None,
                    "city": s.city,
                    "address": s.address,
                    "main_image": request.build_absolute_uri(s.main_image.url) if s.main_image else None,
                    "contact_no": s.contact_no,
                    "category": category_name,
                }
                for s in queryset
            ]

        # ── Restaurant filter (uses restaurant_name, not business_name) ──────
        def filter_restaurant(queryset):
            queryset = queryset.filter(
                status='approved',
                is_active=True,
                subcategory__status='Active'
            )
            if subcategory:
                queryset = queryset.filter(
                    subcategory__subcategory_name__icontains=subcategory
                )
            if city:
                queryset = queryset.filter(city__icontains=city)
            if keyword:
                queryset = queryset.filter(
                    Q(restaurant_name__icontains=keyword) |
                    Q(description__icontains=keyword)
                )

            return [
                {
                    "id": s.id,
                    # business_name = restaurant_name so frontend card works
                    "business_name": s.restaurant_name,
                    "restaurant_name": s.restaurant_name,
                    "subcategory": s.subcategory.id,
                    "vendor": s.vendor.id,
                    "subcategory_name": s.subcategory.subcategory_name if s.subcategory else None,
                    "city": s.city,
                    "address": s.address,
                    "main_image": request.build_absolute_uri(s.main_image.url) if s.main_image else None,
                    "contact_no": s.contact_no,
                    "category": "restaurant",   # ← frontend DETAIL_ROUTE_MAP key
                }
                for s in queryset
            ]

        gym_services       = filter_services(GymService.objects.all(),          "gym")
        saloon_services    = filter_services(SaloonService.objects.all(),        "salon")
        travel_services    = filter_services(TravelAgencyService.objects.all(),  "travel_agency")
        finance_service    = filter_services(FinanceService.objects.all(),       "finance")
        healthcare_service = filter_services(HealthcareService.objects.all(),    "healthcare")
        education_service  = filter_services(EducationNewService.objects.all(),  "education")
        hotel_service      = filter_services(HotelService.objects.all(),         "hotel")
        restaurant_service = filter_restaurant(RestaurantService.objects.all())  # ← fixed
        

        all_services = (
            gym_services
            + saloon_services
            + travel_services
            + finance_service
            + healthcare_service
            + education_service
            + restaurant_service
            + hotel_service
        )

        return Response({"services": all_services}, status=status.HTTP_200_OK)

    
VENDOR_FILTER_MODELS = {
    "gym": (GymService, GymServiceSerializer),
    "salon": (SaloonService, SaloonServiceSerializer),
    "travel agency": (TravelAgencyService, TravelAgencyServiceSerializer),
    "finance": (FinanceService, FinanceServiceSerializer),
    "healthcare": (HealthcareService, HealthcareServiceSerializer),
    "education": (EducationNewService, EducationNewServiceSerializer),
    "restaurant": (RestaurantService, RestaurantServiceSerializer),
    "hotel" : (HotelService, HotelServiceSerializer),
}


class SubcategoryCityAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):

        subcategory_name = request.GET.get("subcategory")
        city_name = request.GET.get("city")
        keyword = request.GET.get("keyword")

        subcategory = None

        if subcategory_name:
            subcategory = ServiceSubcategory.objects.filter(
                subcategory_name=subcategory_name
            ).first()

        elif keyword:
            for key in VENDOR_FILTER_MODELS:
                service_model, _ = VENDOR_FILTER_MODELS[key]

                # restaurant uses restaurant_name
                if key == "restaurant":
                    service = service_model.objects.filter(
                        Q(restaurant_name__icontains=keyword) |
                        Q(description__icontains=keyword) |
                        Q(subcategory__subcategory_name__icontains=keyword)
                    ).first()
                else:
                    service = service_model.objects.filter(
                        Q(business_name__icontains=keyword) |
                        Q(description__icontains=keyword) |
                        Q(subcategory__subcategory_name__icontains=keyword)
                    ).first()

                if service:
                    subcategory = service.subcategory
                    break

        elif city_name:
            for key in VENDOR_FILTER_MODELS:
                service_model, _ = VENDOR_FILTER_MODELS[key]
                service = service_model.objects.filter(
                    city__icontains=city_name
                ).first()
                if service:
                    subcategory = service.subcategory
                    break

        if not subcategory:
            return Response({"subcategories": [], "cities": []})

        parent_service = subcategory.parent_service

        related_subcategories = ServiceSubcategory.objects.filter(
            parent_service=parent_service
        )

        subcategory_names = list(
            related_subcategories.values_list("subcategory_name", flat=True)
        )

        services_data = []
        for key in VENDOR_FILTER_MODELS:
            service_model, _ = VENDOR_FILTER_MODELS[key]
            queryset = service_model.objects.filter(
                subcategory__subcategory_name__in=subcategory_names
            )
            services_data.extend(queryset)

        cities = set()
        for service in services_data:
            if service.city:
                cities.add(service.city)

        return Response({
            "subcategories": subcategory_names,
            "cities": list(cities)
        })

        
class AdvancedServiceSearchAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        min_rating = request.GET.get("rating")
        sort_by = request.GET.get("sort_by")

        final_services = []

        for category_name, (model, _) in VENDOR_FILTER_MODELS.items():
            queryset = model.objects.filter(status="approved")
            content_type = ContentType.objects.get_for_model(model)

            for service in queryset:
                ratings_qs = ServiceReview.objects.filter(
                    object_id=service.id,
                    content_type=content_type
                )
                avg = ratings_qs.aggregate(avg=Avg('rating'))['avg'] or 0
                service.avg_rating = round(avg, 1)

                if min_rating and not ratings_qs.filter(rating__gte=float(min_rating)).exists():
                    continue

                # restaurant_name fallback for display
                name = (
                    getattr(service, "restaurant_name", None)
                    or getattr(service, "business_name", None)
                )

                final_services.append({
                    "id": service.id,
                    "business_name": name,
                    "restaurant_name": getattr(service, "restaurant_name", None),
                    "subcategory_name": service.subcategory.subcategory_name if getattr(service, "subcategory", None) else None,
                    "city": service.city,
                    "address": getattr(service, "address", None),
                    "main_image": request.build_absolute_uri(service.main_image.url) if getattr(service, "main_image", None) else None,
                    "contact_no": getattr(service, "contact_no", None),
                    "avg_rating": getattr(service, "avg_rating", 0),
                    "category": category_name,
                    "created_at": getattr(service, "created_at", None),
                    "vendor": service.vendor.id if service.vendor else None,
                })

        if sort_by == "top_rated":
            final_services = sorted(final_services, key=lambda x: x["avg_rating"], reverse=True)
        elif sort_by == "newest":
            final_services = sorted(final_services, key=lambda x: x["created_at"], reverse=True)

        return Response({
            "success": True,
            "data": final_services
        })

        
VENDOR_MODELS = [
    (GymService, GymServiceSerializer, "gym"),
    (SaloonService, SaloonServiceSerializer, "salon"),
    (TravelAgencyService, TravelAgencyServiceSerializer, "travel_agency"),
    (FinanceService, FinanceServiceSerializer, "finance"),
    (HealthcareService, HealthcareServiceSerializer, "healthcare"),
    (EducationNewService, EducationNewServiceSerializer, "education"),  
    (RestaurantService, RestaurantServiceSerializer, "restaurant"),
    (HotelService, HotelServiceSerializer, "hotel"),
]

        
class AllServicesFilterAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        property_type_name = request.GET.get("property_type")
        subcategory_id = request.GET.get("subcategory")

        if not property_type_name:
            return Response({"error": "property_type query param is required", "data": []}, status=400)

        property_type = get_object_or_404(ServiceSubcategory, subcategory_name__iexact=property_type_name)

        queryset = Property.objects.filter(status="approved", property_type=property_type)
        if subcategory_id:
            queryset = queryset.filter(subcategory_id=subcategory_id)

        serializer = PropertyDetailSerializer(queryset, many=True, context={"request": request})
        data = serializer.data

        for idx, prop in enumerate(queryset):
            main_img = prop.images.filter(image_type='main').first() or prop.images.first()
            if main_img and main_img.image:
                data[idx]['main_image'] = request.build_absolute_uri(main_img.image.url)
            else:
                data[idx]['main_image'] = None
            data[idx]['category_label'] = property_type.subcategory_name

        return Response({property_type_name.lower(): data})
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError

from services.models.restaurant import RestaurantService, RestaurantServiceImage
from services.models.subcategory import ServiceSubcategory
from services.serializers.restaurant_serialisers import (
    RestaurantServiceSerializer, 
    RestaurantServiceListSerializer
)


# ============================================
# VENDOR: List + Create Restaurant Service
# ============================================
class RestaurantServiceListCreateView(APIView):
    """
    GET: List all restaurant services for current vendor
    POST: Create new restaurant service
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = RestaurantService.objects.filter(vendor=vendor)
        serializer = RestaurantServiceSerializer(
            services, many=True, context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        vendor = request.user.vendor
        data = request.data

        # Validate subcategory
        subcategory_id = data.get("subcategory")
        if not subcategory_id:
            raise ValidationError({"subcategory": "Subcategory is required"})
        
        try:
            subcategory = ServiceSubcategory.objects.get(id=subcategory_id)
        except ServiceSubcategory.DoesNotExist:
            raise ValidationError({"subcategory": "Invalid Subcategory ID"})

        # Create restaurant service
        service = RestaurantService.objects.create(
            vendor=vendor,
            subcategory=subcategory,
            restaurant_name=data.get('restaurant_name'),
            address=data.get('address'),
            location=data.get('location', ''),
            country=data.get('country', ''),
            state=data.get('state', ''),
            city=data.get('city', ''),
            contact_no=data.get('contact_no'),
            whatsapp_no=data.get('whatsapp_no', ''),
            gmail_id=data.get('gmail_id', ''),
            restaurant_rating=data.get('restaurant_rating'),
            description=data.get('description', ''),
            tax_description=data.get('tax_description', ''),
            main_image=request.FILES.get('main_image'),
        )

        # Handle multi images
        multi_images_files = request.FILES.getlist('multi_images')
        for img_file in multi_images_files:
            img_instance = RestaurantServiceImage.objects.create(image=img_file)
            service.multi_images.add(img_instance)

        serializer = RestaurantServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ============================================
# VENDOR: Retrieve, Update, Delete
# ============================================
class RestaurantServiceDetailView(APIView):
    """
    GET: Retrieve single restaurant service
    PUT: Update restaurant service
    DELETE: Delete restaurant service
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk, vendor):
        return get_object_or_404(RestaurantService, pk=pk, vendor=vendor)

    def get(self, request, pk):
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        serializer = RestaurantServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        data = request.data

        # Update subcategory if provided
        subcategory_id = data.get("subcategory")
        if subcategory_id:
            try:
                service.subcategory = ServiceSubcategory.objects.get(id=subcategory_id)
            except ServiceSubcategory.DoesNotExist:
                raise ValidationError({"subcategory": "Invalid Subcategory ID"})

        # Update fields
        service.restaurant_name = data.get("restaurant_name", service.restaurant_name)
        service.address = data.get("address", service.address)
        service.location = data.get("location", service.location)
        service.country = data.get("country", service.country)
        service.state = data.get("state", service.state)
        service.city = data.get("city", service.city)
        service.contact_no = data.get("contact_no", service.contact_no)
        service.whatsapp_no = data.get("whatsapp_no", service.whatsapp_no)
        service.gmail_id = data.get("gmail_id", service.gmail_id)
        service.restaurant_rating = data.get("restaurant_rating", service.restaurant_rating)
        service.description = data.get("description", service.description)
        service.tax_description = data.get("tax_description", service.tax_description)

        # Handle main image
        if "main_image" in request.FILES:
            # Delete old image if exists
            if service.main_image:
                service.main_image.delete(save=False)
            service.main_image = request.FILES["main_image"]

        service.save()

        # Handle multi images - append new ones
        if request.FILES.getlist("multi_images"):
            for img_file in request.FILES.getlist("multi_images"):
                img_instance = RestaurantServiceImage.objects.create(image=img_file)
                service.multi_images.add(img_instance)

        serializer = RestaurantServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)

        # Delete images
        if service.main_image:
            service.main_image.delete(save=False)
        
        for img in service.multi_images.all():
            img.image.delete(save=False)
            img.delete()

        service.delete()
        return Response(
            {"message": "Restaurant service deleted successfully"}, 
            status=status.HTTP_204_NO_CONTENT
        )


# ============================================
# PUBLIC: List Restaurant Services (Approved Only)
# ============================================
class PublicRestaurantListView(generics.ListAPIView):
    """
    GET: List all approved restaurant services
    Filters: subcategory, city
    """
    permission_classes = [AllowAny]
    serializer_class = RestaurantServiceSerializer

    def get_queryset(self):
        queryset = RestaurantService.objects.filter(
            status='approved', 
            is_active=True,
            subcategory__status='Active'
        )

        # Filter by subcategory
        subcategory = self.request.query_params.get('subcategory')
        if subcategory:
            queryset = queryset.filter(
                subcategory__subcategory_name__icontains=subcategory
            )

        # Filter by city
        city = self.request.query_params.get('city')
        if city:
            queryset = queryset.filter(city__icontains=city)

        return queryset.order_by('-created_at')


# ============================================
# PUBLIC: Detail View
# ============================================
class PublicRestaurantDetailView(APIView):
    """
    GET: Retrieve single approved restaurant service
    """
    permission_classes = [AllowAny]

    def get(self, request, id):
        try:
            service = RestaurantService.objects.get(
                id=id, 
                status='approved', 
                is_active=True,
                subcategory__status='Active'
            )
            serializer = RestaurantServiceSerializer(service, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except RestaurantService.DoesNotExist:
            return Response(
                {"error": "Restaurant service not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


# ============================================
# ADMIN: Restaurant Service Approval
# ============================================
class RestaurantServiceApprovalAPIView(APIView):
    """
    PATCH: Approve or reject restaurant service
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        status_value = request.data.get("status")
        if status_value not in ["approved", "rejected"]:
            return Response(
                {"error": "Invalid status. Must be 'approved' or 'rejected'"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        service = get_object_or_404(RestaurantService, pk=pk)
        service.status = status_value
        service.approved_by = request.user
        service.approved_date = timezone.now() if status_value == "approved" else None
        service.save()

        return Response({
            "message": f"Restaurant service {status_value} successfully",
            "status": service.status,
            "approved_by": service.approved_by.id if service.approved_by else None,
            "approved_date": service.approved_date
        }, status=status.HTTP_200_OK)


# ============================================
# ADMIN: Restaurant Service Filter/Stats
# ============================================
class RestaurantApprovalFilterAPI(APIView):
    """
    GET: Filter restaurant services for admin
    Query params: status, category
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.GET.get("status")
        category_filter = request.GET.get("category")

        queryset = RestaurantService.objects.select_related(
            "vendor", "subcategory"
        ).all().order_by("-created_at")

        if status_filter and status_filter != "all":
            queryset = queryset.filter(status=status_filter)

        if category_filter:
            queryset = queryset.filter(subcategory__subcategory_name__icontains=category_filter)

        serializer = RestaurantServiceSerializer(
            queryset, many=True, context={"request": request}
        )
        
        # Add type for identification
        data = serializer.data
        for item in data:
            item["type"] = "restaurant"

        return Response({
            "status": True,
            "data": data
        }, status=status.HTTP_200_OK)


class RestaurantApprovalStatsAPI(APIView):
    """
    GET: Restaurant service approval statistics
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total = RestaurantService.objects.count()
        approved = RestaurantService.objects.filter(status='approved').count()
        pending = RestaurantService.objects.filter(status='pending').count()
        rejected = RestaurantService.objects.filter(status='rejected').count()

        return Response({
            "status": True,
            "data": {
                "total_vendor": total,
                "approved": approved,
                "pending": pending,
                "rejected": rejected
            }
        }, status=status.HTTP_200_OK)


# ============================================
# UTILITY: Get Restaurant Cities
# ============================================
class RestaurantCitiesView(APIView):
    """
    GET: Get unique cities with restaurants
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            queryset = RestaurantService.objects.filter(
                status__iexact="approved"
            ).exclude(city__isnull=True).exclude(city='')

            city_data = []
            city_names = queryset.values_list("city", flat=True).distinct()

            for city_name in city_names:
                # Get subcategories for this city
                subcategories = queryset.filter(city=city_name).values(
                    "subcategory_id", "subcategory__subcategory_name"
                ).distinct()

                city_data.append({
                    "id": None,
                    "name": city_name,
                    "type": "restaurant_service",
                    "subcategories": [
                        {"id": s["subcategory_id"], "name": s["subcategory__subcategory_name"]}
                        for s in subcategories
                    ]
                })

            return Response({"cities": city_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================
# MULTI-CATEGORY SEARCH - Add Restaurant
# ============================================
# Add this to your existing MultiCategorySearchAPIView
# In the filter_services function, add restaurant:
"""
restaurant_services = filter_services(RestaurantService.objects.all(), "restaurant")
all_services = gym_services + saloon_services + travel_services + finance_service + healthcare_service + education_service + restaurant_services
"""

# ============================================
# REGISTER RESTAURANT IN VENDOR_MODELS
# ============================================
# Update your gym_views.py to include RestaurantService:

"""
from services.models.restaurant import RestaurantService
from services.serializers.restaurant_serializers import RestaurantServiceSerializer

# Add to VENDOR_MODELS set
VENDOR_MODELS = {
    GymService, SaloonService, TravelAgencyService, 
    TechIndustryService, ProfessionalService, FinanceService,
    HealthcareService, EducationNewService, RestaurantService  # ← Add this
}

# Add to VENDOR_FILTER_MODELS dict
VENDOR_FILTER_MODELS = {
    "gym": (GymService, GymServiceSerializer),
    "salon": (SaloonService, SaloonServiceSerializer),
    "travel_agency": (TravelAgencyService, TravelAgencyServiceSerializer),
    "tech_industry": (TechIndustryService, TechIndustryServiceSerializer),
    "professional": (ProfessionalService, ProfessionalServiceSerializer),
    "finance": (FinanceService, FinanceServiceSerializer),
    "healthcare": (HealthcareService, HealthcareServiceSerializer),
    "education": (EducationNewService, EducationNewServiceSerializer),
    "restaurant": (RestaurantService, RestaurantServiceSerializer),  # ← Add this
}
"""
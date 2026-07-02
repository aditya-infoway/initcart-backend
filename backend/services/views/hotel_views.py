from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError
import json

from services.models.hotel import HotelService, HotelServiceImage, HotelRoomType
from services.models.subcategory import ServiceSubcategory
from services.serializers.hotel_serializers import HotelServiceSerializer


# ============================================
# VENDOR: List + Create Hotel Service
# ============================================
class HotelServiceListCreateView(APIView):
    """
    GET: List all hotel services for current vendor
    POST: Create new hotel service with room types
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = HotelService.objects.filter(vendor=vendor)
        serializer = HotelServiceSerializer(
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

        # Parse room types from JSON
        room_types_data = []
        if data.get('room_types'):
            try:
                room_types_data = json.loads(data.get('room_types'))
            except json.JSONDecodeError:
                raise ValidationError({"room_types": "Invalid JSON format"})

        # Create hotel service
        service = HotelService.objects.create(
            vendor=vendor,
            subcategory=subcategory,
            hotel_name=data.get('hotel_name'),
            address=data.get('address'),
            location=data.get('location', ''),
            country=data.get('country', ''),
            state=data.get('state', ''),
            city=data.get('city', ''),
            contact_no=data.get('contact_no'),
            whatsapp_no=data.get('whatsapp_no', ''),
            gmail_id=data.get('gmail_id', ''),
            hotel_rating=data.get('hotel_rating'),
            description=data.get('description', ''),
            room_category=data.get('room_category', 'manual'),
            main_image=request.FILES.get('main_image'),
        )

        # Handle room types
        for room_data in room_types_data:
            HotelRoomType.objects.create(
                service=service,
                room_type=room_data.get('room_type', ''),
                person=room_data.get('person', 0),
                rate=room_data.get('rate', 0)
            )

        # Handle multi images
        multi_images_files = request.FILES.getlist('multi_images')
        for img_file in multi_images_files:
            img_instance = HotelServiceImage.objects.create(image=img_file)
            service.multi_images.add(img_instance)

        serializer = HotelServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ============================================
# VENDOR: Retrieve, Update, Delete
# ============================================
class HotelServiceDetailView(APIView):
    """
    GET: Retrieve single hotel service
    PUT: Update hotel service with room types
    DELETE: Delete hotel service
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk, vendor):
        return get_object_or_404(HotelService, pk=pk, vendor=vendor)

    def get(self, request, pk):
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        serializer = HotelServiceSerializer(service, context={'request': request})
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
        service.hotel_name = data.get("hotel_name", service.hotel_name)
        service.address = data.get("address", service.address)
        service.location = data.get("location", service.location)
        service.country = data.get("country", service.country)
        service.state = data.get("state", service.state)
        service.city = data.get("city", service.city)
        service.contact_no = data.get("contact_no", service.contact_no)
        service.whatsapp_no = data.get("whatsapp_no", service.whatsapp_no)
        service.gmail_id = data.get("gmail_id", service.gmail_id)
        service.hotel_rating = data.get("hotel_rating", service.hotel_rating)
        service.description = data.get("description", service.description)
        service.room_category = data.get("room_category", service.room_category)

        # Handle main image
        if "main_image" in request.FILES:
            if service.main_image:
                service.main_image.delete(save=False)
            service.main_image = request.FILES["main_image"]

        service.save()

        # Handle room types - delete existing and create new
        if data.get('room_types'):
            try:
                room_types_data = json.loads(data.get('room_types'))
                # Delete existing room types
                HotelRoomType.objects.filter(service=service).delete()
                # Create new room types
                for room_data in room_types_data:
                    HotelRoomType.objects.create(
                        service=service,
                        room_type=room_data.get('room_type', ''),
                        person=room_data.get('person', 0),
                        rate=room_data.get('rate', 0)
                    )
            except json.JSONDecodeError:
                raise ValidationError({"room_types": "Invalid JSON format"})

        # Handle multi images - append new ones
        if request.FILES.getlist("multi_images"):
            for img_file in request.FILES.getlist("multi_images"):
                img_instance = HotelServiceImage.objects.create(image=img_file)
                service.multi_images.add(img_instance)

        serializer = HotelServiceSerializer(service, context={'request': request})
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

        # Delete room types
        HotelRoomType.objects.filter(service=service).delete()

        service.delete()
        return Response(
            {"message": "Hotel service deleted successfully"}, 
            status=status.HTTP_204_NO_CONTENT
        )


# ============================================
# PUBLIC: List Hotel Services (Approved Only)
# ============================================
class PublicHotelListView(generics.ListAPIView):
    """
    GET: List all approved hotel services
    Filters: subcategory, city
    """
    permission_classes = [AllowAny]
    serializer_class = HotelServiceSerializer

    def get_queryset(self):
        queryset = HotelService.objects.filter(
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
class PublicHotelDetailView(APIView):
    """
    GET: Retrieve single approved hotel service
    """
    permission_classes = [AllowAny]

    def get(self, request, id):
        try:
            service = HotelService.objects.get(
                id=id, 
                status='approved', 
                is_active=True,
                subcategory__status='Active'
            )
            serializer = HotelServiceSerializer(service, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except HotelService.DoesNotExist:
            return Response(
                {"error": "Hotel service not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


# ============================================
# ADMIN: Hotel Service Approval
# ============================================
class HotelServiceApprovalAPIView(APIView):
    """
    PATCH: Approve or reject hotel service
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        status_value = request.data.get("status")
        if status_value not in ["approved", "rejected"]:
            return Response(
                {"error": "Invalid status. Must be 'approved' or 'rejected'"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        service = get_object_or_404(HotelService, pk=pk)
        service.status = status_value
        service.approved_by = request.user
        service.approved_date = timezone.now() if status_value == "approved" else None
        service.save()

        return Response({
            "message": f"Hotel service {status_value} successfully",
            "status": service.status,
            "approved_by": service.approved_by.id if service.approved_by else None,
            "approved_date": service.approved_date
        }, status=status.HTTP_200_OK)


# ============================================
# ADMIN: Hotel Service Filter/Stats
# ============================================
class HotelApprovalFilterAPI(APIView):
    """
    GET: Filter hotel services for admin
    Query params: status, category
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.GET.get("status")
        category_filter = request.GET.get("category")

        queryset = HotelService.objects.select_related(
            "vendor", "subcategory"
        ).all().order_by("-created_at")

        if status_filter and status_filter != "all":
            queryset = queryset.filter(status=status_filter)

        if category_filter:
            queryset = queryset.filter(subcategory__subcategory_name__icontains=category_filter)

        serializer = HotelServiceSerializer(
            queryset, many=True, context={"request": request}
        )
        
        data = serializer.data
        for item in data:
            item["type"] = "hotel"

        return Response({
            "status": True,
            "data": data
        }, status=status.HTTP_200_OK)


class HotelApprovalStatsAPI(APIView):
    """
    GET: Hotel service approval statistics
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total = HotelService.objects.count()
        approved = HotelService.objects.filter(status='approved').count()
        pending = HotelService.objects.filter(status='pending').count()
        rejected = HotelService.objects.filter(status='rejected').count()

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
# UTILITY: Get Hotel Cities
# ============================================
class HotelCitiesView(APIView):
    """
    GET: Get unique cities with hotels
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            queryset = HotelService.objects.filter(
                status__iexact="approved"
            ).exclude(city__isnull=True).exclude(city='')

            city_data = []
            city_names = queryset.values_list("city", flat=True).distinct()

            for city_name in city_names:
                subcategories = queryset.filter(city=city_name).values(
                    "subcategory_id", "subcategory__subcategory_name"
                ).distinct()

                city_data.append({
                    "id": None,
                    "name": city_name,
                    "type": "hotel_service",
                    "subcategories": [
                        {"id": s["subcategory_id"], "name": s["subcategory__subcategory_name"]} 
                        for s in subcategories
                    ]
                })

            return Response({"cities": city_data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError

from services.models.healthcare import HealthcareService, HealthcareServiceImage
from services.models.subcategory import ServiceSubcategory
from services.serializers.healthcare_serializers import HealthcareServiceSerializer


# -----------------------------------------------
# Vendor: List + Create
# -----------------------------------------------
class HealthcareServiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        vendor = request.user.vendor
        services = HealthcareService.objects.filter(vendor=vendor)
        serializer = HealthcareServiceSerializer(
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

        service = HealthcareService.objects.create(
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
            img_instance = HealthcareServiceImage.objects.create(image=img_file)
            service.multi_images.add(img_instance)

        serializer = HealthcareServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=201)


# -----------------------------------------------
# Vendor: Retrieve, Update, Delete
# -----------------------------------------------
class HealthcareServiceDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk, vendor):
        return get_object_or_404(HealthcareService, pk=pk, vendor=vendor)

    def get(self, request, pk):
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)
        serializer = HealthcareServiceSerializer(service, context={'request': request})
        return Response(serializer.data)

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
            for img in request.FILES.getlist("multi_images"):
                img_instance = HealthcareServiceImage.objects.create(image=img)
                service.multi_images.add(img_instance)

        serializer = HealthcareServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=200)

    def delete(self, request, pk):
        vendor = request.user.vendor
        service = self.get_object(pk, vendor)

        if service.main_image:
            service.main_image.delete(save=False)

        for img in service.multi_images.all():
            img.image.delete(save=False)
            img.delete()

        service.delete()
        return Response({"message": "Service deleted successfully"}, status=status.HTTP_204_NO_CONTENT)


# -----------------------------------------------
# Public: List (approved only)
# -----------------------------------------------
class PublicHealthcareListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = HealthcareServiceSerializer

    def get_queryset(self):
        qs = HealthcareService.objects.filter(status='approved', subcategory__status='Active')
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
class PublicHealthcareDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, id):
        try:
            service = HealthcareService.objects.get(id=id, status='approved', subcategory__status='Active')
            serializer = HealthcareServiceSerializer(service, context={'request': request})
            return Response(serializer.data)
        except HealthcareService.DoesNotExist:
            return Response({"error": "Service not found"}, status=404)


# -----------------------------------------------
# Admin: Approval
# -----------------------------------------------
class HealthcareServiceApprovalAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        status_value = request.data.get("status")
        if status_value not in ["approved", "rejected"]:
            return Response({"error": "Invalid status"}, status=400)

        service = get_object_or_404(HealthcareService, pk=pk)
        service.status = status_value
        service.approved_by = request.user
        service.approved_date = timezone.now() if status_value == "approved" else None
        service.save()

        return Response({
            "message": "Healthcare service status updated successfully",
            "status": service.status,
            "approved_by": service.approved_by.id if service.approved_by else None
        })
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser

from ecommerce.models.documents import SiteDocument
from ecommerce.serializers.document_serializers import SiteDocumentSerializer, PublicSiteDocumentSerializer

DOC_FIELDS = [
    "contact_us_pdf",
    "privacy_policy_pdf",
    "terms_conditions_pdf",
    "return_cancellation_pdf",
    "refund_pdf",
]


class SiteDocumentAPI(APIView):
    """Superadmin: view and upload/replace/remove the 4 site documents."""
    
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        obj = SiteDocument.objects.first()
        if not obj:
            return Response({})

        data = SiteDocumentSerializer(obj, context={"request": request}).data
        return Response(data)

    def put(self, request):
        obj = SiteDocument.objects.first()

        data = request.data.copy()

        # Allow explicit removal: frontend sends field="" to clear a document
        clear_fields = {}
        for field in DOC_FIELDS:
            if field in data and data.get(field) == "":
                clear_fields[field] = None
                data.pop(field)

        if not obj:
            ser = SiteDocumentSerializer(data=data, context={"request": request})
        else:
            ser = SiteDocumentSerializer(
                obj, data=data, partial=True, context={"request": request}
            )

        ser.is_valid(raise_exception=True)
        saved_obj = ser.save()

        if clear_fields:
            for field, value in clear_fields.items():
                getattr(saved_obj, field).delete(save=False)
                setattr(saved_obj, field, value)
            saved_obj.save(update_fields=list(clear_fields.keys()))

        final_data = SiteDocumentSerializer(
            saved_obj, context={"request": request}
        ).data

        return Response({
            "success": True,
            "message": "Documents updated successfully",
            "data": final_data,
        }, status=status.HTTP_200_OK)


class PublicSiteDocumentAPI(APIView):
    """Public: used by the website to show/download the 4 documents."""

    permission_classes = [AllowAny]

    def get(self, request):
        obj = SiteDocument.objects.first()
        if not obj:
            return Response({}, status=200)

        return Response(
            PublicSiteDocumentSerializer(obj, context={"request": request}).data
        )
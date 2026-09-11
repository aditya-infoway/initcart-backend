#ecommerce/views/qrcard_views.py
from rest_framework import viewsets, permissions, parsers
from rest_framework.response import Response
from rest_framework.views import APIView

from ecommerce.models.qrcards import QRCard
from ecommerce.serializers.qrcard_serializers import QRCardSerializer


class QRCardViewSet(viewsets.ModelViewSet):
    """
    Admin panel CRUD — list/create/retrieve/update/delete.
    FormData (logo file) accept karne ke liye MultiPart parser zaroori hai.
    """
    queryset = QRCard.objects.all()
    serializer_class = QRCardSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]


class QRCardPublicView(APIView):
    """
    Public endpoint — QR scan hone ke baad slug se card details fetch
    karne ke liye. Login/auth ki zaroorat nahi.
    """
    permission_classes = []

    def get(self, request, slug):
        try:
            card = QRCard.objects.get(slug=slug)
        except QRCard.DoesNotExist:
            return Response({"error": "Card not found"}, status=404)

        serializer = QRCardSerializer(card, context={"request": request})
        return Response(serializer.data)
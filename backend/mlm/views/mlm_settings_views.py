#mlm/views/mlm_settings_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import status

from mlm.models.mlm_settings import MLMSettings
from mlm.serializers.mlm_settings_serializer import MLMSettingsSerializer


class MLMSettingsAPIView(APIView):

    permission_classes = [IsAdminUser]

    def get(self, request):

        settings = MLMSettings.objects.first()

        if not settings:
            settings = MLMSettings.objects.create(minimum_sale_amount=0)

        serializer = MLMSettingsSerializer(settings)

        return Response(serializer.data)


class UpdateMLMSettingsAPIView(APIView):

    permission_classes = [IsAdminUser]

    def put(self, request):

        settings = MLMSettings.objects.first()

        if not settings:
            settings = MLMSettings.objects.create()

        serializer = MLMSettingsSerializer(
            settings,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():

            serializer.save()

            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
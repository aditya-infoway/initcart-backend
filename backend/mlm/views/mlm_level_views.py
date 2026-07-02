#mlm/views/mlm_level_views.py
from rest_framework import generics
from mlm.models.mlm_level import MLMLevel
from users.utils.permissions import IsSuperAdmin
from mlm.serializers.mlm_level_serializer import MLMLevelSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication


class MLMLevelListCreateView(generics.ListCreateAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]
    queryset = MLMLevel.objects.all()
    serializer_class = MLMLevelSerializer


class MLMLevelUpdateView(generics.UpdateAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]
    queryset = MLMLevel.objects.all()
    serializer_class = MLMLevelSerializer
    lookup_field = "id"

    
class MLMLevelDeleteView(generics.DestroyAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]
    queryset = MLMLevel.objects.all()
    lookup_field = "id"
    
    
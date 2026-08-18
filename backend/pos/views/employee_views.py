# pos/views/employee_views.py
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication

from pos.models.employee import Employee, EmployeePermission
from pos.serializers.employee_serializers import (
    EmployeeCreateSerializer, EmployeeListSerializer,
    EmployeeDetailSerializer, EmployeeUpdateSerializer,
)
from ecommerce.permissions import IsSuperAdmin


class EmployeeViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication] 
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        branch = getattr(self.request.user, 'branch', None)
        return Employee.objects.filter(branch=branch).order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return EmployeeCreateSerializer
        elif self.action == 'list':
            return EmployeeListSerializer
        elif self.action in ['update', 'partial_update']:
            return EmployeeUpdateSerializer
        return EmployeeDetailSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        return Response({
            "success": True,
            "message": "Employee created successfully!",
            "data": EmployeeDetailSerializer(employee).data
        }, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return Response({"success": True, "data": serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response({"success": True, "data": self.get_serializer(instance).data})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            "success": True,
            "message": "Employee updated successfully!",
            "data": EmployeeDetailSerializer(instance).data
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = instance.user
        instance.delete()
        if user:
            user.delete()
        return Response({"success": True, "message": "Employee deleted successfully"})


class EmployeePermissionView(APIView):
    """
    GET  -> employee ka current data + saved permissions bhejta hai
    POST -> saari permissions ek saath (bulk) update/create karta hai
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication, SessionAuthentication] 

    def get(self, request, employee_id):
        branch = getattr(request.user, 'branch', None)
        employee = get_object_or_404(Employee, id=employee_id, branch=branch)
        return Response({"success": True, "data": EmployeeDetailSerializer(employee).data})

    def post(self, request, employee_id):
        branch = getattr(request.user, 'branch', None)
        employee = get_object_or_404(Employee, id=employee_id, branch=branch)

        permissions = request.data.get('permissions', [])
        for perm in permissions:
            page_key = perm.get('page_key')
            if not page_key:
                continue
            EmployeePermission.objects.update_or_create(
                employee=employee,
                page_key=page_key,
                defaults={
                    'page_label': perm.get('page_label', ''),
                    'can_view': bool(perm.get('can_view', False)),
                    'can_add': bool(perm.get('can_add', False)),
                    'can_edit': bool(perm.get('can_edit', False)),
                    'can_delete': bool(perm.get('can_delete', False)),
                }
            )

        employee.refresh_from_db()
        return Response({
            "success": True,
            "message": "Permissions updated successfully!",
            "data": EmployeeDetailSerializer(employee).data
        })
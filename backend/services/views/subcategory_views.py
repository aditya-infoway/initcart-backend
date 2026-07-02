#services/views/subcategory_views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from ..models.subcategory import ServiceSubcategory
from ..serializers.subcategory_serializers import ServiceSubcategorySerializer
from django.db.models import Q

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class ServiceSubcategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing service subcategories
    """
    queryset = ServiceSubcategory.objects.all().order_by('-created_at')
    serializer_class = ServiceSubcategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['parent_service', 'status']
    search_fields = ['subcategory_name', 'description', 'parent_service']
    ordering_fields = ['subcategory_name', 'parent_service', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Optionally filter by parent service and search term
        """
        queryset = super().get_queryset()
        
        # Filter by parent service if provided
        parent_service = self.request.query_params.get('parent_service', None)
        if parent_service:
            queryset = queryset.filter(parent_service=parent_service)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Search across multiple fields
        search_term = self.request.query_params.get('search', None)
        if search_term:
            queryset = queryset.filter(
                Q(subcategory_name__icontains=search_term) |
                Q(description__icontains=search_term) |
                Q(parent_service__icontains=search_term)
            )
        
        return queryset
    
    def perform_create(self, serializer):
        """
        Set created_by to current user
        """
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def service_categories(self, request):
        """
        Get list of available parent service categories
        """
        categories = ServiceSubcategory.SERVICE_CATEGORIES
        return Response(categories, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def by_service(self, request):
        """
        Get subcategories grouped by parent service
        """
        service_filter = request.query_params.get('service', None)   
        queryset = self.get_queryset().filter(status='Active')
        
        if service_filter:  # ← agar service param hai toh filter karo
            queryset = queryset.filter(parent_service__iexact=service_filter)
        grouped_data = {}
        
        for subcategory in queryset:
            service = subcategory.parent_service
            if service not in grouped_data:
                grouped_data[service] = []
            
            serializer = self.get_serializer(subcategory)
            grouped_data[service].append(serializer.data)
        
        return Response(grouped_data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        """
        Change status of a subcategory
        """
        subcategory = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(ServiceSubcategory.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status value'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        subcategory.status = new_status
        subcategory.save()
        
        serializer = self.get_serializer(subcategory)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def active_by_service(self, request):
        """
        Get active subcategories for a specific service
        """
        service = request.query_params.get('service')
        if not service:
            return Response(
                {'error': 'Service parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(
            parent_service=service,
            status='Active'
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def destroy(self, request, *args, **kwargs):
        """
        Override delete to add custom response
        """
        instance = self.get_object()
        subcategory_name = instance.subcategory_name
        instance.delete()
        
        return Response(
            {
                'message': f'Subcategory "{subcategory_name}" has been deleted successfully',
                'deleted_id': kwargs['pk']
            },
            status=status.HTTP_200_OK
        )
        
    def get_permissions(self):
        if self.action in ['by_service', 'active_by_service', 'service_categories']:
            return [AllowAny()]  
        return super().get_permissions()    
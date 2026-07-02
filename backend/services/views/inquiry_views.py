#services/views/inquiry_views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import filters as drf_filters  # DRF filters
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import  SessionAuthentication
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_filters import CharFilter, NumberFilter, BooleanFilter, DateFilter
from django.db.models import Count, Q, Avg, F
from django.utils import timezone
from datetime import timedelta
import logging

from services.models.inquiry import ServiceInquiry, InquiryAttachment, InquiryNote
from services.serializers.inquiry_serializers import (
    ServiceInquiryCreateSerializer, ServiceInquiryListSerializer,
    ServiceInquiryDetailSerializer, ServiceInquiryUpdateSerializer,
    InquiryNoteSerializer, VendorInquiryDashboardSerializer,
    InquiryStatsSerializer, PublicServiceInquirySerializer
)
from ecommerce.permissions import IsVendorAuthenticated, IsSuperAdmin
from ecommerce.models.vendor import Vendor
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

class ServiceInquiryFilter(FilterSet):
    """Filter for service inquiries"""
    service_category = CharFilter(field_name='service_category')
    status = CharFilter(field_name='status')
    inquiry_type = CharFilter(field_name='inquiry_type')
    date_from = DateFilter(field_name='created_at', lookup_expr='gte')
    date_to = DateFilter(field_name='created_at', lookup_expr='lte')
    is_read = BooleanFilter(field_name='is_read')
    is_archived = BooleanFilter(field_name='is_archived')
    priority = NumberFilter(field_name='priority')
    vendor_id = NumberFilter(field_name='vendor__id')
    customer_email = CharFilter(field_name='customer_email', lookup_expr='icontains')
    customer_name = CharFilter(field_name='customer_name', lookup_expr='icontains')
    
    class Meta:
        model = ServiceInquiry
        fields = [
            'service_category', 'status', 'inquiry_type', 'priority',
            'is_read', 'is_archived', 'vendor_id'
        ]

class PublicServiceInquiryViewSet(viewsets.GenericViewSet):
    """
    Public API for submitting service inquiries
    No authentication required
    """
    queryset = ServiceInquiry.objects.all()
    serializer_class = PublicServiceInquirySerializer
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def create(self, request):
        """
        Submit a new service inquiry
        Vendor must be specified in request data
        """
        # Validate vendor exists and is active
        vendor_id = request.data.get('vendor')
        if not vendor_id:
            return Response(
                {"error": "Vendor ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            vendor = Vendor.objects.get(id=vendor_id)
            if vendor.vendor_type != 'service':
                return Response(
                    {"error": "Only service vendors can receive inquiries"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not vendor.is_approved or vendor.status != 'active':
                return Response(
                    {"error": "Vendor is not active or approved"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Vendor.DoesNotExist:
            return Response(
                {"error": "Vendor not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Add vendor to request data
        data = request.data.copy()
        data['vendor'] = vendor_id
        
        serializer = ServiceInquiryCreateSerializer(
            data=data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            inquiry = serializer.save()
            
            return Response({
                "message": "Inquiry submitted successfully",
                "inquiry_id": inquiry.inquiry_id,
                "data": ServiceInquiryListSerializer(inquiry, context={'request': request}).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def service_categories(self, request):
        """Get available service categories"""
        from services.models.inquiry import ServiceCategory
        categories = [{'value': cat[0], 'label': cat[1]} for cat in ServiceCategory.choices]
        return Response(categories)
    
    @action(detail=False, methods=['get'])
    def inquiry_types(self, request):
        """Get available inquiry types"""
        from services.models.inquiry import InquiryType
        types = [{'value': typ[0], 'label': typ[1]} for typ in InquiryType.choices]
        return Response(types)

class VendorServiceInquiryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for vendors to manage their service inquiries
    """
    queryset = ServiceInquiry.objects.all().order_by('-created_at')
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsVendorAuthenticated]
    serializer_class = ServiceInquiryListSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_class = ServiceInquiryFilter
    search_fields = ['customer_name', 'customer_email', 'customer_phone', 'subject', 'message']
    ordering_fields = ['created_at', 'updated_at', 'priority']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ServiceInquiryCreateSerializer
        elif self.action == 'retrieve':
            return ServiceInquiryDetailSerializer
        elif self.action in ['update', 'partial_update']:
            return ServiceInquiryUpdateSerializer
        return ServiceInquiryListSerializer
    
    def get_queryset(self):
        """Return only inquiries belonging to the logged-in vendor"""
        if self.request.user.is_authenticated and hasattr(self.request.user, 'vendor'):
            vendor = self.request.user.vendor
            return ServiceInquiry.objects.filter(vendor=vendor).order_by('-created_at')
        return ServiceInquiry.objects.none()
    
    def create(self, request):
        """Vendors can create inquiries on behalf of customers"""
        # Auto-set vendor to logged-in vendor
        data = request.data.copy()
        data['vendor'] = request.user.vendor.id
        
        serializer = ServiceInquiryCreateSerializer(
            data=data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            inquiry = serializer.save()
            return Response(
                ServiceInquiryListSerializer(inquiry, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def mark_as_read(self, request, pk=None):
        """Mark inquiry as read"""
        inquiry = self.get_object()
        inquiry.mark_as_read()
        return Response({"message": "Inquiry marked as read", "is_read": inquiry.is_read})
    
    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """Respond to an inquiry"""
        inquiry = self.get_object()
        response_notes = request.data.get('response_notes', '')
        
        if not response_notes:
            return Response(
                {"error": "Response notes are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        inquiry.respond(response_notes, request.user)
        return Response({
            "message": "Response submitted",
            "status": inquiry.get_status_display(),
            "response_date": inquiry.response_date
        })
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark inquiry as resolved"""
        inquiry = self.get_object()
        resolution_notes = request.data.get('resolution_notes', '')
        
        inquiry.resolve(resolution_notes, request.user)
        return Response({
            "message": "Inquiry resolved",
            "status": inquiry.get_status_display()
        })
    
    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """Add internal note to inquiry"""
        inquiry = self.get_object()
        
        serializer = InquiryNoteSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save(inquiry=inquiry, user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get vendor inquiry dashboard"""
        vendor = request.user.vendor
        
        # Calculate stats
        total_inquiries = ServiceInquiry.objects.filter(vendor=vendor).count()
        new_inquiries = ServiceInquiry.objects.filter(vendor=vendor, status='new').count()
        in_progress_inquiries = ServiceInquiry.objects.filter(vendor=vendor, status='in_progress').count()
        responded_inquiries = ServiceInquiry.objects.filter(vendor=vendor, status='responded').count()
        resolved_inquiries = ServiceInquiry.objects.filter(vendor=vendor, status='resolved').count()
        
        # Inquiries by category
        total_by_category = dict(
            ServiceInquiry.objects
            .filter(vendor=vendor)
            .values('service_category')
            .annotate(count=Count('id'))
            .values_list('service_category', 'count')
        )
        
        # Recent inquiries
        recent_inquiries = ServiceInquiry.objects.filter(vendor=vendor)[:10]
        
        # Top service categories
        top_categories = list(
            ServiceInquiry.objects
            .filter(vendor=vendor)
            .values('service_category')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
            .values_list('service_category', flat=True)
        )
        
        data = {
            'total_inquiries': total_inquiries,
            'new_inquiries': new_inquiries,
            'in_progress_inquiries': in_progress_inquiries,
            'responded_inquiries': responded_inquiries,
            'resolved_inquiries': resolved_inquiries,
            'total_by_category': total_by_category,
            'recent_inquiries': ServiceInquiryListSerializer(recent_inquiries, many=True, context={'request': request}).data,
            'top_service_categories': top_categories
        }
        
        serializer = VendorInquiryDashboardSerializer(data=data)
        serializer.is_valid()
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get detailed inquiry statistics"""
        vendor = request.user.vendor
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        # Status breakdown
        status_counts = dict(
            ServiceInquiry.objects
            .filter(vendor=vendor)
            .values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        
        # Category breakdown
        category_counts = dict(
            ServiceInquiry.objects
            .filter(vendor=vendor)
            .values('service_category')
            .annotate(count=Count('id'))
            .values_list('service_category', 'count')
        )
        
        # Monthly trend
        monthly_counts = list(
            ServiceInquiry.objects
            .filter(vendor=vendor, created_at__gte=thirty_days_ago)
            .extra({'month': "DATE_TRUNC('month', created_at)"})
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
            .values('month', 'count')
        )
        
        # Average response time (for responded inquiries)
        avg_response_time = ServiceInquiry.objects.filter(
            vendor=vendor,
            status='responded',
            response_date__isnull=False
        ).aggregate(
            avg_time=Avg(F('response_date') - F('created_at'))
        )['avg_time']
        
        avg_hours = avg_response_time.total_seconds() / 3600 if avg_response_time else 0
        
        # Resolution rate
        total_inquiries = ServiceInquiry.objects.filter(vendor=vendor).count()
        total_resolved = ServiceInquiry.objects.filter(vendor=vendor, status__in=['resolved', 'closed']).count()
        resolution_rate = (total_resolved / total_inquiries * 100) if total_inquiries > 0 else 0
        
        data = {
            'total_inquiries': total_inquiries,
            'inquiries_by_status': status_counts,
            'inquiries_by_category': category_counts,
            'inquiries_by_month': monthly_counts,
            'average_response_time': round(avg_hours, 2),
            'resolution_rate': round(resolution_rate, 2)
        }
        
        serializer = InquiryStatsSerializer(data=data)
        serializer.is_valid()
        return Response(serializer.data)

class AdminServiceInquiryViewSet(viewsets.ModelViewSet):
    """
    Admin ViewSet for managing all service inquiries
    Superadmin can view and manage all inquiries
    """
    queryset = ServiceInquiry.objects.all().order_by('-created_at')
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]
    serializer_class = ServiceInquiryDetailSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_class = ServiceInquiryFilter
    search_fields = ['customer_name', 'customer_email', 'customer_phone', 'subject', 'message', 'inquiry_id']
    ordering_fields = ['created_at', 'updated_at', 'priority']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ServiceInquiryListSerializer
        elif self.action in ['update', 'partial_update']:
            return ServiceInquiryUpdateSerializer
        return ServiceInquiryDetailSerializer
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Admin dashboard with all inquiries"""
        # Total stats
        total_inquiries = ServiceInquiry.objects.count()
        new_inquiries = ServiceInquiry.objects.filter(status='new').count()
        in_progress_inquiries = ServiceInquiry.objects.filter(status='in_progress').count()
        
        # By vendor type
        service_vendors = Vendor.objects.filter(vendor_type='service', is_approved=True)
        vendor_inquiry_counts = {
            vendor.business_name: ServiceInquiry.objects.filter(vendor=vendor).count()
            for vendor in service_vendors
        }
        
        # Recent inquiries
        recent_inquiries = ServiceInquiry.objects.select_related('vendor')[:20]
        
        # Top categories
        top_categories = list(
            ServiceInquiry.objects
            .values('service_category')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        
        return Response({
            'total_inquiries': total_inquiries,
            'new_inquiries': new_inquiries,
            'in_progress_inquiries': in_progress_inquiries,
            'vendor_inquiry_counts': vendor_inquiry_counts,
            'recent_inquiries': ServiceInquiryListSerializer(recent_inquiries, many=True, context={'request': request}).data,
            'top_categories': top_categories
        })
    
    @action(detail=False, methods=['get'])
    def vendor_stats(self, request):
        """Get inquiry statistics by vendor"""
        vendor_id = request.query_params.get('vendor_id')
        
        if vendor_id:
            try:
                vendor = Vendor.objects.get(id=vendor_id)
                inquiries = ServiceInquiry.objects.filter(vendor=vendor)
                
                stats = {
                    'vendor': vendor.business_name,
                    'total_inquiries': inquiries.count(),
                    'by_status': dict(inquiries.values('status').annotate(count=Count('id')).values_list('status', 'count')),
                    'by_category': dict(inquiries.values('service_category').annotate(count=Count('id')).values_list('service_category', 'count')),
                    'average_response_time': inquiries.filter(response_date__isnull=False).aggregate(
                        avg_time=Avg(F('response_date') - F('created_at'))
                    )['avg_time']
                }
                
                return Response(stats)
            except Vendor.DoesNotExist:
                return Response({"error": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Get all service vendors with their inquiry counts
        vendors = Vendor.objects.filter(vendor_type='service', is_approved=True)
        vendor_stats = []
        
        for vendor in vendors:
            inquiry_count = ServiceInquiry.objects.filter(vendor=vendor).count()
            if inquiry_count > 0:
                vendor_stats.append({
                    'id': vendor.id,
                    'name': vendor.business_name,
                    'email': vendor.email,
                    'inquiry_count': inquiry_count,
                    'last_inquiry': ServiceInquiry.objects.filter(vendor=vendor).order_by('-created_at').first().created_at if inquiry_count > 0 else None
                })
        
        return Response(sorted(vendor_stats, key=lambda x: x['inquiry_count'], reverse=True))
    @action(detail=False, methods=['get'])
    def super_admin_list(self, request):
        """
        Special endpoint for Super Admin with specific columns
        Returns: SR No., Vendor Name, Service Name, User Name, 
                Number, City, Message, Create Date, Create Time
        """
        from services.serializers.inquiry_serializers import SuperAdminInquiryListSerializer
        
        # Get filtered queryset
        queryset = self.filter_queryset(self.get_queryset())
        
        # Add pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            # Pass queryset to context for serial number calculation
            serializer = SuperAdminInquiryListSerializer(
                page, 
                many=True, 
                context={'request': request, 'queryset': page}
            )
            return self.get_paginated_response(serializer.data)
        
        # For non-paginated response
        serializer = SuperAdminInquiryListSerializer(
            queryset, 
            many=True, 
            context={'request': request, 'queryset': queryset}
        )
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign inquiry to admin user"""
        inquiry = self.get_object()
        user_id = request.data.get('user_id')
        
        try:
            user = User.objects.get(id=user_id)
            inquiry.assigned_to = user
            inquiry.save()
            return Response({"message": f"Inquiry assigned to {user.get_full_name()}"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export inquiries data"""
        from django.http import HttpResponse
        import csv
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="service_inquiries.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Inquiry ID', 'Service Category', 'Vendor', 'Customer Name',
            'Customer Email', 'Customer Phone', 'Inquiry Type', 'Subject',
            'Status', 'Priority', 'Created Date', 'Response Date'
        ])
        
        inquiries = self.filter_queryset(self.get_queryset())
        for inquiry in inquiries:
            writer.writerow([
                inquiry.inquiry_id,
                inquiry.get_service_category_display(),
                inquiry.vendor.business_name if inquiry.vendor else '',
                inquiry.customer_name,
                inquiry.customer_email,
                inquiry.customer_phone,
                inquiry.get_inquiry_type_display(),
                inquiry.subject,
                inquiry.get_status_display(),
                inquiry.priority,
                inquiry.created_at.strftime('%Y-%m-%d %H:%M'),
                inquiry.response_date.strftime('%Y-%m-%d %H:%M') if inquiry.response_date else ''
            ])
        
        return response
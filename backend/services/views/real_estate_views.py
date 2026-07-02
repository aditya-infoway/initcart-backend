#services/views/real_estate_views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication 
from rest_framework.authentication import  SessionAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum
from django.utils import timezone
from django.core.exceptions import PermissionDenied
import logging
from services.models.subcategory import ServiceSubcategory
from django.db.models import Min, Max, Avg, Count, Q, Sum
from django_filters import FilterSet, CharFilter, NumberFilter
from django.http import HttpResponse
import csv


logger = logging.getLogger(__name__)

from services.models.real_estate import Property, PropertyEnquiry
from services.serializers.real_estate_serializers import (
    PropertyListSerializer, PropertyCreateSerializer, PropertyDetailSerializer,
    PropertyAdminSerializer, PropertyStatusUpdateSerializer,
    PropertyEnquirySerializer, CreateEnquirySerializer,
    VendorPropertyDashboardSerializer, PropertyUpdateSerializer, PublicPropertyDetailSerializer ,PublicPropertyListSerializer,
)
from ecommerce.permissions import IsVendorAuthenticated, IsSuperAdmin

from django_filters import FilterSet, CharFilter, NumberFilter, ChoiceFilter, BooleanFilter

class PropertyFilter(FilterSet):
    min_price = NumberFilter(field_name="price", lookup_expr='gte')
    max_price = NumberFilter(field_name="price", lookup_expr='lte')
    min_area = NumberFilter(field_name="total_area_size", lookup_expr='gte')
    max_area = NumberFilter(field_name="total_area_size", lookup_expr='lte')
    bedrooms = CharFilter(method='filter_bedrooms')
    property_type = CharFilter(field_name='property_type')
    transaction_type = CharFilter(field_name='transaction_type')
    city = CharFilter(field_name='city', lookup_expr='icontains')
    search = CharFilter(method='filter_search')
    
    class Meta:
        model = Property
        fields = ['property_type', 'transaction_type', 'city', 'bedrooms']
    
    def filter_bedrooms(self, queryset, name, value):
        if value == '4+':
            return queryset.filter(bedrooms__gte=4)
        try:
            return queryset.filter(bedrooms=value)
        except ValueError:
            return queryset
    
    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(address__icontains=value) |
            Q(city__icontains=value) |
            Q(state__icontains=value) |
            Q(landmark__icontains=value)
        )

class VendorPropertyViewSet(viewsets.ModelViewSet):
    """ViewSet for vendors to manage their properties"""
    queryset = Property.objects.all().order_by('-created_at')
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsVendorAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PropertyFilter
    search_fields = ['title', 'description', 'address', 'city', 'state']
    ordering_fields = ['price', 'total_area_size', 'created_at', 'views_count']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PropertyCreateSerializer
        elif self.action == 'list':
            return PropertyListSerializer
        elif self.action == 'retrieve':
            return PropertyDetailSerializer
        elif self.action in ['update', 'partial_update']:
            return PropertyUpdateSerializer
        return PropertyListSerializer

    
    def get_queryset(self):
        """Return only properties belonging to the logged-in vendor"""
        if self.request.user.is_authenticated and hasattr(self.request.user, 'vendor'):
            return Property.objects.filter(vendor=self.request.user.vendor).order_by('-created_at')
        return Property.objects.none()

    def perform_update(self, serializer):
        """Handle property updates - set status to pending if editing approved property"""
        instance = serializer.instance
        
        # If editing an approved property, change status to pending for re-approval
        if instance.status == 'approved':
            instance.status = 'pending'
            instance.save()
        
        serializer.save()
    
    def perform_create(self, serializer):
        """Set vendor and user automatically"""
        try:
            # Don't pass vendor and user, serializer will handle them
            serializer.save()
        except Exception as e:
            logger.error(f"Error creating property: {str(e)}")
            raise

    @action(detail=False, methods=['get'])
    def property_type_choices(self, request):
        """Get available property types from subcategories"""
        from services.models.subcategory import ServiceSubcategory

        # Get real estate subcategories
        subcategories = ServiceSubcategory.objects.filter(
            parent_service='Real-Estate',
            status='Active'
        ).order_by('subcategory_name').distinct()
        
        # Format for frontend dropdown
        choices = [
            {
                'value': sub.subcategory_name.lower().replace(' ', '_'),
                'label': sub.subcategory_name,
                'id': sub.id
            }
            for sub in subcategories
        ]
        
        # If no subcategories, return default choices
        if not choices:
            choices = [
                {'value': 'apartment', 'label': 'Apartment'},
                {'value': 'house', 'label': 'House'},
                {'value': 'villa', 'label': 'Villa'},
                {'value': 'commercial', 'label': 'Commercial'},
                {'value': 'pg_coliving', 'label': 'PG/Co-living'},
                {'value': 'plots', 'label': 'Plots'},
            ]
        
        return Response(choices, status=status.HTTP_200_OK)


    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit property for admin approval"""
        property_obj = self.get_object()
        
        if property_obj.vendor != request.user.vendor:
            raise PermissionDenied("You don't have permission to modify this property")
        
        if property_obj.status not in ['draft', 'rejected']:
            return Response(
                {"error": "Only draft or rejected properties can be submitted for approval"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        property_obj.status = 'pending'
        property_obj.save()
        
        return Response({
            "message": "Property submitted for approval",
            "status": property_obj.status
        })
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Vendor property dashboard"""
        vendor = request.user.vendor
        
        # Get counts
        total_properties = Property.objects.filter(vendor=vendor).count()
        approved_properties = Property.objects.filter(vendor=vendor, status='approved').count()
        pending_properties = Property.objects.filter(vendor=vendor, status='pending').count()
        draft_properties = Property.objects.filter(vendor=vendor, status='draft').count()
        sold_rented_properties = Property.objects.filter(vendor=vendor, status='sold_rented').count()
        
        # Get total views
        total_views = Property.objects.filter(vendor=vendor).aggregate(
            total_views=Sum('views_count')
        )['total_views'] or 0
        
        # Get total enquiries
        total_enquiries = PropertyEnquiry.objects.filter(
            property__vendor=vendor
        ).count()
        
        # Get recent enquiries
        recent_enquiries = PropertyEnquiry.objects.filter(
            property__vendor=vendor
        ).order_by('-created_at')[:10]
        
        # Get recent properties
        recent_properties = Property.objects.filter(
            vendor=vendor
        ).order_by('-created_at')[:5]
        
        data = {
            'total_properties': total_properties,
            'approved_properties': approved_properties,
            'pending_properties': pending_properties,
            'draft_properties': draft_properties,
            'sold_rented_properties': sold_rented_properties,
            'total_views': total_views,
            'total_enquiries': total_enquiries,
            'recent_enquiries': PropertyEnquirySerializer(recent_enquiries, many=True).data,
            'recent_properties': PropertyListSerializer(recent_properties, many=True).data,
        }
        
        serializer = VendorPropertyDashboardSerializer(data=data)
        serializer.is_valid()
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def enquiries(self, request, pk=None):
        """Get enquiries for a specific property"""
        property_obj = self.get_object()
        
        if property_obj.vendor != request.user.vendor:
            raise PermissionDenied("You don't have permission to view enquiries for this property")
        
        enquiries = PropertyEnquiry.objects.filter(property=property_obj).order_by('-created_at')
        serializer = PropertyEnquirySerializer(enquiries, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def contact_info(self, request):
        """Get vendor's contact information for auto-fill"""
        if not hasattr(request.user, 'vendor'):
            return Response(
                {"error": "User is not a vendor"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        vendor = request.user.vendor
        data = {
            'name': vendor.owner_name or '',
            'email': vendor.email or '',
            'phone': vendor.phone or '',
            'owner_name': vendor.owner_name or '',
            'business_name': vendor.business_name or '',
            'address': vendor.address or '',
            'city': vendor.city or '',
            'state': vendor.state or '',
            'pincode': vendor.pincode or ''
        }
        
        return Response(data)

class PublicPropertyViewSet(viewsets.ReadOnlyModelViewSet):
    """Public API for viewing approved properties on website"""
    serializer_class = PublicPropertyListSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PropertyFilter
    search_fields = ['title', 'description', 'address', 'city', 'state', 'landmark']
    ordering_fields = ['price', 'total_area_size', 'created_at', 'views_count']
    ordering = ['-created_at']
    
        
    @action(detail=False, methods=['get'])
    def property_types(self, request):
        """Get dynamic property types from subcategories"""
        try:
            # Get all active subcategories for Real-Estate service
            subcategories = ServiceSubcategory.objects.filter(
                parent_service='Real-Estate',
                status='Active'
            ).order_by('subcategory_name')
            
            # Format for frontend
            property_types = []
            for subcategory in subcategories:
                # Create slugified version for value
                value = subcategory.subcategory_name.lower().replace(' ', '_')
                
                property_types.append({
                    'value': value,
                    'label': subcategory.subcategory_name,
                    'id': subcategory.id
                })
            
            # If no subcategories found, return default types
            if not property_types:
                property_types = [
                    {'value': 'apartment', 'label': 'Apartment', 'id': None},
                    {'value': 'house', 'label': 'House', 'id': None},
                    {'value': 'villa', 'label': 'Villa', 'id': None},
                    {'value': 'commercial', 'label': 'Commercial', 'id': None},
                    {'value': 'pg_coliving', 'label': 'PG/Co-living', 'id': None},
                    {'value': 'plots', 'label': 'Plots', 'id': None},
                ]
            
            return Response(property_types, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching property types: {str(e)}")
            return Response(
                {'error': 'Failed to fetch property types'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_queryset(self):
        """Only show approved and active properties"""
        return Property.objects.filter(
            status='approved'
        ).exclude(
            status__in=['sold_rented', 'expired']
        ).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PublicPropertyDetailSerializer
        return PublicPropertyListSerializer
    
    def retrieve(self, request, *args, **kwargs):
        """Increment view count when property is viewed"""
        instance = self.get_object()
        
        # Increment view count
        instance.views_count += 1
        instance.save(update_fields=['views_count'])
        
        serializer = PublicPropertyDetailSerializer(instance, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def create_enquiry(self, request, slug=None):
        """Create an enquiry for a property"""
        property_obj = self.get_object()
        
        # Check if property is available
        if not property_obj.is_available:
            return Response(
                {"error": "This property is not available for enquiries"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = request.data.copy()
        data['property'] = property_obj.id
        
        serializer = CreateEnquirySerializer(data=data)
        if serializer.is_valid():
            enquiry = serializer.save()
            
            return Response({
                "message": "Enquiry submitted successfully",
                "enquiry_id": enquiry.id
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured properties"""
        featured_properties = self.get_queryset().filter(is_featured=True)[:10]
        serializer = self.get_serializer(featured_properties, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent properties"""
        recent_properties = self.get_queryset().order_by('-created_at')[:20]
        serializer = self.get_serializer(recent_properties, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get property statistics for website"""
        total_properties = self.get_queryset().count()
        featured_count = self.get_queryset().filter(is_featured=True).count()
        
        # Property type distribution
        property_types = self.get_queryset().values('property_type').annotate(
            count=Count('property_type')
        )
        
        # City distribution
        cities = self.get_queryset().values('city').annotate(
            count=Count('city')
        ).order_by('-count')[:5]
        
        return Response({
            'total_properties': total_properties,
            'featured_count': featured_count,
            'property_types': list(property_types),
            'top_cities': list(cities)
        })
    
    @action(detail=False, methods=['get'])
    def search_filters(self, request):
        """Get available filters for search"""
        cities = Property.objects.filter(status='approved').values_list(
            'city', flat=True
        ).distinct().order_by('city')
        
        property_types = Property.objects.filter(status='approved').values_list(
            'property_type', flat=True
        ).distinct()
        
        transaction_types = Property.objects.filter(status='approved').values_list(
            'transaction_type', flat=True
        ).distinct()
        
        # Price range
        price_stats = Property.objects.filter(status='approved').aggregate(
            min_price=Min('price'),
            max_price=Max('price'),
            avg_price=Avg('price')
        )
        
        # Area range
        area_stats = Property.objects.filter(status='approved').aggregate(
            min_area=Min('total_area_size'),
            max_area=Max('total_area_size'),
            avg_area=Avg('total_area_size')
        )
        
        return Response({
            'cities': list(cities),
            'property_types': list(property_types),
            'transaction_types': list(transaction_types),
            'price_range': {
                'min': price_stats['min_price'] or 0,
                'max': price_stats['max_price'] or 0,
                'avg': price_stats['avg_price'] or 0
            },
            'area_range': {
                'min': area_stats['min_area'] or 0,
                'max': area_stats['max_area'] or 0,
                'avg': area_stats['avg_area'] or 0
            }
        })

class AdminPropertyViewSet(viewsets.ModelViewSet):
    """Admin ViewSet for managing all properties"""
    queryset = Property.objects.all().order_by('-created_at')
    authentication_classes = [JWTAuthentication,SessionAuthentication]
    permission_classes = [IsSuperAdmin]
    serializer_class = PropertyAdminSerializer

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['title', 'description', 'address', 'city', 'property_id']

    def retrieve(self, request, *args, **kwargs):
        """Get property details for admin"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        """Admin can update any property"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def vendor_details(self, request, pk=None):
        """Get vendor details for a property"""
        property_obj = self.get_object()
        vendor = property_obj.vendor
        
        from ecommerce.serializers.vendor_serializers import VendorDetailSerializer
        serializer = VendorDetailSerializer(vendor, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def enquiries_list(self, request, pk=None):
        """Get all enquiries for a property"""
        property_obj = self.get_object()
        enquiries = PropertyEnquiry.objects.filter(property=property_obj).order_by('-created_at')
        serializer = PropertyEnquirySerializer(enquiries, many=True)
        return Response(serializer.data)

    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending properties for approval"""
        pending_properties = self.queryset.filter(status='pending')
        serializer = self.get_serializer(pending_properties, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get admin dashboard stats"""
        total_properties = self.queryset.count()
        pending_count = self.queryset.filter(status='pending').count()
        approved_count = self.queryset.filter(status='approved').count()
        rejected_count = self.queryset.filter(status='rejected').count()
        draft_count = self.queryset.filter(status='draft').count()
        
        # Recent activities
        recent_approvals = self.queryset.filter(
            approved_at__isnull=False
        ).order_by('-approved_at')[:10]
        
        # Vendor stats
        vendor_stats = Property.objects.values(
            'vendor__business_name', 'vendor__id'
        ).annotate(
            total=Count('id'),
            approved=Count('id', filter=Q(status='approved')),
            pending=Count('id', filter=Q(status='pending'))
        ).order_by('-total')[:5]
        
        # Property type distribution
        type_stats = Property.objects.values('property_type').annotate(
            count=Count('property_type')
        ).order_by('-count')
        
        # Transaction type distribution
        transaction_stats = Property.objects.values('transaction_type').annotate(
            count=Count('transaction_type')
        ).order_by('-count')
        
        return Response({
            'total_properties': total_properties,
            'pending_approval': pending_count,
            'approved': approved_count,
            'rejected': rejected_count,
            'draft': draft_count,
            'recent_approvals': PropertyAdminSerializer(recent_approvals, many=True).data,
            'top_vendors': list(vendor_stats),
            'property_types': list(type_stats),
            'transaction_types': list(transaction_stats)
        })

    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a property"""
        property_obj = self.get_object()
        
        if property_obj.status != 'pending':
            return Response(
                {"error": "Only pending properties can be approved"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = PropertyStatusUpdateSerializer(data=request.data)
        if serializer.is_valid():
            admin_notes = serializer.validated_data.get('admin_notes', '')
            property_obj.approve(request.user, admin_notes)
            
            return Response({
                "message": "Property approved successfully",
                "status": property_obj.status,
                "approved_at": property_obj.approved_at,
                "published_at": property_obj.published_at,
                "property_id": property_obj.property_id
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a property"""
        property_obj = self.get_object()
        
        if property_obj.status != 'pending':
            return Response(
                {"error": "Only pending properties can be rejected"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = PropertyStatusUpdateSerializer(data=request.data)
        if serializer.is_valid():
            admin_notes = serializer.validated_data.get('admin_notes', '')
            property_obj.reject(request.user, admin_notes)
            
            return Response({
                "message": "Property rejected",
                "status": property_obj.status,
                "rejected_at": property_obj.approved_at,
                "admin_notes": admin_notes
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def mark_featured(self, request, pk=None):
        """Mark/unmark property as featured"""
        property_obj = self.get_object()
        is_featured = request.data.get('is_featured', False)
        
        property_obj.is_featured = is_featured
        property_obj.save()
        
        return Response({
            "message": f"Property {'marked as' if is_featured else 'removed from'} featured",
            "is_featured": property_obj.is_featured
        })
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export properties data"""
        from django.http import HttpResponse
        import csv
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="properties.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Property ID', 'Title', 'Vendor', 'Type', 'Transaction',
            'City', 'State', 'Price', 'Area', 'Bedrooms', 'Status',
            'Created Date', 'Approved Date', 'Views', 'Enquiries'
        ])
        
        properties = self.get_queryset()
        for prop in properties:
            writer.writerow([
                prop.property_id,
                prop.title,
                prop.vendor.business_name if prop.vendor else '',
                prop.get_property_type_display(),
                prop.get_transaction_type_display(),
                prop.city,
                prop.state,
                prop.price,
                prop.total_area_size,
                prop.bedrooms,
                prop.get_status_display(),
                prop.created_at.strftime('%Y-%m-%d'),
                prop.approved_at.strftime('%Y-%m-%d') if prop.approved_at else '',
                prop.views_count,
                prop.enquiry_count
            ])
        
        return response

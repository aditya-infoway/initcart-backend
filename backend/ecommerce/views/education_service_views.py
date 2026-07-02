from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import models

from ecommerce.models.education_service import EducationService
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.education_service_serializer import (
    EducationServiceSerializer,
    EducationServiceCreateSerializer,
    EducationServiceUpdateSerializer,
    EducationServiceListSerializer,
    EducationServiceSubmitSerializer,
    EducationServiceApproveSerializer,
    EducationServiceRejectSerializer,
    EducationServiceStatusUpdateSerializer
)
from ecommerce.permissions import IsSuperAdmin, IsVendorAuthenticated

class EducationServiceViewSet(viewsets.ModelViewSet):
    queryset = EducationService.objects.all().order_by('-created_at')
    authentication_classes = [JWTAuthentication]
    parser_classes = [MultiPartParser, FormParser]
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['service_name', 'short_description', 'city', 'state', 'subjects_courses']
    filterset_fields = ['status', 'is_active', 'education_type', 'mode_of_class', 'city', 'state']
    ordering_fields = ['price', 'created_at', 'views_count']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'public_list', 'filter_options']:
            return [AllowAny()]
        elif self.action in ['create', 'my_services', 'vendor_dashboard', 'submit_for_approval']:
            return [IsVendorAuthenticated()]
        elif self.action in ['approve', 'reject', 'admin_list', 'pending_approvals']:
            return [IsSuperAdmin()]
        elif self.action in ['toggle_active', 'update_status']:
            # Both vendor (for their services) and admin (for all) can toggle active
            return [IsAuthenticated()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return EducationServiceCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return EducationServiceUpdateSerializer
        elif self.action in ['list', 'retrieve', 'public_list', 'admin_list', 'pending_approvals']:
            return EducationServiceListSerializer
        elif self.action == 'submit_for_approval':
            return EducationServiceSubmitSerializer
        elif self.action == 'approve':
            return EducationServiceApproveSerializer
        elif self.action == 'reject':
            return EducationServiceRejectSerializer
        elif self.action in ['toggle_active', 'update_status']:
            return EducationServiceStatusUpdateSerializer
        return EducationServiceSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        if self.action == 'my_services':
            # Vendor can see all their services
            vendor = get_object_or_404(Vendor, user=user)
            return EducationService.objects.filter(vendor=vendor).order_by('-created_at')
        elif self.action == 'admin_list':
            # Admin can see all services
            return EducationService.objects.all().order_by('-created_at')
        elif self.action == 'pending_approvals':
            # Only pending approval services
            return EducationService.objects.filter(status='pending').order_by('-submitted_for_approval_at')
        elif self.action == 'public_list':
            # Public can only see approved and active services
            return EducationService.objects.filter(status='approved', is_active=True).order_by('-created_at')
        return super().get_queryset()
    
    # ==================== VENDOR ACTIONS ====================
    
    # Create Education Service (Default status: draft)
    def create(self, request):
        vendor = get_object_or_404(Vendor, user=request.user)
        
        if vendor.vendor_type != 'service' or vendor.vendor_subtype != 'education':
            return Response({
                "success": False,
                "message": "Only education service vendors can add education services"
            }, status=403)
        
        data = request.data.copy()
        data['vendor'] = vendor.id
        
        serializer = EducationServiceCreateSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            education_service = serializer.save(vendor=vendor, status='draft')
            
            return Response({
                "success": True,
                "message": "Education service created as draft",
                "data": {
                    "id": education_service.id,
                    "service_name": education_service.service_name,
                    "status": education_service.status,
                    "can_be_submitted": education_service.can_be_submitted_for_approval
                }
            }, status=201)
        
        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=400)
    
    # Get vendor's own services
    @action(detail=False, methods=['get'], url_path='my-services')
    def my_services(self, request):
        vendor = get_object_or_404(Vendor, user=request.user)
        services = EducationService.objects.filter(vendor=vendor).order_by('-created_at')
        
        # Apply filters if any
        status_filter = request.query_params.get('status')
        if status_filter:
            services = services.filter(status=status_filter)
        
        serializer = self.get_serializer(services, many=True)
        
        return Response({
            "success": True,
            "count": services.count(),
            "services": serializer.data
        })
    
    # Vendor updates their service (only if in draft or rejected state)
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        vendor = get_object_or_404(Vendor, user=request.user)
        
        if instance.vendor != vendor:
            return Response({
                "success": False,
                "message": "You can only update your own services"
            }, status=403)
        
        if not instance.can_be_edited_by_vendor:
            return Response({
                "success": False,
                "message": f"Cannot edit service in '{instance.status}' status. Contact admin."
            }, status=400)
        
        serializer = EducationServiceUpdateSerializer(instance, data=request.data, partial=True, context={'request': request})
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Education service updated successfully",
                "data": serializer.data
            })
        
        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=400)
    
    # Vendor deletes their service
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        vendor = get_object_or_404(Vendor, user=request.user)
        
        if instance.vendor != vendor:
            return Response({
                "success": False,
                "message": "You can only delete your own services"
            }, status=403)
        
        service_name = instance.service_name
        instance.delete()
        
        return Response({
            "success": True,
            "message": f"Education service '{service_name}' deleted successfully"
        })
    
    # Vendor submits service for approval
    @action(detail=True, methods=['post'], url_path='submit-for-approval')
    def submit_for_approval(self, request, pk=None):
        instance = self.get_object()
        vendor = get_object_or_404(Vendor, user=request.user)
        
        if instance.vendor != vendor:
            return Response({
                "success": False,
                "message": "You can only submit your own services for approval"
            }, status=403)
        
        if not instance.can_be_submitted_for_approval:
            return Response({
                "success": False,
                "message": f"Cannot submit service in '{instance.status}' status"
            }, status=400)
        
        serializer = EducationServiceSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "errors": serializer.errors
            }, status=400)
        
        # Submit for approval
        if instance.submit_for_approval():
            return Response({
                "success": True,
                "message": "Service submitted for admin approval",
                "data": {
                    "id": instance.id,
                    "service_name": instance.service_name,
                    "status": instance.status,
                    "submitted_at": instance.submitted_for_approval_at
                }
            })
        
        return Response({
            "success": False,
            "message": "Failed to submit service for approval"
        }, status=400)
    
    # ==================== ADMIN ACTIONS ====================
    
    # Admin: List all services
    @action(detail=False, methods=['get'], url_path='admin-list')
    def admin_list(self, request):
        services = self.get_queryset()
        
        # Apply filters
        status_filter = request.query_params.get('status')
        vendor_id = request.query_params.get('vendor_id')
        
        if status_filter:
            services = services.filter(status=status_filter)
        if vendor_id:
            services = services.filter(vendor_id=vendor_id)
        
        page = self.paginate_queryset(services)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(services, many=True)
        return Response({
            "success": True,
            "count": services.count(),
            "services": serializer.data
        })
    
    # Admin: Get pending approvals
    @action(detail=False, methods=['get'], url_path='pending-approvals')
    def pending_approvals(self, request):
        pending_services = self.get_queryset()
        
        serializer = self.get_serializer(pending_services, many=True)
        return Response({
            "success": True,
            "count": pending_services.count(),
            "pending_services": serializer.data
        })
    
    # Admin: Approve service
    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        instance = self.get_object()
        serializer = EducationServiceApproveSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                "success": False,
                "errors": serializer.errors
            }, status=400)
        
        if instance.status != 'pending':
            return Response({
                "success": False,
                "message": f"Only services with 'pending' status can be approved. Current status: {instance.status}"
            }, status=400)
        
        # Approve the service
        instance.approve(request.user)
        
        return Response({
            "success": True,
            "message": "Service approved successfully",
            "data": {
                "id": instance.id,
                "service_name": instance.service_name,
                "status": instance.status,
                "approved_at": instance.approved_at,
                "approved_by": request.user.username if request.user else None
            }
        })
    
    # Admin: Reject service
    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        instance = self.get_object()
        serializer = EducationServiceRejectSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                "success": False,
                "errors": serializer.errors
            }, status=400)
        
        if instance.status != 'pending':
            return Response({
                "success": False,
                "message": f"Only services with 'pending' status can be rejected. Current status: {instance.status}"
            }, status=400)
        
        # Reject the service
        rejection_reason = serializer.validated_data['rejection_reason']
        instance.reject(rejection_reason)
        
        return Response({
            "success": True,
            "message": "Service rejected",
            "data": {
                "id": instance.id,
                "service_name": instance.service_name,
                "status": instance.status,
                "rejection_reason": rejection_reason,
                "rejected_at": instance.rejected_at
            }
        })
    
    # Admin/Vendor: Toggle active status
    @action(detail=True, methods=['post'], url_path='toggle-active')
    def toggle_active(self, request, pk=None):
        instance = self.get_object()
        
        # Check permissions
        if not request.user.is_superuser:
            vendor = get_object_or_404(Vendor, user=request.user)
            if instance.vendor != vendor:
                return Response({
                    "success": False,
                    "message": "You can only toggle active status for your own services"
                }, status=403)
        
        if instance.status != 'approved':
            return Response({
                "success": False,
                "message": f"Only approved services can be toggled. Current status: {instance.status}"
            }, status=400)
        
        # Toggle active status
        instance.toggle_active()
        
        return Response({
            "success": True,
            "message": f"Service {'activated' if instance.is_active else 'deactivated'} successfully",
            "data": {
                "id": instance.id,
                "service_name": instance.service_name,
                "is_active": instance.is_active,
                "status": instance.status
            }
        })
    
    # ==================== PUBLIC ACTIONS ====================
    
    # Public: List all approved and active services
    @action(detail=False, methods=['get'], url_path='public-list')
    def public_list(self, request):
        services = self.get_queryset()
        
        # Apply filters
        education_type = request.query_params.get('education_type')
        mode = request.query_params.get('mode')
        city = request.query_params.get('city')
        min_price = request.query_params.get('min_price')
        max_price = request.query_params.get('max_price')
        
        if education_type:
            services = services.filter(education_type=education_type)
        if mode:
            services = services.filter(mode_of_class=mode)
        if city:
            services = services.filter(city__icontains=city)
        if min_price:
            services = services.filter(price__gte=min_price)
        if max_price:
            services = services.filter(price__lte=max_price)
        
        page = self.paginate_queryset(services)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(services, many=True)
        return Response({
            "success": True,
            "count": services.count(),
            "services": serializer.data
        })
    
    # Public: Get service details (increments view count)
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Only show approved and active services to public
        if not request.user.is_authenticated or not request.user.is_superuser:
            if instance.status != 'approved' or not instance.is_active:
                return Response({
                    "success": False,
                    "message": "Service not found or not available"
                }, status=404)
        
        # Increment view count for public views
        if not request.user.is_authenticated or (request.user.is_authenticated and not request.user.is_superuser):
            instance.increment_views()
        
        serializer = EducationServiceSerializer(instance)
        return Response({
            "success": True,
            "service": serializer.data
        })
    
    # Public: Get filter options
    @action(detail=False, methods=['get'], url_path='filter-options')
    def filter_options(self, request):
        # Get unique cities with approved services
        cities = EducationService.objects.filter(
            status='approved', 
            is_active=True
        ).values_list('city', flat=True).distinct().order_by('city')
        
        # Get education types
        education_types = [choice[0] for choice in EducationService.EDUCATION_TYPE_CHOICES]
        
        # Get modes
        modes = [choice[0] for choice in EducationService.MODE_OF_CLASS_CHOICES]
        
        # Get price ranges
        price_stats = EducationService.objects.filter(
            status='approved', 
            is_active=True
        ).aggregate(
            min_price=models.Min('price'),
            max_price=models.Max('price'),
            avg_price=models.Avg('price')
        )
        
        return Response({
            "cities": list(cities),
            "education_types": education_types,
            "modes": modes,
            "price_range": {
                "min": float(price_stats['min_price'] or 0),
                "max": float(price_stats['max_price'] or 10000),
                "avg": float(price_stats['avg_price'] or 5000)
            }
        })
    
    # ==================== DASHBOARD & STATISTICS ====================
    
    # Vendor dashboard statistics
    @action(detail=False, methods=['get'], url_path='vendor-dashboard')
    def vendor_dashboard(self, request):
        vendor = get_object_or_404(Vendor, user=request.user)
        
        total_services = EducationService.objects.filter(vendor=vendor).count()
        
        # Status counts
        draft_services = EducationService.objects.filter(vendor=vendor, status='draft').count()
        pending_services = EducationService.objects.filter(vendor=vendor, status='pending').count()
        approved_services = EducationService.objects.filter(vendor=vendor, status='approved').count()
        rejected_services = EducationService.objects.filter(vendor=vendor, status='rejected').count()
        inactive_services = EducationService.objects.filter(vendor=vendor, status='inactive').count()
        
        # Active/Inactive
        active_services = EducationService.objects.filter(vendor=vendor, is_active=True).count()
        
        # Views
        total_views = EducationService.objects.filter(vendor=vendor).aggregate(
            total_views=models.Sum('views_count')
        )['total_views'] or 0
        
        # Featured
        featured_services = EducationService.objects.filter(vendor=vendor, is_featured=True).count()
        
        # Recent pending submissions
        recent_pending = EducationService.objects.filter(
            vendor=vendor, 
            status='pending'
        ).order_by('-submitted_for_approval_at')[:5]
        
        recent_pending_serializer = EducationServiceListSerializer(recent_pending, many=True)
        
        return Response({
            "success": True,
            "vendor": {
                "id": vendor.id,
                "business_name": vendor.business_name,
                "vendor_type": vendor.vendor_type,
                "vendor_subtype": vendor.vendor_subtype
            },
            "statistics": {
                "total_services": total_services,
                "status_breakdown": {
                    "draft": draft_services,
                    "pending_approval": pending_services,
                    "approved": approved_services,
                    "rejected": rejected_services,
                    "inactive": inactive_services
                },
                "active_services": active_services,
                "inactive_services": total_services - active_services,
                "total_views": total_views,
                "featured_services": featured_services
            },
            "recent_pending_submissions": recent_pending_serializer.data
        })
    
    # Admin dashboard statistics
    @action(detail=False, methods=['get'], url_path='admin-dashboard')
    def admin_dashboard(self, request):
        if not request.user.is_superuser:
            return Response({
                "success": False,
                "message": "Only superadmin can access admin dashboard"
            }, status=403)
        
        total_services = EducationService.objects.count()
        
        # Status counts
        draft_services = EducationService.objects.filter(status='draft').count()
        pending_services = EducationService.objects.filter(status='pending').count()
        approved_services = EducationService.objects.filter(status='approved').count()
        rejected_services = EducationService.objects.filter(status='rejected').count()
        inactive_services = EducationService.objects.filter(status='inactive').count()
        
        # Vendors with education services
        vendor_count = Vendor.objects.filter(
            vendor_type='service',
            vendor_subtype='education'
        ).count()
        
        # Top vendors by service count
        top_vendors = Vendor.objects.filter(
            vendor_type='service',
            vendor_subtype='education'
        ).annotate(
            service_count=models.Count('education_services'),
            approved_service_count=models.Count('education_services', filter=models.Q(education_services__status='approved'))
        ).order_by('-service_count')[:10]
        
        top_vendors_data = []
        for vendor in top_vendors:
            top_vendors_data.append({
                "id": vendor.id,
                "business_name": vendor.business_name,
                "total_services": vendor.service_count,
                "approved_services": vendor.approved_service_count
            })
        
        # Recent submissions
        recent_submissions = EducationService.objects.filter(
            status='pending'
        ).select_related('vendor').order_by('-submitted_for_approval_at')[:10]
        
        recent_submissions_data = []
        for service in recent_submissions:
            recent_submissions_data.append({
                "id": service.id,
                "service_name": service.service_name,
                "vendor_name": service.vendor.business_name,
                "submitted_at": service.submitted_for_approval_at,
                "city": service.city
            })
        
        return Response({
            "success": True,
            "statistics": {
                "total_services": total_services,
                "status_breakdown": {
                    "draft": draft_services,
                    "pending_approval": pending_services,
                    "approved": approved_services,
                    "rejected": rejected_services,
                    "inactive": inactive_services
                },
                "vendor_count": vendor_count,
                "approval_rate": (approved_services / (approved_services + rejected_services)) * 100 if (approved_services + rejected_services) > 0 else 0
            },
            "top_vendors": top_vendors_data,
            "recent_submissions": recent_submissions_data
        })
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404
from django.db import models

from ecommerce.models.vendor import Vendor
from ecommerce.permissions import IsSuperAdmin, IsVendorAuthenticated

class VendorMyServicesView(APIView):
    """Get all services for a vendor (across all service types)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsVendorAuthenticated]
    
    def get(self, request):
        vendor = get_object_or_404(Vendor, user=request.user)
        
        # Import all service models
        from ecommerce.models.education_service import EducationService
        # from ecommerce.models.healthcare_service import HealthcareService
        # ... import other service models
        
        # Collect services from all service types
        all_services = []
        
        # Education services
        education_services = EducationService.objects.filter(vendor=vendor)
        for service in education_services:
            all_services.append({
                'id': service.id,
                'service_type': 'education',
                'service_name': service.service_name,
                'status': service.status,
                'created_at': service.created_at,
                'is_active': service.is_active,
                'price': float(service.price)
            })
        
        # Add other service types similarly
        # healthcare_services = HealthcareService.objects.filter(vendor=vendor)
        # for service in healthcare_services:
        #     all_services.append({...})
        
        # Sort by creation date
        all_services.sort(key=lambda x: x['created_at'], reverse=True)
        
        # Statistics
        total_services = len(all_services)
        approved_services = len([s for s in all_services if s['status'] == 'approved'])
        pending_services = len([s for s in all_services if s['status'] == 'pending'])
        draft_services = len([s for s in all_services if s['status'] == 'draft'])
        
        return Response({
            'success': True,
            'vendor': {
                'id': vendor.id,
                'business_name': vendor.business_name,
                'vendor_subtype': vendor.vendor_subtype
            },
            'statistics': {
                'total_services': total_services,
                'approved': approved_services,
                'pending': pending_services,
                'draft': draft_services
            },
            'services': all_services
        })

class AdminPendingServicesView(APIView):
    """Get all pending services across all service types (for admin)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdmin]
    
    def get(self, request):
        # Import all service models
        from ecommerce.models.education_service import EducationService
        # from ecommerce.models.healthcare_service import HealthcareService
        # ... import other service models
        
        all_pending_services = []
        
        # Education services
        education_pending = EducationService.objects.filter(status='pending').select_related('vendor')
        for service in education_pending:
            all_pending_services.append({
                'id': service.id,
                'service_type': 'education',
                'service_name': service.service_name,
                'vendor_name': service.vendor.business_name,
                'vendor_id': service.vendor.id,
                'submitted_at': service.submitted_for_approval_at,
                'city': service.city,
                'price': float(service.price)
            })
        
        # Add other service types similarly
        # healthcare_pending = HealthcareService.objects.filter(status='pending').select_related('vendor')
        # for service in healthcare_pending:
        #     all_pending_services.append({...})
        
        # Sort by submission date
        all_pending_services.sort(key=lambda x: x['submitted_at'] if x['submitted_at'] else '', reverse=True)
        
        # Count by service type
        service_type_counts = {}
        for service in all_pending_services:
            service_type = service['service_type']
            service_type_counts[service_type] = service_type_counts.get(service_type, 0) + 1
        
        return Response({
            'success': True,
            'total_pending': len(all_pending_services),
            'service_type_counts': service_type_counts,
            'pending_services': all_pending_services
        })

class ServiceTypesView(APIView):
    """Get all service types available in the system"""
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        service_types = [
            {
                'type': 'education',
                'name': 'Education Services',
                'description': 'Schools, Coaching, Tuitions, Online Courses',
                'vendor_subtype': 'education',
                'icon': 'FaSchool',
                'endpoint': '/api/ecommerce/services/education/'
            },
            {
                'type': 'healthcare',
                'name': 'Healthcare Services',
                'description': 'Hospitals, Clinics, Diagnostics, Pharmacy',
                'vendor_subtype': 'healthcare',
                'icon': 'MdHealthAndSafety',
                'endpoint': '/api/ecommerce/services/healthcare/'
            },
            {
                'type': 'gym',
                'name': 'Gym & Fitness',
                'description': 'Gyms, Yoga, Fitness Centers, Personal Training',
                'vendor_subtype': 'gym',
                'icon': 'GiWeightLiftingUp',
                'endpoint': '/api/ecommerce/services/gym/'
            },
            {
                'type': 'salon',
                'name': 'Salon & Beauty',
                'description': 'Salons, Spa, Beauty Parlors, Barber Shops',
                'vendor_subtype': 'salon',
                'icon': 'GiScissors',
                'endpoint': '/api/ecommerce/services/salon/'
            },
            {
                'type': 'real_estate',
                'name': 'Real Estate',
                'description': 'Property Dealers, Builders, Rental Services',
                'vendor_subtype': 'real_estate',
                'icon': 'MdRealEstateAgent',
                'endpoint': '/api/ecommerce/services/real-estate/'
            },
            {
                'type': 'travel',
                'name': 'Travel Agency',
                'description': 'Tour Packages, Tickets, Hotels, Transportation',
                'vendor_subtype': 'travel_agency',
                'icon': 'FaPlane',
                'endpoint': '/api/ecommerce/services/travel/'
            },
            {
                'type': 'finance',
                'name': 'Finance Services',
                'description': 'Loans, Insurance, Investment, Accounting',
                'vendor_subtype': 'finance',
                'icon': 'FaMoneyCheckAlt',
                'endpoint': '/api/ecommerce/services/finance/'
            },
            {
                'type': 'tech',
                'name': 'Technology Services',
                'description': 'IT Services, Software Development, Repair',
                'vendor_subtype': 'tech_industry',
                'icon': 'FaUserTie',
                'endpoint': '/api/ecommerce/services/tech/'
            },
            {
                'type': 'hotel',
                'name': 'Hotel & Restaurant',
                'description': 'Hotels, Restaurants, Catering, Event Spaces',
                'vendor_subtype': 'hotel',
                'icon': 'FaHotel',
                'endpoint': '/api/ecommerce/services/hotel/'
            },
            {
                'type': 'professional',
                'name': 'Professional Services',
                'description': 'Consulting, Legal, CA, Architects, Interior',
                'vendor_subtype': 'professional',
                'icon': 'FaUserTie',
                'endpoint': '/api/ecommerce/services/professional/'
            },
            {
                'type': 'workplace',
                'name': 'Work Place Services',
                'description': 'Office Spaces, Coworking, Meeting Rooms',
                'vendor_subtype': 'work_place',
                'icon': 'RiShoppingBag3Fill',
                'endpoint': '/api/ecommerce/services/workplace/'
            }
        ]
        
        return Response({
            'success': True,
            'service_types': service_types,
            'total_types': len(service_types)
        })
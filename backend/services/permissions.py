# service/permissions.py
from rest_framework import permissions
from services.models.real_estate import RealEstateProperty
from ecommerce.models.vendor import Vendor

class IsVendorOwner(permissions.BasePermission):
    """
    Permission to check if user owns the property
    """
    def has_object_permission(self, request, view, obj):
        # Check if user is a vendor and owns the property
        try:
            vendor = Vendor.objects.get(user=request.user)
            if isinstance(obj, RealEstateProperty):
                return obj.vendor == vendor
            # For PropertyImage, check through property
            elif hasattr(obj, 'property'):
                return obj.property.vendor == vendor
        except Vendor.DoesNotExist:
            return False
        return False

class IsVendorOrReadOnly(permissions.BasePermission):
    """
    Permission to allow vendors to create/edit, others to read only
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Check if user is a vendor
        try:
            Vendor.objects.get(user=request.user)
            return True
        except Vendor.DoesNotExist:
            return False

class IsServiceVendor(permissions.BasePermission):
    """
    Permission to check if user is a service vendor
    """
    def has_permission(self, request, view):
        try:
            vendor = Vendor.objects.get(user=request.user)
            return vendor.vendor_type == 'service' and vendor.vendor_subtype == 'real_estate'
        except Vendor.DoesNotExist:
            return False
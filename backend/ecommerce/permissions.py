# ecommerce/permissions.py
from rest_framework import permissions
from ecommerce.models.vendor import Vendor

class IsVendorAuthenticated(permissions.BasePermission):
    """
    Check if user has a vendor profile and is approved.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        try:
            vendor = request.user.vendor
            return vendor.is_approved and vendor.status == 'active'
        except Vendor.DoesNotExist:
            return False


class IsAdminUser(permissions.BasePermission):
    """
    Check if user is admin/superadmin based on role
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ["superadmin", "admin"]
        )


class IsSuperAdmin(permissions.BasePermission):
    """
    Check if user is superadmin (with multiple checks)
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (
                request.user.role == "superadmin" or 
                request.user.is_superuser or 
                request.user.is_staff
            )
        )
    
class IsCustomer(permissions.BasePermission):
    """
    Check if user is customer
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'customer')   

    
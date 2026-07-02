# users/utils/permissions.py

from rest_framework.permissions import BasePermission
""" 
class IsSuperAdmin(BasePermission):
   
    # Allow only superadmin.
    

    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and getattr(request.user, "user_type", "") == "superadmin"
        )
 """

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            (request.user.role == "superadmin" or request.user.is_staff or request.user.is_superuser)
        )


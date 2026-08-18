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


# ecommerce/permissions.py me is class ko add karo (IsSuperAdmin ke saath, alag se)

from rest_framework.permissions import BasePermission


class HasEmployeePagePermission(BasePermission):
    """
    View me `page_key = "<route>"` set karo (jo frontend menuItems ke 'to' se match kare).
    Employee ke alawa sabko (superadmin/branch/vendor etc.) full access milta hai —
    ye class sirf role='employee' ke liye restrict karti hai.
    """
    action_map = {
        'GET': None,          # view access can_view se already control hota hai
        'POST': 'can_add',
        'PUT': 'can_edit',
        'PATCH': 'can_edit',
        'DELETE': 'can_delete',
    }

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if getattr(user, 'role', None) != 'employee':
            return True  # superadmin / branch / other roles unaffected

        page_key = getattr(view, 'page_key', None)
        if not page_key:
            return True  # view opt-in nahi kiya

        employee = getattr(user, 'employee_profile', None)
        if not employee:
            return False

        perm = employee.permissions.filter(page_key=page_key).first()
        if not perm or not perm.can_view:
            return False

        required_field = self.action_map.get(request.method)
        if required_field is None:
            return True
        return getattr(perm, required_field, False)
    
    
# ecommerce/permissions.py me is class ko add karo
# (IsSuperAdmin aur HasEmployeePagePermission ke saath, alag se)

from rest_framework.permissions import BasePermission


class IsSuperAdminOrPagePermittedEmployee(BasePermission):
    """
    ViewSet-based views (jaise BranchViewSet) ke liye:
    - superadmin -> hamesha full access
    - employee   -> sirf agar EmployeePermission me is view.page_key ke liye
                    can_view=True hai, aur action ke hisaab se can_add/can_edit/can_delete
    - baaki koi bhi role -> access nahi (jaisa pehle sirf-superadmin restriction tha)

    request.method ki jagah view.action use karta hai, taaki custom @action
    (jaise change_status) bhi sahi se map ho (edit ke equivalent).
    """
    action_map = {
        'list': None,
        'retrieve': None,
        'stats': None,
        'create': 'can_add',
        'update': 'can_edit',
        'partial_update': 'can_edit',
        'destroy': 'can_delete',
        'change_status': 'can_edit',
    }

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if getattr(user, 'role', None) == 'superadmin':
            return True

        if getattr(user, 'role', None) == 'employee':
            page_key = getattr(view, 'page_key', None)
            if not page_key:
                return False

            employee = getattr(user, 'employee_profile', None)
            if not employee:
                return False

            perm = employee.permissions.filter(page_key=page_key).first()
            if not perm or not perm.can_view:
                return False

            required_field = self.action_map.get(getattr(view, 'action', None))
            if required_field is None:
                return True
            return getattr(perm, required_field, False)

        return False  # branch/vendor/customer etc. — pehle bhi access nahi tha   
    
# ecommerce/permissions.py  (file ke SABSE NEECHE, add karo)

VIEW_ACTIONS = ["list", "retrieve", "me", "stats"]
ADD_ACTIONS = ["create"]
EDIT_ACTIONS = ["update", "partial_update"]
DELETE_ACTIONS = ["destroy"]

METHOD_TO_FIELD = {
    "GET": "can_view",
    "POST": "can_add",
    "PATCH": "can_edit",
    "PUT": "can_edit",
    "DELETE": "can_delete",
}


def get_employee(request):
    user = request.user
    if not user or not user.is_authenticated:
        return None
    if getattr(user, "role", None) != "employee":
        return None
    return getattr(user, "employee_profile", None)


def resolve_perm_field(view, request):
    action = getattr(view, "action", None)
    override_map = getattr(view, "action_permission_map", {})

    if action and action in override_map:
        return override_map[action]
    if action in VIEW_ACTIONS:
        return "can_view"
    if action in ADD_ACTIONS:
        return "can_add"
    if action in EDIT_ACTIONS:
        return "can_edit"
    if action in DELETE_ACTIONS:
        return "can_delete"
    if action:
        return "can_edit"
    return METHOD_TO_FIELD.get(request.method, "can_view")


class HasEmployeePagePermission(BasePermission):
    def has_permission(self, request, view):
        employee = get_employee(request)
        if not employee:
            return False
        page_key = getattr(view, "page_key", None)
        if not page_key:
            return False
        field = resolve_perm_field(view, request)
        perm = employee.permissions.filter(page_key=page_key).first()
        if not perm:
            return False
        return bool(getattr(perm, field, False))


class IsSuperAdminOrPagePermittedEmployee(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        role = getattr(user, "role", None)
        if role == "superadmin":
            return True
        if role == "employee":
            return HasEmployeePagePermission().has_permission(request, view)
        return False     
    
    
class IsSuperAdminOrBranchOrPagePermittedEmployee(BasePermission):
    """
    - Superadmin => full access
    - Branch/Vendor roles => full access (jaisa pehle IsAuthenticated se tha, koi change nahi)
    - Employee => sirf page_key permission ke hisaab se
    """
    BRANCH_ROLES = ("branch", "branch_customer", "branch_agent", "branch_both", "vendor")

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        role = getattr(user, "role", None)

        if role == "superadmin":
            return True

        if role in self.BRANCH_ROLES:
            return True

        if role == "employee":
            return HasEmployeePagePermission().has_permission(request, view)

        return False    
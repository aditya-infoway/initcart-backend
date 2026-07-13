# pos/utils/branch_validation.py - NEW FILE

from pos.models.branch import Branch


def is_branch_location_complete(branch) -> bool:
    """
    Check if branch has all required location fields filled.
    Returns True if city, state, and country are all filled.
    """
    if not branch:
        return False
    
    city = getattr(branch, 'city', None)
    state = getattr(branch, 'state', None)
    country = getattr(branch, 'country', None)
    
    return bool(city and state and country)


def get_branch_from_user(user):
    """Get branch from user, returns None if not found"""
    try:
        return Branch.objects.get(user=user)
    except Branch.DoesNotExist:
        return None


def get_superadmin_branch_from_user(user):
    """Get superadmin's branch (auto-created on login)"""
    try:
        return Branch.objects.get(user=user)
    except Branch.DoesNotExist:
        return None
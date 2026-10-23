# ecommerce/utils/return_helpers.py  (FULL FILE)
from datetime import timedelta
from django.utils import timezone

DEFAULT_RETURN_DAYS = 7


NO_RETURN_POLICIES = ("no return", "exchange only")

def get_return_days(order_item):
    product = order_item.product
    policy = (getattr(product, "return_policy", "") or "").strip().lower()
    if policy in NO_RETURN_POLICIES:
        return 0

    days = getattr(order_item, "return_days", None)
    if days is None:
        days = getattr(product, "return_days", None)
    return DEFAULT_RETURN_DAYS if days is None else days


def get_return_deadline(order_item):
    if not order_item.delivered_at:
        return None
    return order_item.delivered_at + timedelta(days=get_return_days(order_item))


def is_order_item_returnable(order_item):
    """
    Return window order_item.delivered_at se start hota hai (per-item, per-vendor)
    aur din product ki return policy se aate hain.
    """
    if order_item.item_status != 'delivered':
        return False, "Item is not delivered yet"
    if not order_item.delivered_at:
        return False, "Delivery date not recorded"

    days = get_return_days(order_item)
    if days <= 0:
        return False, "This product is not returnable"

    if timezone.now() > get_return_deadline(order_item):
        return False, f"Return window ({days} days) has expired"

    if (order_item.returned_quantity or 0) >= order_item.quantity:
        return False, "Item already returned"

    from ecommerce.models.return_request import ReturnRequest
    active = ReturnRequest.objects.filter(
        order_item=order_item,
        status__in=['requested', 'vendor_approved', 're_requested', 'admin_approved']
    ).exists()
    if active:
        return False, "A return request is already active for this item"

    return True, None
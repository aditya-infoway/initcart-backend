# ecommerce/utils/return_helpers.py
from datetime import timedelta
from django.utils import timezone

RETURN_WINDOW_DAYS = 7

def is_order_item_returnable(order_item):
    order = order_item.order
    if order_item.item_status != 'delivered':
        return False, "Item is not delivered yet"
    if not order.delivered_at:
        return False, "Delivery date not recorded"
    if timezone.now() > order.delivered_at + timedelta(days=RETURN_WINDOW_DAYS):
        return False, "Return window (7 days) has expired"

    from ecommerce.models.return_request import ReturnRequest
    active = ReturnRequest.objects.filter(
        order_item=order_item,
        status__in=['requested', 'vendor_approved', 're_requested', 'admin_approved']
    ).exists()
    if active:
        return False, "A return request is already active for this item"
    return True, None
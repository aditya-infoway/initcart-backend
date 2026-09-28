# ecommerce/utils/return_helpers.py  (FULL FILE — replace your existing one with this)
from datetime import timedelta
from django.utils import timezone

RETURN_WINDOW_DAYS = 7

def is_order_item_returnable(order_item):
    """
    ✅ FIX: the 7-day window is now keyed off order_item.delivered_at —
    the moment THIS specific item (from its own vendor) was marked
    delivered — instead of order.delivered_at, which only gets set once
    EVERY vendor's item on a multi-vendor order has been delivered. A
    customer whose one product arrived on day 1 shouldn't have to wait
    for a completely different vendor's item to arrive before their
    return window even starts.
    """
    if order_item.item_status != 'delivered':
        return False, "Item is not delivered yet"
    if not order_item.delivered_at:
        return False, "Delivery date not recorded"
    if timezone.now() > order_item.delivered_at + timedelta(days=RETURN_WINDOW_DAYS):
        return False, "Return window (7 days) has expired"

    from ecommerce.models.return_request import ReturnRequest
    active = ReturnRequest.objects.filter(
        order_item=order_item,
        status__in=['requested', 'vendor_approved', 're_requested', 'admin_approved']
    ).exists()
    if active:
        return False, "A return request is already active for this item"
    return True, None
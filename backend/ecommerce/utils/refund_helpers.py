# ecommerce/utils/refund_helpers.py  (FULL FILE — replace your existing one with this)
from decimal import Decimal, ROUND_HALF_UP
import razorpay
from django.conf import settings
from django.utils import timezone

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def calculate_refund_amount(order_item, return_quantity):
    """
    Proportional refund for the returned quantity — handles partial
    returns correctly (e.g. customer ordered 3, returning only 1).
    order_item.total_price already covers the FULL ordered quantity.
    """
    if not order_item.quantity:
        return Decimal('0.00')
    per_unit = order_item.total_price / order_item.quantity
    amount = (per_unit * return_quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return amount


def create_refund_if_online(return_request):
    """
    Call this right after a ReturnRequest's status becomes 'vendor_approved'
    or 'admin_approved'. Only online (razorpay) orders get a refund row —
    COD orders are not touched here (vendor handles cash return directly).

    Idempotent: calling it twice for the same return_request never creates
    a duplicate row.
    """
    from ecommerce.models.refund import OrderRefund

    order = return_request.order
    if order.payment_method != 'razorpay':
        return None

    # already created earlier (e.g. re-triggered by mistake) — don't duplicate
    existing = OrderRefund.objects.filter(return_request=return_request).first()
    if existing:
        return existing

    amount = calculate_refund_amount(return_request.order_item, return_request.quantity)
    if amount <= 0:
        return None

    refund = OrderRefund.objects.create(
        return_request=return_request,
        order=order,
        order_item=return_request.order_item,
        refund_amount=amount,
        status='pending',
    )

    # No razorpay_payment_id on the order → flag immediately instead of
    # silently sitting in "pending" forever with no way to ever succeed.
    if not order.razorpay_payment_id:
        refund.status = 'failed'
        refund.failure_reason = "No Razorpay payment id found on this order"
        refund.save(update_fields=['status', 'failure_reason'])

    return refund


def process_refund(refund):
    """
    Calls Razorpay's refund API for this OrderRefund and updates its status.
    On success, also:
      - marks the order_item as 'refunded'
      - marks the whole order as 'refunded' if every item on it is now refunded
      - reverses the MLM commission (upline / pos / society) + the referral
        agent's total_sales that were credited for this item — see
        mlm/utils/commission_reversal.py
    Returns (success: bool, message: str). Never raises — all Razorpay/network
    errors are caught and stored on the refund record so admin can retry.
    """
    if refund.status == 'processed':
        return False, "This refund has already been processed"

    order = refund.order
    if not order.razorpay_payment_id:
        refund.status = 'failed'
        refund.failure_reason = "No Razorpay payment id found on this order"
        refund.save(update_fields=['status', 'failure_reason'])
        return False, refund.failure_reason

    amount_paise = int(refund.refund_amount * 100)

    try:
        rp_response = client.payment.refund(order.razorpay_payment_id, {
            'amount': amount_paise,
            'speed': 'normal',
            'notes': {
                'refund_id': refund.refund_id,
                'return_id': refund.return_request.return_id,
                'order_number': order.order_number,
            },
        })

        refund.razorpay_refund_id = rp_response.get('id')
        refund.status = 'processed'
        refund.processed_at = timezone.now()
        refund.failure_reason = None
        refund.save()

        # reflect on the order item so order pages can show "Refunded"
        refund.order_item.item_status = 'refunded'
        refund.order_item.save(update_fields=['item_status'])

        # ✅ If every item on this order is now refunded, mark the whole
        # order as refunded too — reports/order lists key off order_status.
        if not order.items.exclude(item_status='refunded').exists():
            if order.order_status != 'refunded':
                order.order_status = 'refunded'
                order.save(update_fields=['order_status'])

        # ✅ Reverse MLM commission + agent total_sales for this returned item
        from utils.commission_reversal import reverse_commission_for_return
        reverse_commission_for_return(refund)

        return True, "Refund processed successfully"

    except Exception as e:
        refund.status = 'failed'
        refund.failure_reason = str(e)
        refund.save(update_fields=['status', 'failure_reason'])
        return False, f"Razorpay refund failed: {str(e)}"
# ecommerce/utils/refund_helpers.py
import logging
from decimal import Decimal, ROUND_HALF_UP

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

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


def create_refund_for_return(return_request):
    """
    Call right after a ReturnRequest becomes 'vendor_approved' / 'admin_approved'.

      - razorpay order -> OrderRefund(refund_type='online')  (admin triggers Razorpay)
      - cod order      -> OrderRefund(refund_type='cod')     (admin pays manually from a
                          refund bank account; customer's bank details are on
                          return_request.bank_detail)

    Idempotent: calling it twice for the same return_request never creates a duplicate.
    """
    from ecommerce.models.refund import OrderRefund

    order = return_request.order
    if order.payment_method == 'razorpay':
        refund_type = 'online'
    elif order.payment_method == 'cod':
        refund_type = 'cod'
    else:
        return None

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
        refund_type=refund_type,
        refund_amount=amount,
        status='pending',
    )

    if refund_type == 'online' and not order.razorpay_payment_id:
        refund.status = 'failed'
        refund.failure_reason = "No Razorpay payment id found on this order"
        refund.save(update_fields=['status', 'failure_reason'])

    return refund


# Backward-compatible alias — return_views.py still imports this name.
create_refund_if_online = create_refund_for_return


def finalize_refund_success(refund):
    """
    Shared by ONLINE (after Razorpay success) and COD (after manual payout recorded).
      - increments order_item.returned_quantity by the RETURNED quantity and flips
        item_status to 'refunded' only once the FULL ordered quantity is returned
      - reverses MLM commission (upline / pos / society) + referral agent's
        total_sales — see utils/commission_reversal.py
    Caller must already have set refund.status='processed'.
    """
    order_item = refund.order_item
    returned_qty = refund.return_request.quantity
    order_item.returned_quantity = (order_item.returned_quantity or 0) + returned_qty
    update_fields = ['returned_quantity']
    if order_item.returned_quantity >= order_item.quantity:
        order_item.item_status = 'refunded'
        update_fields.append('item_status')
    order_item.save(update_fields=update_fields)

    from utils.commission_reversal import reverse_commission_for_return
    reverse_commission_for_return(refund)


def process_refund(refund):
    """
    ONLINE refunds only: calls Razorpay's refund API and updates status.
    COD refunds are paid manually (AdminCODRefundPayAPIView).
    Returns (success: bool, message: str). Never raises.
    """
    if refund.refund_type == 'cod':
        return False, "COD refunds are paid manually from the COD Refunds page"

    if refund.status == 'processed':
        return False, "This refund has already been processed"

    order = refund.order
    if not order.razorpay_payment_id:
        refund.status = 'failed'
        refund.failure_reason = "No Razorpay payment id found on this order"
        refund.save(update_fields=['status', 'failure_reason'])
        return False, refund.failure_reason

    amount_paise = int(refund.refund_amount * 100)

    # 1) Razorpay call — only THIS step may mark the refund as failed
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
    except Exception as e:
        refund.status = 'failed'
        refund.failure_reason = str(e)
        refund.save(update_fields=['status', 'failure_reason'])
        return False, f"Razorpay refund failed: {str(e)}"

    refund.razorpay_refund_id = rp_response.get('id')
    refund.status = 'processed'
    refund.processed_at = timezone.now()
    refund.failure_reason = None
    refund.save()

    # 2) Post-processing — money already moved, so never flip back to 'failed'
    try:
        with transaction.atomic():
            finalize_refund_success(refund)
    except Exception as e:
        logger.exception("Post-refund processing failed for %s", refund.refund_id)
        refund.failure_reason = f"Refund sent via Razorpay but post-processing failed: {e}"
        refund.save(update_fields=['failure_reason'])
        return True, "Refund sent, but item/commission update failed — please check manually"

    return True, "Refund processed successfully"
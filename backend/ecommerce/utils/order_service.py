#ecommerce/utils/order_service.py  (FULL FILE — replace your existing one with this)
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import F
from decimal import Decimal
from ecommerce.models.order import Order, Cart
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings

from utils.profit_engine import calculate_profit_distribution
from utils.commision_engine import distribute_commission



def process_order_from_pending(pending, payment_data=None):
    """
    Production-safe order processor
    - Idempotent
    - Atomic
    - Stock safe
    - Amount verified
    """

    with transaction.atomic():

        #  Lock pending checkout
        pending = (
            type(pending)
            .objects
            .select_for_update()
            .get(id=pending.id)
        )

        #  Idempotency check (inside transaction)
        if Order.objects.filter(
            razorpay_order_id=pending.razorpay_order_id
        ).exists():
            return "already_processed"

        if pending.is_expired():
            pending.delete()
            raise ValidationError("Checkout expired.")

        #  Lock cart
        cart = (
            Cart.objects
            .select_for_update()
            .select_related("user")
            .get(user=pending.user)
        )

        cart_items = cart.items.select_related("product").all()

        if not cart_items.exists():
            raise ValidationError("Cart empty.")

        subtotal = Decimal(cart.get_subtotal())
        discount = Decimal(cart.get_coupon_discount(pending.coupon_code))
        loyalty_discount = Decimal(
            cart.get_loyalty_discount(pending.loyalty_points_to_use)
        )

        final_amount = subtotal - discount - loyalty_discount

        if final_amount <= 0:
            raise ValidationError("Invalid final amount.")

        #  Razorpay amount verification
        if payment_data:
            razorpay_amount = Decimal(payment_data.get("amount")) / Decimal(100)

            if razorpay_amount != final_amount:
                raise ValidationError("Amount mismatch detected.")

        #  Create Order
        order = Order.objects.create(
            user=pending.user,
            razorpay_order_id=pending.razorpay_order_id,
            total_amount=final_amount,
            billing_address_id=pending.billing_address_id,
            shipping_address_id=pending.shipping_address_id,
            notes=pending.notes,
            payment_status="paid" if payment_data else "cod",
        )

        # 🛒 Move cart items safely
        for item in cart_items:

            if item.product.stock < item.quantity:
                raise ValidationError(
                    f"Insufficient stock for {item.product.name}"
                )

            order.items.create(
                product=item.product,
                quantity=item.quantity,
                price=item.price,
            )

            #  Atomic stock update
            item.product.stock = F("stock") - item.quantity
            item.product.save(update_fields=["stock"])

        # Clear cart
        cart.items.all().delete()

        # Delete pending checkout
        pending.delete()

        return order


########  M L M ###########

# ecommerce/utils/order_service.py

def update_agent_sales(user, amount, from_delivery=False, add_sales=True, order=None):
    """
    add_sales=False lets a caller check/apply the activation threshold
    (is_active_agent / minimum_achieved_at) WITHOUT incrementing total_sales
    again — used when total_sales for this order was already accounted for
    by another path (see the self-purchase note in ecommerce/signals.py).

    order: the Order instance whose delivery is triggering this call —
    passed through so, if this call is what crosses the threshold, we can
    record EXACTLY which order did it (minimum_achieved_order). That's what
    is_agent_active() later uses to skip commission only on that exact
    order — ID-based, no timestamp race.
    """
    from mlm.models.agent import Agent
    from mlm.models.mlm_settings import MLMSettings

    try:
        agent = Agent.objects.get(user=user, status="approved")
    except Agent.DoesNotExist:
        return False

    amount = Decimal(str(amount))

    if add_sales and amount > Decimal("0"):
        Agent.objects.filter(pk=agent.pk).update(
            total_sales=F("total_sales") + amount
        )
        agent.refresh_from_db()
        print(f"📊 Sales | {user.username} | +₹{amount} | Total: ₹{agent.total_sales}")
    elif not add_sales:
        agent.refresh_from_db()
        print(f"📊 Sales | {user.username} | skipped increment (already accounted for) | Total: ₹{agent.total_sales}")

    settings = MLMSettings.objects.first()
    if not settings:
        return False

    if agent.total_sales >= settings.minimum_sale_amount:
        changed = []
        if not agent.is_active_agent:
            agent.is_active_agent = True
            changed.append("is_active_agent")
            print(f"✅ ACTIVATED: {user.username}")
        if not agent.minimum_achieved_at:
            agent.minimum_achieved_at = timezone.now()
            changed.append("minimum_achieved_at")
            print(f"⏰ minimum_achieved_at set: {user.username}")
            # ✅ NAYA: exact achieving order record karo
            if order is not None:
                agent.minimum_achieved_order = order
                changed.append("minimum_achieved_order")
                print(f"🎯 minimum_achieved_order set: {user.username} → {order.order_number}")
        if changed:
            agent.save(update_fields=changed)
        return True

    return False

def process_mlm_commission(order):
    """
    Commission on DELIVERY only.

    - Inactive seller → skipped, upline earns
    - Jis order se minimum achieve hua → seller skip, upline earns
    - Agle order se → seller khud commission lega

    mlm_commission_processed flag caller (signals._handle_order) set karta hai.
    """
    from django.db.models import Sum
    from utils.profit_engine import calculate_profit_distribution
    from utils.commision_engine import distribute_commission

    print(f"\n process_mlm_commission: {order.order_number}")

    if not order.referral_agent:
        print(f" No referral_agent: {order.order_number}")
        return

    agent = order.referral_agent
    agent.refresh_from_db()
    agent.user.refresh_from_db()

    print(f"   Agent: {agent.user.username} | status={agent.status} | "
          f"is_active={agent.is_active_agent} | "
          f"minimum_achieved_at={agent.minimum_achieved_at}")

    total_platform_profit = (
        order.items.aggregate(total=Sum("platform_profit"))["total"] or Decimal("0")
    )

    if total_platform_profit <= Decimal("0"):
        print(f"⚠️ Zero platform_profit — no commission for {order.order_number}")
        return

    #  current_order pass karo — seller ke activation-order check ke liye
    result = calculate_profit_distribution(
        total_profit=total_platform_profit,
        seller_user=agent.user,
        current_order=order,        # ← YAHI FIX HAI
    )

    if not result.get("upline_payouts"):
        print(f"⏭️ No eligible upline agents for {order.order_number}")
        return

    distribute_commission(order, result)
    print(f"✅ Commission distributed: {order.order_number} | "
          f"{len(result['upline_payouts'])} agents credited")
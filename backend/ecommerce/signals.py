# ecommerce/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal

from ecommerce.models.customer import CustomerProfile
from ecommerce.models.order import Order, OrderItem

_PROCESSING_ORDERS = set()
_PROCESSING_ITEMS = set()


@receiver(post_save, sender=Order)
def handle_order_status_change(sender, instance, created, update_fields, **kwargs):
    if instance.pk in _PROCESSING_ORDERS:
        return
    _PROCESSING_ORDERS.add(instance.pk)
    try:
        _update_customer_stats(instance)
    except Exception as e:
        print(f" Signal error for order {instance.pk}: {e}")
        import traceback; traceback.print_exc()
    finally:
        _PROCESSING_ORDERS.discard(instance.pk)


@receiver(post_save, sender=OrderItem)
def handle_order_item_delivered(sender, instance, created, **kwargs):
    if created:
        return
    if instance.pk in _PROCESSING_ITEMS:
        return
    if instance.item_status != 'delivered':
        return
    if instance.mlm_commission_processed:
        return

    _PROCESSING_ITEMS.add(instance.pk)
    try:
        _handle_item_commission(instance)
    except Exception as e:
        print(f" Item signal error for item {instance.pk}: {e}")
        import traceback; traceback.print_exc()
    finally:
        _PROCESSING_ITEMS.discard(instance.pk)


def _sync_self_purchase_agent_sales(customer, activation_item=None):
    """
    ✅ FIX: total_price ka sum nahi — net_amount ka sum. Partial return
    ab item ka sirf proportional amount hi minus karta hai, poora
    total_price nahi. Full-return items (item_status != 'delivered')
    pehle hi filter se bahar hain; is-bich wale partial-return items
    (status abhi 'delivered' hai, returned_quantity > 0) ke liye
    net_amount khud proportional reduction de deta hai.
    """
    from mlm.models.agent import Agent
    from mlm.models.mlm_settings import MLMSettings
    from django.utils import timezone

    try:
        agent = Agent.objects.get(user=customer, status="approved")
    except Agent.DoesNotExist:
        return None

    delivered_items = OrderItem.objects.filter(
        order__customer=customer,
        item_status="delivered",
    )
    delivered_total = sum(
        (item.net_amount for item in delivered_items), Decimal("0.00")
    )

    changed = []
    if delivered_total != agent.total_sales:
        agent.total_sales = delivered_total
        changed.append("total_sales")

    mlm_settings = MLMSettings.objects.first()
    if mlm_settings and agent.total_sales >= mlm_settings.minimum_sale_amount:
        if not agent.is_active_agent:
            agent.is_active_agent = True
            changed.append("is_active_agent")
            print(f"✅ Agent ACTIVATED (self-purchase sync): {customer.username}")
        if not agent.minimum_achieved_at:
            agent.minimum_achieved_at = timezone.now()
            changed.append("minimum_achieved_at")
            if activation_item is not None:
                agent.minimum_achieved_item = activation_item
                changed.append("minimum_achieved_item")

    if changed:
        agent.save(update_fields=changed)
        print(f"✅ Agent sales synced: {customer.username} → ₹{agent.total_sales} "
              f"(active={agent.is_active_agent})")

    return agent


def _handle_item_commission(item):
    from ecommerce.utils.order_service import update_agent_sales, process_item_mlm_commission

    try:
        fresh_item = OrderItem.objects.select_related('order').get(pk=item.pk)
    except OrderItem.DoesNotExist:
        return

    order = fresh_item.order
    print(f"\n ITEM DELIVERED: item={fresh_item.id} product={fresh_item.product_name} "
          f"order={order.order_number}")

    if fresh_item.mlm_commission_processed:
        print(f" Already processed (DB check): item {fresh_item.id}")
        return

    referral_agent = order.referral_agent
    if not referral_agent:
        from ecommerce.utils.agent_order_utils import resolve_referral_agent
        referral_agent = resolve_referral_agent(order.customer)
        if referral_agent:
            Order.objects.filter(pk=order.pk).update(referral_agent=referral_agent)
            order.referral_agent = referral_agent
            print(f" Auto-linked: {referral_agent.user.username} → {order.order_number}")

    if not referral_agent:
        print(f" No referral agent for item {fresh_item.id}")
        return

    item_profit = Decimal(str(fresh_item.platform_profit or 0))
    if item_profit <= Decimal("0"):
        print(f"  platform_profit is ZERO for item {fresh_item.id} — nothing to commission")
        OrderItem.objects.filter(pk=fresh_item.pk).update(mlm_commission_processed=True)
        return

    is_self_purchase = referral_agent.user_id == order.customer_id

    if is_self_purchase:
        print(f"  Self-purchase item — syncing total_sales directly from delivered items")
        _sync_self_purchase_agent_sales(order.customer, activation_item=fresh_item)
        update_agent_sales(referral_agent.user, fresh_item.total_price,
                        from_delivery=True, add_sales=False, item=fresh_item)
    else:
        update_agent_sales(
            referral_agent.user,
            fresh_item.total_price,
            from_delivery=True,
            add_sales=True,
            item=fresh_item,   # ✅ FIX — was `order=fresh_item` (passing the
                                # OrderItem into an `order=` kwarg), which
                                # meant minimum_achieved_item never got set
                                # for referral agents (see earlier fix round).
        )

    referral_agent.refresh_from_db()
    print(f"   Agent after sales update: is_active={referral_agent.is_active_agent} "
          f"total_sales={referral_agent.total_sales}")

    was_distributed = process_item_mlm_commission(order, fresh_item, referral_agent)

    if was_distributed:
        OrderItem.objects.filter(pk=fresh_item.pk).update(mlm_commission_processed=True)
        print(f" Commission processed and flag set for item {fresh_item.id}\n")
    else:
        print(f" Commission NOT distributed for item {fresh_item.id} — flag left False, will retry\n")

    all_processed = not order.items.filter(mlm_commission_processed=False).exists()
    if all_processed:
        Order.objects.filter(pk=order.pk).update(mlm_commission_processed=True)


def _update_customer_stats(instance):
    try:
        profile, _ = CustomerProfile.objects.get_or_create(
            user=instance.customer,
            defaults={
                "full_name": instance.customer.get_full_name() or instance.customer.username,
                "email":     instance.customer.email,
                "phone":     getattr(instance.customer, 'phone', '') or "",
                "address":   "",
                "city":      "",
                "state":     "",
            },
        )
        completed = Order.objects.filter(
            customer=instance.customer,
            order_status__in=["delivered", "confirmed", "completed"],
        )
        total_spent = completed.aggregate(total=Sum("final_amount"))["total"] or Decimal("0.00")
        profile.total_spent  = total_spent
        profile.total_orders = completed.count()
        profile.save(update_fields=["total_spent", "total_orders", "updated_at"])
        profile.check_agent_eligibility()

        _sync_self_purchase_agent_sales(instance.customer, activation_item=instance)

    except Exception as e:
        print(f" Customer stats error: {e}")
        import traceback; traceback.print_exc()


@receiver(post_delete, sender=Order)
def update_customer_stats_on_delete(sender, instance, **kwargs):
    try:
        profile = CustomerProfile.objects.get(user=instance.customer)
        completed = Order.objects.filter(
            customer=instance.customer,
            order_status__in=["delivered", "confirmed", "completed"],
        ).exclude(id=instance.id)
        profile.total_orders = completed.count()
        profile.total_spent  = (
            completed.aggregate(total=Sum("final_amount"))["total"] or Decimal("0.00")
        )
        profile.save(update_fields=["total_spent", "total_orders", "updated_at"])
    except CustomerProfile.DoesNotExist:
        pass
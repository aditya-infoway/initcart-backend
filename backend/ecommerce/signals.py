# ecommerce/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal

from ecommerce.models.customer import CustomerProfile
from ecommerce.models.order import Order

_PROCESSING_ORDERS = set()


@receiver(post_save, sender=Order)
def handle_order_status_change(sender, instance, created, update_fields, **kwargs):
    if instance.pk in _PROCESSING_ORDERS:
        print(f" Signal skipped (already processing): {instance.pk}")
        return
    _PROCESSING_ORDERS.add(instance.pk)
    try:
        _handle_order(instance)
    except Exception as e:
        print(f" Signal error for order {instance.pk}: {e}")
        import traceback; traceback.print_exc()
    finally:
        _PROCESSING_ORDERS.discard(instance.pk)


def _handle_order(instance):
    from ecommerce.utils.order_service import update_agent_sales, process_mlm_commission

    print(f"\n SIGNAL FIRED: order={instance.order_number} status={instance.order_status} payment={instance.payment_status}")

    # 1. Always update customer stats
    _update_customer_stats(instance)

    # 2. Only process MLM on delivery
    if instance.order_status != "delivered":
        print(f" Not delivered yet ({instance.order_status}), skipping commission")
        return

    print(f"\n ORDER DELIVERED: {instance.order_number}")
    print(f"   referral_agent: {instance.referral_agent}")
    print(f"   payment_status: {instance.payment_status}")
    print(f"   mlm_commission_processed: {instance.mlm_commission_processed}")
    print(f"   final_amount: {instance.final_amount}")

    # 3. Re-fetch from DB to get the most current state
    # This avoids stale in-memory data from update_order_status
    try:
        fresh_order = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        print(f" Order {instance.pk} not found in DB")
        return

    print(f"   [DB fresh] order_status: {fresh_order.order_status}")
    print(f"   [DB fresh] payment_status: {fresh_order.payment_status}")
    print(f"   [DB fresh] mlm_commission_processed: {fresh_order.mlm_commission_processed}")
    print(f"   [DB fresh] referral_agent: {fresh_order.referral_agent}")

    # 4. Guard: already processed
    if fresh_order.mlm_commission_processed:
        print(f" Already processed (DB check): {fresh_order.order_number}")
        return

    # 5. Resolve referral_agent if missing
    referral_agent = fresh_order.referral_agent
    if not referral_agent:
        from ecommerce.utils.agent_order_utils import resolve_referral_agent
        referral_agent = resolve_referral_agent(fresh_order.customer)
        if referral_agent:
            Order.objects.filter(pk=fresh_order.pk).update(referral_agent=referral_agent)
            fresh_order.referral_agent = referral_agent
            print(f" Auto-linked: {referral_agent.user.username} → {fresh_order.order_number}")

    if not referral_agent:
        print(f" No referral agent found for order {fresh_order.order_number}")
        return

    print(f"   Agent resolved: {referral_agent.user.username} | status={referral_agent.status}")

    # 6. Check platform_profit on items — silent killer
    total_platform_profit = (
        fresh_order.items.aggregate(total=Sum("platform_profit"))["total"] or Decimal("0")
    )
    print(f"   total_platform_profit on items: ₹{total_platform_profit}")

    if total_platform_profit <= Decimal("0"):
        print(f"  platform_profit is ZERO — commission cannot be created!")
        print(f"   Check OrderItem.platform_profit values:")
        for item in fresh_order.items.all():
            print(f"     Item {item.id}: product={item.product_name} platform_profit={item.platform_profit}")
        return

    # 7. Update agent sales
    update_agent_sales(referral_agent.user, fresh_order.final_amount, from_delivery=True)
    referral_agent.refresh_from_db()
    print(f"   Agent after sales update: is_active={referral_agent.is_active_agent} total_sales={referral_agent.total_sales}")

    # 8. Process commission
    print(f"   Calling process_mlm_commission...")
    process_mlm_commission(fresh_order)

    # 9. Mark as processed using queryset update (avoids re-triggering signal)
    Order.objects.filter(pk=fresh_order.pk).update(
        mlm_commission_processed=True,
        commission_distributed_at_delivery=True,
    )
    print(f"Commission processed and flags set for {fresh_order.order_number}")

    # 10. Check upline activation
    from utils.upline_engine import get_upline_agents
    for upline in get_upline_agents(referral_agent.user):
        update_agent_sales(upline["user"], Decimal("0"), from_delivery=True)

    print(f" _handle_order complete: {fresh_order.order_number}\n")


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

        # ── Agent total_sales sync ────────────────────────────────────────
        try:
            from mlm.models.agent import Agent
            from mlm.models.mlm_settings import MLMSettings

            agent = Agent.objects.get(user=instance.customer, status="approved")

            delivered_total = Order.objects.filter(
                customer=instance.customer,
                order_status="delivered",
            ).aggregate(total=Sum("final_amount"))["total"] or Decimal("0.00")

            if delivered_total != agent.total_sales:
                agent.total_sales = delivered_total
                changed = ["total_sales"]

                mlm_settings = MLMSettings.objects.first()
                if mlm_settings and agent.total_sales >= mlm_settings.minimum_sale_amount:
                    if not agent.is_active_agent:
                        agent.is_active_agent = True
                        changed.append("is_active_agent")
                        print(f"✅ Agent ACTIVATED: {instance.customer.username}")
                    if not agent.minimum_achieved_at:
                        from django.utils import timezone
                        agent.minimum_achieved_at = timezone.now()
                        changed.append("minimum_achieved_at")

                agent.save(update_fields=changed)
                print(f"✅ Agent sales synced: {instance.customer.username} → ₹{agent.total_sales}")

        except Agent.DoesNotExist:
            pass
        # ─────────────────────────────────────────────────────────────────

    except Exception as e:
        print(f"❌ Customer stats error: {e}")
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
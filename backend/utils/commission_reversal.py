# mlm/utils/commission_reversal.py  (FULL FILE — replace your existing one with this)
from decimal import Decimal
from django.db.models import Sum
from mlm.models.mlm_transaction import MLMTransaction


def reverse_commission_for_return(refund):
    """
    ✅ FIX (this version): self-purchase agent ka total_sales ab yahin,
    DIRECTLY, delivered order-items se RECOMPUTE hota hai — pehle sirf
    agent.refresh_from_db() call hota tha, yeh maan ke ki total_sales
    kahin aur (Order post_save / item post_save) se already sahi ho
    chuka hoga. Lekin partial-item refund mein:
      - order poora refund nahi hota (doosre items delivered rehte hain)
        → order.order_status 'delivered' hi rehta hai → order.save()
        kabhi nahi chalta → Order post_save fire hi nahi hota
      - item ka post_save (jab item_status='refunded' set hota hai)
        handle_order_item_delivered() sirf item_status=='delivered' pe
        react karta hai, 'refunded' ko turant ignore kar deta hai
    Isliye koi resync kabhi trigger hi nahi hota tha — agent.total_sales
    stale (purana, refunded amount included) reh jata, threshold se upar
    hi dikhta, aur agent kabhi deactivate nahi hota chahe delivered sales
    actual mein threshold se neeche gir chuki ho.

    Ab self-purchase case mein bhi total_sales ko "sum of currently
    item_status='delivered' items for this customer" se directly
    recompute kiya jata hai — bilkul waisi hi query jaisi
    ecommerce/signals.py ke _sync_self_purchase_agent_sales() mein hai.
    """
    if refund.commission_reversed:
        return

    order = refund.order
    order_item = refund.order_item

    if not order_item.mlm_commission_processed:
        refund.commission_reversed = True
        refund.save(update_fields=['commission_reversed'])
        return

    item_profit = Decimal(str(order_item.platform_profit or 0))

    if item_profit <= 0:
        refund.commission_reversed = True
        refund.save(update_fields=['commission_reversed'])
        return

    original_transactions = MLMTransaction.objects.filter(
        order_item=order_item, amount__gt=0
    )

    if not original_transactions.exists():
        print(f"    ⚠️ No order_item-tagged transactions found for item "
              f"{order_item.id} — may be pre-migration commission, "
              f"skipping automated reversal")
        refund.commission_reversed = True
        refund.save(update_fields=['commission_reversed'])
        return

    fraction = Decimal(str(refund.refund_amount)) / Decimal(str(order_item.total_price)) \
        if order_item.total_price else Decimal("1")
    fraction = min(fraction, Decimal("1"))

    print(f"\n  ↩️  Reversing commission for {order.order_number} item {order_item.id} — "
          f"refund fraction = {fraction:.4f}")

    for tx in original_transactions:
        reversal_amount = (Decimal(str(tx.amount)) * fraction).quantize(Decimal('0.01'))
        if reversal_amount <= 0:
            continue

        MLMTransaction.objects.create(
            user=tx.user,
            order=order,
            order_item=order_item,
            level=tx.level,
            percentage=tx.percentage,
            amount=-reversal_amount,
            transaction_type=tx.transaction_type,
        )
        print(f"    ↩️ {tx.transaction_type} reversed | {tx.user.username} | "
              f"L{tx.level} | -₹{reversal_amount}")

    if order.referral_agent:
        from ecommerce.models.order import OrderItem  # local import — avoid circular import

        agent = order.referral_agent
        is_self_purchase = agent.user_id == order.customer_id
        update_fields = []

        if is_self_purchase:
            # ✅ FIX: refresh_from_db() ki jagah ab actual recompute —
            # yeh item ka status DB mein already 'refunded' set ho chuka
            # hai (refund_helpers.process_refund isko commission_reversal
            # call karne se PEHLE set karta hai), isliye query mein yeh
            # item khud-ba-khud exclude ho jayega.
            delivered_total = OrderItem.objects.filter(
                order__customer=agent.user,
                item_status="delivered",
            ).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")

            agent.total_sales = delivered_total
            update_fields.append('total_sales')
            print(f"    ↩️ Self-purchase recompute — {agent.full_name} total_sales: "
                  f"₹{agent.total_sales} (recalculated from currently-delivered items)")
        else:
            reduce_by = Decimal(str(refund.refund_amount))
            agent.total_sales = max(Decimal('0'), agent.total_sales - reduce_by)
            update_fields.append('total_sales')
            print(f"    ↩️ {agent.full_name} total_sales: -₹{reduce_by} = ₹{agent.total_sales}")

        from mlm.models.mlm_settings import MLMSettings
        settings_obj = MLMSettings.objects.first()

        is_pos_branch = agent.agent_type == 'pos' and agent.is_pos_branch_agent

        if settings_obj and not is_pos_branch and agent.total_sales < settings_obj.minimum_sale_amount:
            if agent.is_active_agent:
                agent.is_active_agent = False
                update_fields.append('is_active_agent')
                print(f"    ⚠️ Agent deactivated (sales fell below minimum): {agent.full_name}")

            if agent.minimum_achieved_at is not None or agent.minimum_achieved_item_id is not None:
                agent.minimum_achieved_at = None
                agent.minimum_achieved_item = None
                update_fields += ['minimum_achieved_at', 'minimum_achieved_item']
                print(f"    🔄 Cleared minimum_achieved_at/order for {agent.full_name} "
                      f"(will be re-set on next threshold crossing)")

        if update_fields:
            agent.save(update_fields=update_fields)

    refund.commission_reversed = True
    refund.save(update_fields=['commission_reversed'])
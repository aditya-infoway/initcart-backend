# mlm/utils/commission_reversal.py  (FULL FILE — replace your existing one with this)
from decimal import Decimal
from django.db.models import Sum
from mlm.models.mlm_transaction import MLMTransaction


def reverse_commission_for_return(refund):
    """
    ✅ FIX (this version): original_transactions ab order_item se filter
    hota hai, order se nahi. Pehle `MLMTransaction.objects.filter(order=order)`
    tha — multi-vendor order mein yeh DOOSRE vendor ke item ki commission
    transactions bhi utha leta, aur unko bhi reverse kar deta jab sirf EK
    item refund ho raha ho. Ab sirf usi order_item ki transactions match
    hoti hain jiska refund ho raha hai.

    total_platform_profit ab bhi order-wide hai kyunki `fraction` ka
    matlab tha "is item ka profit / order ka poora profit" — lekin ab jab
    commission khud item-level pe distribute hota hai, tx.amount pehle se
    hi is item ke liye hai, poore order ke liye nahi. Isliye fraction
    calculation ab REDUNDANT hai (fraction hamesha ~1.0 hoga agar sirf is
    item ki transactions match ho rahi hain) — lekin partial-item-quantity
    refunds ke liye (agar aap kabhi ek item ke andar ke quantity ka partial
    refund support karte ho) yeh proportional scaling abhi bhi kaam ka hai,
    isliye rakha hai as a safety multiplier.
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

    # ✅ FIX: order_item se filter, order se nahi
    original_transactions = MLMTransaction.objects.filter(
        order_item=order_item, amount__gt=0
    )

    if not original_transactions.exists():
        # order_item tag se pehle (migration se pehle) ki transactions ho
        # sakti hain jinke paas order_item set nahi hai — un legacy cases
        # ke liye yahan manually reconcile karna padega.
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
        agent = order.referral_agent
        is_self_purchase = agent.user_id == order.customer_id
        update_fields = []

        if is_self_purchase:
            agent.refresh_from_db()
            print(f"    ℹ️ Self-purchase — total_sales already recalculated "
                  f"by _update_customer_stats ({agent.total_sales}), "
                  f"skipping duplicate reduction")
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

            if agent.minimum_achieved_at is not None or agent.minimum_achieved_order_id is not None:
                agent.minimum_achieved_at = None
                agent.minimum_achieved_order = None
                update_fields += ['minimum_achieved_at', 'minimum_achieved_order']
                print(f"    🔄 Cleared minimum_achieved_at/order for {agent.full_name} "
                      f"(will be re-set on next threshold crossing)")

        if update_fields:
            agent.save(update_fields=update_fields)

    refund.commission_reversed = True
    refund.save(update_fields=['commission_reversed'])
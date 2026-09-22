# mlm/utils/commission_reversal.py  (FULL FILE — replace your existing one with this)
from decimal import Decimal
from django.db.models import Sum
from mlm.models.mlm_transaction import MLMTransaction


def reverse_commission_for_return(refund):
    """
    Call this right after a Razorpay refund is successfully PROCESSED
    (see ecommerce/utils/refund_helpers.py -> process_refund()).

    Reverses everything that was credited for the RETURNED item —
    proportional to how much of the order's platform_profit that one
    order_item was responsible for:

      1. Upline MLM commission, POS-branch profit, Society profit —
         each gets a matching NEGATIVE MLMTransaction. Original
         transactions are never touched, so history stays visible.

      2. referral_agent.total_sales is reduced — BUT ONLY when the
         referral_agent is NOT the order's own customer (self-purchase).
         For self-purchases, _update_customer_stats() already
         recalculated total_sales from scratch (order no longer counts
         as 'delivered'), so we don't subtract again here.

      3. ✅ BUG FIX: minimum_achieved_order / minimum_achieved_at reset.
         Previously this only cleared when the REFUNDED order happened
         to be the exact order stored as minimum_achieved_order. But if
         total_sales drops below the minimum because of a DIFFERENT
         order's refund, minimum_achieved_order was left pointing at a
         stale order — and since update_agent_sales() only ever sets a
         new minimum_achieved_order when minimum_achieved_at is None,
         that stale pointer never gets replaced. The agent then gets
         is_active_agent flipped back to True on their next qualifying
         order, but the stale ID means the *actual* new crossing order
         no longer gets correctly skipped — commission fires on it by
         mistake. Fix: whenever total_sales drops below minimum, ALWAYS
         clear minimum_achieved_at / minimum_achieved_order, regardless
         of which order caused the drop. The next order that re-crosses
         the threshold (via update_agent_sales) will then correctly set
         a fresh minimum_achieved_order.

    Idempotent — refund.commission_reversed guards against double-firing.
    """
    if refund.commission_reversed:
        return

    order = refund.order
    order_item = refund.order_item

    if not order.mlm_commission_processed:
        refund.commission_reversed = True
        refund.save(update_fields=['commission_reversed'])
        return

    total_platform_profit = order.items.aggregate(
        total=Sum('platform_profit')
    )['total'] or Decimal('0')

    item_profit = Decimal(str(order_item.platform_profit or 0))

    if total_platform_profit <= 0 or item_profit <= 0:
        refund.commission_reversed = True
        refund.save(update_fields=['commission_reversed'])
        return

    fraction = item_profit / total_platform_profit
    print(f"\n  ↩️  Reversing commission for {order.order_number} — "
          f"item share = {fraction:.4f} of order profit")

    original_transactions = MLMTransaction.objects.filter(order=order, amount__gt=0)

    for tx in original_transactions:
        reversal_amount = (Decimal(str(tx.amount)) * fraction).quantize(Decimal('0.01'))
        if reversal_amount <= 0:
            continue

        MLMTransaction.objects.create(
            user=tx.user,
            order=order,
            level=tx.level,
            percentage=tx.percentage,
            amount=-reversal_amount,
            transaction_type=tx.transaction_type,
        )
        print(f"    ↩️ {tx.transaction_type} reversed | {tx.user.username} | "
              f"L{tx.level} | -₹{reversal_amount}")

    # ── Adjust referral agent's total_sales / activation ───────────────────
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

            # ✅ FIX: reset unconditionally on drop-below-minimum, not only
            # when this specific order matches minimum_achieved_order_id.
            # Whatever was stored as the achieving order is no longer
            # meaningful once total_sales is back under threshold — the
            # next order to re-cross it must become the new one.
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
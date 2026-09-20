# mlm/utils/commission_reversal.py
from decimal import Decimal
from django.db.models import Sum
from mlm.models.mlm_transaction import MLMTransaction


def reverse_commission_for_return(refund):
    """
    Call this right after a Razorpay refund is successfully PROCESSED
    (see ecommerce/utils/refund_helpers.py -> process_refund()).

    Reverses everything that was credited for the RETURNED item —
    proportional to how much of the order's platform_profit that one
    order_item was responsible for (so a partial return inside a
    multi-item order only reverses its own share):

      1. Upline MLM commission, POS-branch profit, Society profit —
         each gets a matching NEGATIVE MLMTransaction (same user, level,
         percentage, tx_type). Original transactions are never touched,
         so full history stays visible — every existing report just sums
         amount, so it nets out automatically.
      2. referral_agent.total_sales is reduced by the actual refunded
         amount. If that drops the agent below the minimum sales
         threshold, the agent is deactivated again (except POS branch
         agents, who are always active by business rule) and, if this
         exact order was the one that had triggered their activation,
         that activation record is cleared too.

    Idempotent — refund.commission_reversed guards against double-firing.
    """
    if refund.commission_reversed:
        return

    order = refund.order
    order_item = refund.order_item

    if not order.mlm_commission_processed:
        # No commission was ever distributed for this order (no referral
        # agent, or delivery-commission step never ran) — nothing to undo.
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

    # ── Reverse every positive commission transaction tied to this order ──
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

    # ── Reduce the referral agent's total_sales by the refunded amount ────
    if order.referral_agent:
        agent = order.referral_agent
        reduce_by = Decimal(str(refund.refund_amount))
        agent.total_sales = max(Decimal('0'), agent.total_sales - reduce_by)
        update_fields = ['total_sales']

        from mlm.models.mlm_settings import MLMSettings
        settings_obj = MLMSettings.objects.first()

        is_pos_branch = agent.agent_type == 'pos' and agent.is_pos_branch_agent

        if settings_obj and not is_pos_branch and agent.total_sales < settings_obj.minimum_sale_amount:
            if agent.is_active_agent:
                agent.is_active_agent = False
                update_fields.append('is_active_agent')
                print(f"    ⚠️ Agent deactivated (sales fell below minimum): {agent.full_name}")

            # If THIS order was the one that originally unlocked the agent,
            # clear that record — a future order will re-evaluate cleanly.
            if agent.minimum_achieved_order_id == order.id:
                agent.minimum_achieved_at = None
                agent.minimum_achieved_order = None
                update_fields += ['minimum_achieved_at', 'minimum_achieved_order']

        agent.save(update_fields=update_fields)
        print(f"    ↩️ {agent.full_name} total_sales: -₹{reduce_by} = ₹{agent.total_sales}")

    refund.commission_reversed = True
    refund.save(update_fields=['commission_reversed'])
# utils/wallet_engine.py  (FULL FILE — replace your existing one with this)
from decimal import Decimal
from mlm.models.mlm_transaction import MLMTransaction


def credit_wallet(
    user,
    amount,
    level,
    percentage,
    tx_type="upline",
    order=None,
    order_item=None,   # ✅ NAYA — item-level commission tagging
    pos_sale=None,
):
    """
    Create one MLMTransaction record (commission / profit credit).

    order_item: jab commission ek specific OrderItem ki delivery se
    trigger hua ho (website multi-vendor orders), taaki refund reversal
    exactly usi item ki transactions ko target kar sake — doosre
    vendor ke item ki commission ko touch kiye bina.
    """
    amount = Decimal(str(amount))

    if amount <= Decimal("0"):
        print(
            f"  ⚠ Skipping zero/negative commission "
            f"for {user.username} (level {level})"
        )
        return None

    tx = MLMTransaction.objects.create(
        user             = user,
        order            = order,
        order_item       = order_item,   # ✅ NAYA
        pos_sale         = pos_sale,
        level            = level,
        percentage       = Decimal(str(percentage)),
        amount           = amount,
        transaction_type = tx_type,
    )

    ref = getattr(order, "order_number", None) or getattr(pos_sale, "bill_no", None)
    item_ref = f" item={order_item.id}" if order_item else ""
    print(
        f"  ✅ Commission credited | User: {user.username} | "
        f"Level: {level} | {percentage}% | ₹{amount} | "
        f"Type: {tx_type} | Ref: {ref}{item_ref}"
    )
    return tx
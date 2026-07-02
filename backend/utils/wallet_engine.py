# ============================================================
# FILE: utils/wallet_engine.py
# ACTION: REPLACE the entire file with this
# ============================================================
# CHANGE: Added optional `pos_sale` param so POS sales can
#         be recorded without an ecommerce Order object
# ============================================================

from decimal import Decimal
from mlm.models.mlm_transaction import MLMTransaction


def credit_wallet(
    user,
    amount,
    level,
    percentage,
    tx_type="upline",
    order=None,       # ecommerce Order (website sales)
    pos_sale=None,    # SalesMaster    (POS sales)  ← NEW
):
    """
    Create one MLMTransaction record (commission / profit credit).

    Exactly ONE of `order` or `pos_sale` should be provided.
    Both can be None only in tests; in production always pass one.
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
        order            = order,       # None for POS sales
        pos_sale         = pos_sale,    # None for website sales
        level            = level,
        percentage       = Decimal(str(percentage)),
        amount           = amount,
        transaction_type = tx_type,
    )

    ref = getattr(order, "order_number", None) or getattr(pos_sale, "bill_no", None)
    print(
        f"  ✅ Commission credited | User: {user.username} | "
        f"Level: {level} | {percentage}% | ₹{amount} | "
        f"Type: {tx_type} | Ref: {ref}"
    )
    return tx


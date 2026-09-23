# utils/commision_engine.py  (FULL FILE — replace your existing one with this)
from utils.wallet_engine import credit_wallet
from utils.agent_status import is_agent_active


def distribute_commission(order, result, order_item=None):
    """
    1. POS/Society seller ko extra profit credit karo (MLM ke upar)
    2. Upline agents ko MLM commission distribute karo

    order_item: ✅ NAYA — pass karo jab yeh ek specific item ki delivery
    se trigger hua commission ho (item-level flow). None rehne do agar
    kahin abhi bhi order-level call ho raha hai (backward compatible).
    """

    seller_extra = result.get("seller_extra")
    if seller_extra:
        seller_user  = seller_extra["user"]
        extra_amount = seller_extra["amount"]
        profit_type  = seller_extra["profit_type"]

        try:
            credit_wallet(
                user=seller_user,
                amount=extra_amount,
                order=order,
                order_item=order_item,   # ✅ NAYA
                level=0,
                percentage=0,
                tx_type=profit_type,
            )
            print(f"   ✅ Seller extra credited: {seller_user.username} "
                  f"₹{extra_amount} ({profit_type})")
        except Exception as e:
            print(f"   ❌ Seller extra credit failed: {e}")

    for payout in result.get("upline_payouts", []):
        if is_agent_active(payout["user"]):
            credit_wallet(
                user=payout["user"],
                amount=payout["profit"],
                order=order,
                order_item=order_item,   # ✅ NAYA
                level=payout["level"],
                percentage=payout["percentage"],
                tx_type="upline",
            )
            print(f"   ✅ Upline: {payout['user'].username} "
                  f"L{payout['level']} ₹{payout['profit']}")
        else:
            print(f"   ⚠️ Skipping upline: {payout['user']} "
                  f"L{payout['level']} — inactive")
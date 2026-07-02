# utils/commision_engine.py
from utils.wallet_engine import credit_wallet
from utils.agent_status import is_agent_active


def distribute_commission(order, result):
    """
    1. POS/Society seller ko extra profit credit karo (MLM ke upar)
    2. Upline agents ko MLM commission distribute karo
    """

    # ── Step 1: POS/Society seller extra profit ──────────────────────────
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
                level=0,                   # level 0 = seller's own profit
                percentage=0,
                tx_type=profit_type,       # "pos_profit" ya "service_profit"
            )
            print(f"   ✅ Seller extra credited: {seller_user.username} "
                  f"₹{extra_amount} ({profit_type})")
        except Exception as e:
            print(f"   ❌ Seller extra credit failed: {e}")

    # ── Step 2: Upline MLM commission ────────────────────────────────────
    for payout in result.get("upline_payouts", []):
        if is_agent_active(payout["user"]):
            credit_wallet(
                user=payout["user"],
                amount=payout["profit"],
                order=order,
                level=payout["level"],
                percentage=payout["percentage"],
                tx_type="upline",
            )
            print(f"   ✅ Upline: {payout['user'].username} "
                  f"L{payout['level']} ₹{payout['profit']}")
        else:
            print(f"   ⚠️ Skipping upline: {payout['user']} "
                  f"L{payout['level']} — inactive")
            
            
            
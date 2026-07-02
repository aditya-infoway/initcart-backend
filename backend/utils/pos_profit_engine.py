# ============================================================
# FILE: utils/pos_profit_engine.py
# ACTION: REPLACE entire file
# ============================================================
#
# CORRECT TOGGLE LOGIC:
#
#   CASE 1 — Referral code diya (agent ka code ya mobile number)
#     → HAMESHA MLM distribution (toggle se independent)
#     → ProfitDistribution config:
#         pos_percentage  % → Branch (POS agent)
#         mlm_percentage  % → Upline chain (level-wise)
#         company_%  + undistributed → Company
#
#   CASE 2 — Referral code NAHI diya (walk-in customer)
#     Toggle ON  → 90% Branch, 10% Company
#     Toggle OFF → ProfitDistribution ka pos_percentage % Branch ko
#                  baaki sab Company ko (no MLM, koi chain nahi)
#
# ============================================================

from decimal import Decimal
from mlm.models.profit_distribution import ProfitDistribution
from utils.pos_upline_engine import calculate_pos_mlm_distribution
from utils.wallet_engine import credit_wallet


# ────────────────────────────────────────────────────────────
# PUBLIC: Profit Calculate karo
# ────────────────────────────────────────────────────────────

def calculate_pos_sale_profit(sales_items):
    """
    SalesMaster ke items se total profit calculate karo.
    Profit per item = basic_amount - (purchasePrice × qty)
    basic_amount already discount + GST handle kiya hua hai.
    """
    total_profit = Decimal("0")

    for item in sales_items:
        sales_basic = Decimal(str(item.basic_amount or 0))

        purchase_price = Decimal("0")
        if item.variant:
            purchase_price = Decimal(str(item.variant.purchasePrice or 0))
        elif item.item_name:
            first_variant = item.item_name.variants.first()
            if first_variant:
                purchase_price = Decimal(str(first_variant.purchasePrice or 0))

        qty         = Decimal(str(item.qty or 0))
        item_profit = sales_basic - (purchase_price * qty)

        print(
            f"   {item.item_name.itemName if item.item_name else '?'} | "
            f"Sales Basic: {sales_basic} | "
            f"Purchase: {purchase_price} × {qty} = {purchase_price * qty} | "
            f"Item Profit: {item_profit}"
        )
        total_profit += item_profit

    total_profit = total_profit.quantize(Decimal("0.01"))
    print(f"   Total Profit: ₹{total_profit}")
    return total_profit


# utils/pos_profit_engine.py — Update distribute_pos_profit()

# ────────────────────────────────────────────────────────────
# PUBLIC: Main distribution entry point
# ────────────────────────────────────────────────────────────

def distribute_pos_profit(
    pos_sale,            # SalesMaster instance
    branch_user,         # Branch ka User (POS agent)
    purchaser_user,      # Agent User (referral code se mila) ya None
    walk_in_toggle,      # True = 90/10 | False = config %
    referral_code_given, # True/False
):
    """
    Decide karo kaunsa mode use hoga, phir profit distribute karo.

    DECISION TABLE:
    ┌─────────────────────┬───────────────┬──────────────────────────────────┐
    │ referral_code_given │ walk_in_toggle│ Mode                             │
    ├─────────────────────┼───────────────┼──────────────────────────────────┤
    │ YES (agent ka code) │ ON ya OFF     │ MLM Distribution (always)        │
    │ NO  (walk-in)       │ ON            │ Simple 90/10 split               │
    │ NO  (walk-in)       │ OFF           │ Config pos_% to branch, rest Co. │
    └─────────────────────┴───────────────┴──────────────────────────────────┘
    """
    print(f"\n{'='*60}")
    print(f"🏪 POS PROFIT DISTRIBUTION")
    print(f"Sale   : {pos_sale.bill_no}")
    print(f"Branch : {branch_user.username}")
    print(f"Referral Given : {referral_code_given}")
    print(f"Walk-in Toggle : {'ON (90/10)' if walk_in_toggle else 'OFF (config%)'}")
    print(f"{'='*60}")

    sales_items = pos_sale.items.select_related("variant", "item_name").all()
    total_profit = calculate_pos_sale_profit(sales_items)
    
    # ✅ Sale ka total amount (grand_total) — sales requirement ke liye
    total_sale_amount = pos_sale.grand_total or Decimal("0")

    if total_profit <= Decimal("0"):
        print("  ⚠ Profit zero ya negative — kuch distribute nahi hoga")
        return {"status": "no_profit", "total_profit": 0}

    # ── CASE 1: Referral code diya → hamesha MLM ────────────────────────
    if referral_code_given and purchaser_user is not None:
        print("\n  🔗 Mode: MLM Distribution (referral code diya)")
        
        # ── ✅ PURCHASER (REFERRAL AGENT) KI TOTAL_SALES UPDATE ──
        if purchaser_user:
            try:
                from mlm.models.agent import Agent
                agent = Agent.objects.get(user=purchaser_user, status="approved")
                agent.add_sales(total_sale_amount)  # ✅ Grand total
                print(f"  ✅ Purchaser {agent.full_name} total_sales: +₹{total_sale_amount}")
            except Agent.DoesNotExist:
                pass
        
        return _mlm_distribution(pos_sale, branch_user, purchaser_user, total_profit)

    # ── CASE 2: Walk-in (no referral code) ──────────────────────────────
    # ⚠️ Walk-in mein total_sales UPDATE NAHI HOGI
    if walk_in_toggle:
        print("\n  🚶 Mode: Walk-in Simple 90/10 (toggle ON)")
        return _walkin_simple_split(pos_sale, branch_user, total_profit)
    else:
        print("\n  🚶 Mode: Walk-in Config % (toggle OFF)")
        return _walkin_config_split(pos_sale, branch_user, total_profit)


# ────────────────────────────────────────────────────────────
# PRIVATE: Walk-in Toggle ON → 90% Branch, 10% Company
# ────────────────────────────────────────────────────────────

def _walkin_simple_split(pos_sale, branch_user, total_profit):
    """
    Simple fixed split:
      Branch  → 90%
      Company → 10%
    """
    branch_amt  = (total_profit * Decimal("0.90")).quantize(Decimal("0.01"))
    company_amt = (total_profit - branch_amt).quantize(Decimal("0.01"))

    print(f"  Branch ({branch_user.username}) : 90% = ₹{branch_amt}")
    print(f"  Company                         : 10% = ₹{company_amt}")

    credit_wallet(
        user       = branch_user,
        amount     = branch_amt,
        level      = 0,
        percentage = 90,
        tx_type    = "pos_profit",
        pos_sale   = pos_sale,
    )

    return {
        "mode"          : "walkin_simple_90_10",
        "total_profit"  : float(total_profit),
        "branch_amount" : float(branch_amt),
        "company_amount": float(company_amt),
    }


# ────────────────────────────────────────────────────────────
# PRIVATE: Walk-in Toggle OFF → Config pos_% Branch, rest Company
# ────────────────────────────────────────────────────────────

def _walkin_config_split(pos_sale, branch_user, total_profit):
    """
    ProfitDistribution config ka pos_percentage branch ko milega.
    Baaki sab (mlm% + company% + service%) company ko.
    No MLM chain — walk-in customer ke liye chain nahi chalegi.
    """
    config = ProfitDistribution.objects.first()

    if not config:
        # Config nahi hai → fallback 90/10
        print("  ⚠ ProfitDistribution config nahi mila → fallback 90/10")
        return _walkin_simple_split(pos_sale, branch_user, total_profit)

    pos_pct    = Decimal(str(config.pos_percentage))
    branch_amt = (total_profit * pos_pct / Decimal("100")).quantize(Decimal("0.01"))
    company_amt = (total_profit - branch_amt).quantize(Decimal("0.01"))

    print(f"  Branch ({branch_user.username}) : {pos_pct}% = ₹{branch_amt}")
    print(f"  Company (rest)                  :          = ₹{company_amt}")

    credit_wallet(
        user       = branch_user,
        amount     = branch_amt,
        level      = 0,
        percentage = float(pos_pct),
        tx_type    = "pos_profit",
        pos_sale   = pos_sale,
    )

    return {
        "mode"          : "walkin_config_pos_pct",
        "total_profit"  : float(total_profit),
        "pos_pct"       : float(pos_pct),
        "branch_amount" : float(branch_amt),
        "company_amount": float(company_amt),
    }


# ────────────────────────────────────────────────────────────
# PRIVATE: MLM Distribution (referral code diya)
# ────────────────────────────────────────────────────────────

def _mlm_distribution(pos_sale, branch_user, purchaser_user, total_profit):
    """
    ProfitDistribution config se poora split:
      pos_percentage  % → Branch (POS agent)
      mlm_percentage  % → Upline chain (level-wise)
      company_%
      + service_%          → Company
      + undistributed MLM  → Company
    """
    config = ProfitDistribution.objects.first()

    if not config:
        print("  ⚠ ProfitDistribution config nahi mila → fallback 90/10")
        return _walkin_simple_split(pos_sale, branch_user, total_profit)

    pos_pct     = Decimal(str(config.pos_percentage))
    mlm_pct     = Decimal(str(config.mlm_percentage))
    company_pct = Decimal(str(config.company_percentage))
    service_pct = Decimal(str(config.service_percentage))

    pos_amt     = (total_profit * pos_pct     / Decimal("100")).quantize(Decimal("0.01"))
    mlm_amt     = (total_profit * mlm_pct     / Decimal("100")).quantize(Decimal("0.01"))
    company_amt = (total_profit * company_pct / Decimal("100")).quantize(Decimal("0.01"))
    service_amt = (total_profit * service_pct / Decimal("100")).quantize(Decimal("0.01"))

    print(f"  POS Branch  ({pos_pct}%) : ₹{pos_amt}")
    print(f"  MLM Chain   ({mlm_pct}%) : ₹{mlm_amt}")
    print(f"  Company     ({company_pct}%) : ₹{company_amt}")
    print(f"  Service→Co  ({service_pct}%) : ₹{service_amt}")

    # ── Branch ko pos_profit credit karo ────────────────────────────────
    credit_wallet(
        user       = branch_user,
        amount     = pos_amt,
        level      = 0,
        percentage = float(pos_pct),
        tx_type    = "pos_profit",
        pos_sale   = pos_sale,
    )

# ── Upline chain mein mlm slice distribute karo ──────────────────────
    upline_result = calculate_pos_mlm_distribution(
        purchaser_user   = purchaser_user,
        total_mlm_profit = mlm_amt,
        total_profit     = total_profit,
        current_pos_sale = pos_sale,
    )

    for payout in upline_result["upline_payouts"]:
        credit_wallet(
            user       = payout["user"],
            amount     = payout["amount"],
            level      = payout["level"],
            percentage = payout["percentage"],
            tx_type    = "upline",
            pos_sale   = pos_sale,
        )

    # ✅ Society extra credit karo (pehli society agent)
    society_extra = upline_result.get("society_extra")
    if society_extra:
        credit_wallet(
            user       = society_extra["user"],
            amount     = society_extra["amount"],
            level      = 0,
            percentage = float(service_pct),
            tx_type    = "service_profit",
            pos_sale   = pos_sale,
        )
        print(f"  ✅ Society extra credited: {society_extra['user'].username} ₹{society_extra['amount']}")

    # ── Undistributed MLM + company + service → company ──────────────────
    # ✅ Agar society_extra mila toh service_amt company mein mat daalo
    service_to_company = Decimal("0") if society_extra else service_amt

    total_to_company = (
        company_amt
        + service_to_company
        + upline_result["undistributed"]
    ).quantize(Decimal("0.01"))

    print(
        f"  🏢 Total to Company: ₹{total_to_company} "
        f"(co={company_amt} + svc={service_amt} "
        f"+ undist={upline_result['undistributed']})"
    )

    return {
        "mode"           : "mlm_distribution",
        "total_profit"   : float(total_profit),
        "pos_amount"     : float(pos_amt),
        "mlm_amount"     : float(mlm_amt),
        "company_amount" : float(total_to_company),
        "upline_payouts" : upline_result["upline_payouts"],
    }
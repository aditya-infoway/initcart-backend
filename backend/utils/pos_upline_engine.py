# utils/pos_upline_engine.py

from decimal import Decimal
from mlm.models.agent import Agent
from mlm.models.mlm_level import MLMLevel
from users.models import User
from utils.agent_status import is_agent_active


def get_pos_upline_chain(purchaser_user, max_levels=None, current_pos_sale=None):  # ✅ current_pos_sale add kiya
    try:
        purchaser_user = User.objects.get(pk=purchaser_user.pk)
    except User.DoesNotExist:
        return []

    if max_levels is None:
        max_levels = MLMLevel.objects.count()

    if max_levels == 0:
        print("  ⚠ No MLM levels configured")
        return []

    chain = []
    level = 1

    print(f"\n  Building POS upline chain (max_levels={max_levels})")
    print(f"  Purchaser: {purchaser_user.username}")

    # ── SLOT 1: Parent → Level 1 (current_pos_sale pass nahi — parent ka check normal hai) ──
    parent = purchaser_user.referred_by
    if parent and is_agent_active(parent):
        chain.append({"level": level, "user": parent})
        print(f"    L{level}: {parent.username} (parent) ✅")
        level += 1
    else:
        print(f"    L{level}: {'None' if not parent else parent.username} ❌")

    # ── SLOT 2: Purchaser → current_pos_sale se check ────────────────
    # ✅ current_pos_sale pass karo taaki activation order skip ho
    purchaser_active = is_agent_active(purchaser_user, current_order=current_pos_sale)

    if purchaser_active:
        chain.append({"level": level, "user": purchaser_user})
        print(f"    L{level}: {purchaser_user.username} (purchaser) ✅ ACTIVE")
        level += 1
    else:
        print(f"    L{level}: {purchaser_user.username} (purchaser) ❌ INACTIVE/ACTIVATION ORDER — SKIPPED")

    # ── SLOTS 3, 4, 5... → Ancestors ──────────────────────────────────
    ancestor = parent.referred_by if parent else None
    current_level = level

    while ancestor and current_level <= max_levels:
        try:
            Agent.objects.get(user=ancestor, status="approved")
            if is_agent_active(ancestor):
                chain.append({"level": current_level, "user": ancestor})
                print(f"    L{current_level}: {ancestor.username} (ancestor) ✅")
                current_level += 1
            else:
                print(f"    L{current_level}: {ancestor.username} ❌ inactive")
        except Agent.DoesNotExist:
            print(f"    L{current_level}: {ancestor.username} ❌ not agent")

        ancestor = ancestor.referred_by

    print(f"  POS chain built: {len(chain)} levels")
    return chain


def calculate_pos_mlm_distribution(purchaser_user, total_mlm_profit, total_profit=None, current_pos_sale=None):
    total_mlm_profit = Decimal(str(total_mlm_profit))
    if total_profit is None:
        total_profit = total_mlm_profit
    else:
        total_profit = Decimal(str(total_profit))

    if total_mlm_profit <= Decimal("0"):
        return {
            "upline_payouts": [],
            "undistributed": Decimal("0"),
            "society_extra": None,
        }

    levels = list(MLMLevel.objects.order_by("level_number"))

    if not levels:
        print("  ⚠ No MLM levels configured")
        return {
            "upline_payouts": [],
            "undistributed": total_mlm_profit,
            "society_extra": None,
        }

    chain = get_pos_upline_chain(purchaser_user, max_levels=len(levels), current_pos_sale=current_pos_sale)
    level_pct_map = {lv.level_number: lv.percentage for lv in levels}

    upline_payouts = []
    distributed = Decimal("0")
    society_extra = None
    society_found = False

    from mlm.models.profit_distribution import ProfitDistribution
    config = ProfitDistribution.objects.first()
    service_pct = Decimal(str(config.service_percentage)) if config else Decimal("0")
    service_amt = (total_profit * service_pct / Decimal("100")).quantize(Decimal("0.01"))

    print(f"\n  Distributing MLM profit: ₹{total_mlm_profit}")
    print(f"  Service extra pool: ₹{service_amt} ({service_pct}% of total)")

    # ✅ PEHLE CHECK: Purchaser khud society agent + active hai?
    if service_amt > Decimal("0"):
        try:
            purchaser_agent = Agent.objects.get(user=purchaser_user, status="approved")
            if purchaser_agent.agent_type == "society" and is_agent_active(purchaser_user, current_order=current_pos_sale):
                society_extra = {
                    "user": purchaser_user,
                    "amount": service_amt,
                    "profit_type": "service_profit",
                }
                society_found = True  # ✅ Upline mein ab kisi society ko nahi milega
                print(f"    ✅ Purchaser khud society: {purchaser_user.username} → ₹{service_amt}")
        except Agent.DoesNotExist:
            pass

    for slot in chain:
        lvl_no = slot["level"]
        usr = slot["user"]
        pct = level_pct_map.get(lvl_no, 0)

        if pct <= 0:
            print(f"    L{lvl_no}: {usr.username} → {pct}% (skipping)")
            continue

        amount = (total_profit * Decimal(str(pct)) / Decimal("100")).quantize(Decimal("0.01"))

        if amount > Decimal("0"):
            distributed += amount
            upline_payouts.append({
                "level": lvl_no,
                "user": usr,
                "percentage": pct,
                "amount": amount,
            })
            print(f"    L{lvl_no}: {usr.username} → {pct}% = ₹{amount}")

        # ── Upline mein pehli society (sirf agar purchaser society nahi tha) ──
        if not society_found and service_amt > Decimal("0"):
            try:
                agent = Agent.objects.get(user=usr, status="approved")
                if agent.agent_type == "society" and is_agent_active(usr):
                    society_extra = {
                        "user": usr,
                        "amount": service_amt,
                        "profit_type": "service_profit",
                    }
                    society_found = True
                    print(f"    ✅ Society extra (upline): {usr.username} → ₹{service_amt}")
            except Agent.DoesNotExist:
                pass

    undistributed = (total_mlm_profit - distributed).quantize(Decimal("0.01"))

    if undistributed > Decimal("0"):
        print(f"  Undistributed → company: ₹{undistributed}")

    return {
        "upline_payouts": upline_payouts,
        "undistributed": undistributed,
        "society_extra": society_extra,
    }
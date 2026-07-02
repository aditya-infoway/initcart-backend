# utils/profit_engine.py
from decimal import Decimal
from mlm.models.profit_distribution import ProfitDistribution
from mlm.models.mlm_level import MLMLevel
from utils.upline_engine import get_upline_agents


def calculate_profit_distribution(total_profit, seller_user, current_order=None, root_user=None):
    """
    Split total_profit per ProfitDistribution config, then distribute
    the MLM slice to upline agents level by level.

    POS/Society agent extra profit rule:
    - Sirf tab milega jab seller ka current_order, minimum_achieved_at ke BAAD ka ho
    - Yani same condition jo MLM commission ke liye hai
    - is_agent_active(seller_user, current_order) = True tabhi extra profit milega
    """
    config = ProfitDistribution.objects.first()
    if not config:
        return {
            "pos_profit":     Decimal("0"),
            "service_profit": Decimal("0"),
            "mlm_profit":     Decimal("0"),
            "company_profit": Decimal(str(total_profit)),
            "upline_payouts": [],
            "seller_extra":   None,           
        }

    total_profit = Decimal(str(total_profit))

    pos_profit     = total_profit * Decimal(str(config.pos_percentage))     / Decimal("100")
    service_profit = total_profit * Decimal(str(config.service_percentage)) / Decimal("100")
    mlm_profit     = total_profit * Decimal(str(config.mlm_percentage))     / Decimal("100")
    company_profit = total_profit * Decimal(str(config.company_percentage)) / Decimal("100")

    print(f"\n💹 Profit split: total={total_profit} pos={pos_profit} "
          f"service={service_profit} mlm={mlm_profit} company={company_profit}")

    # ── POS/Society seller extra profit ─────────────────────────────────
    # SAME condition jo MLM commission ke liye hai:
    # is_agent_active(seller, current_order) = True hona chahiye
    seller_extra = None

    try:
        from mlm.models.agent import Agent
        from utils.agent_status import is_agent_active

        seller_agent = Agent.objects.get(user=seller_user, status="approved")

        if seller_agent.agent_type in ("pos", "society"):
            # ✅ Same check jo upline_engine mein seller ke liye hota hai
            # Agar seller inactive hai ya jis order se minimum achieve hua → skip
            seller_eligible = is_agent_active(seller_user, current_order=current_order)

            if seller_eligible:
                if seller_agent.agent_type == "pos":
                    extra_amount = pos_profit
                    extra_type   = "pos_profit"
                else:
                    extra_amount = service_profit
                    extra_type   = "service_profit"

                if extra_amount > Decimal("0"):
                    seller_extra = {
                        "user":        seller_user,
                        "amount":      extra_amount,
                        "profit_type": extra_type,
                    }
                    print(f"    {seller_agent.agent_type.upper()} extra profit: "
                          f"{seller_user.username} → ₹{extra_amount} ({extra_type})")
            else:
                print(f"    {seller_agent.agent_type.upper()} seller {seller_user.username} "
                      f"— not eligible for extra profit on this order "
                      f"(inactive or activation order)")

    except Agent.DoesNotExist:
        pass

    # ── Build upline chain ───────────────────────────────────────────────
    uplines = get_upline_agents(seller_user, current_order=current_order)
    levels  = MLMLevel.objects.all().order_by("level_number")

    upline_payouts  = []
    distributed_mlm = Decimal("0")

    for index, level_config in enumerate(levels):
        if index >= len(uplines):
            break

        agent_user = uplines[index]["user"]
        profit     = total_profit * Decimal(str(level_config.percentage)) / Decimal("100")

        distributed_mlm += profit
        upline_payouts.append({
            "level":      level_config.level_number,
            "user":       agent_user,
            "percentage": level_config.percentage,
            "profit":     profit,
        })

        print(f"  L{level_config.level_number}: {agent_user.username} → ₹{profit}")

    undistributed   = mlm_profit - distributed_mlm
    company_profit += undistributed

    if undistributed > 0:
        print(f"    Undistributed → company: ₹{undistributed}")

    return {
        "pos_profit":     pos_profit,
        "service_profit": service_profit,
        "mlm_profit":     mlm_profit,
        "company_profit": company_profit,
        "upline_payouts": upline_payouts,
        "seller_extra":   seller_extra,
    }
    
    
    
    
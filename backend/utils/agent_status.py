# utils/agent_status.py
from mlm.models.mlm_settings import MLMSettings
from mlm.models.agent import Agent
from decimal import Decimal
from django.utils import timezone


def is_agent_active(user, current_order=None):
    """
    Agent active hai ya nahi — commission ke liye.

    RULES:
    1. POS Branch Agent (is_pos_branch_agent=True) → hamesha active
    2. Manually registered POS / Normal / Society → minimum sale check
    3. Jis EXACT order se minimum complete hua, us order pe commission
       nahi milega — ID-based check (timestamp NAHI, race-proof)
    """
    try:
        agent = Agent.objects.get(user=user, status="approved")

        # ✅ POS Branch Agent (signal se bana) → hamesha active
        if agent.agent_type == "pos" and agent.is_pos_branch_agent:
            return True

        settings = MLMSettings.objects.first()
        if not settings:
            return False

        # AUTO-ACTIVATE: Agar total_sales >= minimum aur abhi tak activate nahi hua
        if agent.total_sales >= settings.minimum_sale_amount:
            if not agent.is_active_agent or not agent.minimum_achieved_at:
                agent.is_active_agent = True
                changed = ['is_active_agent']
                if not agent.minimum_achieved_at:
                    agent.minimum_achieved_at = timezone.now()
                    changed.append('minimum_achieved_at')
                    # ✅ Yahi wo order hai jisne threshold cross karaya —
                    # ID save karo taaki isi order ko exactly skip kar sakein
                    if current_order is not None and not agent.minimum_achieved_order_id:
                        agent.minimum_achieved_order = current_order
                        changed.append('minimum_achieved_order')
                agent.save(update_fields=changed)
                print(f"  ✅ AUTO-ACTIVATED: {agent.full_name}")

        # Agent ne minimum achieve nahi kiya → inactive
        if not agent.is_active_agent or not agent.minimum_achieved_at:
            return False

        # ✅ FIX: Time-based comparison HATAYA — ab sirf exact order-ID
        # compare hota hai. Jis order ne threshold cross karaya, SIRF
        # wahi skip hoga — chahe woh order kitni bhi jaldi/der se
        # process/deliver hua ho, ya doosre orders kitne bhi close-timing
        # mein hon. Yeh timestamp-race se completely immune hai.
        if current_order is not None and agent.minimum_achieved_order_id == current_order.id:
            return False

        return True

    except Agent.DoesNotExist:
        return False


def get_active_agents_in_chain(users_list):
    """Filter only active agents from a list of users"""
    active_agents = []
    for user in users_list:
        if is_agent_active(user):
            active_agents.append(user)
    return active_agents
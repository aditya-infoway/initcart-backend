# utils/agent_status.py
from mlm.models.mlm_settings import MLMSettings
from mlm.models.agent import Agent
from decimal import Decimal
from django.utils import timezone


def is_agent_active(user, current_item=None):
    """
    Agent active hai ya nahi — commission ke liye.

    RULES:
    1. POS Branch Agent (is_pos_branch_agent=True) → hamesha active
    2. Manually registered POS / Normal / Society → minimum sale check
    3. Jis EXACT ITEM se minimum complete hua, sirf USI item pe
       commission nahi milega — ITEM-ID based check (order-ID NAHI).
       Order-ID se check karne par, us item ke saath usi order ke
       DOOSRE (genuinely eligible) items bhi galti se skip ho jate the.
    """
    try:
        agent = Agent.objects.get(user=user, status="approved")

        if agent.agent_type == "pos" and agent.is_pos_branch_agent:
            return True

        settings = MLMSettings.objects.first()
        if not settings:
            return False

        if agent.total_sales >= settings.minimum_sale_amount:
            if not agent.is_active_agent or not agent.minimum_achieved_at:
                agent.is_active_agent = True
                changed = ['is_active_agent']
                if not agent.minimum_achieved_at:
                    agent.minimum_achieved_at = timezone.now()
                    changed.append('minimum_achieved_at')
                    if current_item is not None and not agent.minimum_achieved_item_id:
                        agent.minimum_achieved_item = current_item
                        changed.append('minimum_achieved_item')
                agent.save(update_fields=changed)
                print(f"  ✅ AUTO-ACTIVATED: {agent.full_name}")

        if not agent.is_active_agent or not agent.minimum_achieved_at:
            return False

        # ✅ FIX: item-ID based check — sirf EXACT achieving item skip
        # hoga, usi order ke doosre items normal eligible rahenge.
        if current_item is not None and agent.minimum_achieved_item_id == current_item.id:
            return False

        return True

    except Agent.DoesNotExist:
        return False


def get_active_agents_in_chain(users_list):
    active_agents = []
    for user in users_list:
        if is_agent_active(user):
            active_agents.append(user)
    return active_agents
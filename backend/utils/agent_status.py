""" #utils/agent_status.py
from mlm.models.mlm_settings import MLMSettings
from ecommerce.models.order import Order
from django.db import models
from mlm.models.agent import Agent

def is_agent_active(user):

    try:

        agent = Agent.objects.get(user=user, status="approved")

        settings = MLMSettings.objects.first()

        if not settings:
            return False

        if agent.total_sales >= settings.minimum_sale_amount:
            return True

        return False

    except Agent.DoesNotExist:
        return False """
        
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
    3. Jis order se minimum complete hua, us order pe commission nahi milega
    """
    try:
        agent = Agent.objects.get(user=user, status="approved")
        
        # ✅ POS Branch Agent (signal se bana) → hamesha active
        if agent.agent_type == "pos" and agent.is_pos_branch_agent:
            return True
        
        # Manually registered agents need minimum sales
        settings = MLMSettings.objects.first()
        if not settings:
            return False
        
        # AUTO-ACTIVATE: Agar total_sales >= minimum
        if agent.total_sales >= settings.minimum_sale_amount:
            if not agent.is_active_agent or not agent.minimum_achieved_at:
                agent.is_active_agent = True
                if not agent.minimum_achieved_at:
                    agent.minimum_achieved_at = timezone.now()
                agent.save(update_fields=['is_active_agent', 'minimum_achieved_at'])
                print(f"  ✅ AUTO-ACTIVATED: {agent.full_name}")
        
                # Agent ne minimum achieve nahi kiya → inactive
        if not agent.is_active_agent or not agent.minimum_achieved_at:
            return False
        
        # Current order check
        if current_order is not None:
            order_time = current_order.created_at
            if order_time <= agent.minimum_achieved_at:
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





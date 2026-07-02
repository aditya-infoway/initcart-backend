#utils/downline_engine.py
from users.models import User
from mlm.models.agent import Agent
from mlm.models.mlm_level import MLMLevel
from utils.agent_status import is_agent_active
from decimal import Decimal


def detect_branch_anywhere(root_user):

    queue = [root_user]

    while queue:

        current = queue.pop(0)

        children = list(User.objects.filter(referred_by=current))

        if len(children) > 1:
            return True

        queue.extend(children)

    return False


def get_full_chain(root_user):

    chain = []

    current = root_user

    try:
        root_agent = Agent.objects.get(user=root_user, status="approved")
    except Agent.DoesNotExist:
        return []

    # root active hona chahiye
    if not is_agent_active(root_user):
        return []

    chain.append({
        "user": root_user,
        "agent": root_agent
    })

    while True:

        children = list(User.objects.filter(referred_by=current))

        if len(children) != 1:
            break

        child = children[0]

        try:
            agent = Agent.objects.get(user=child, status="approved")
        except Agent.DoesNotExist:
            current = child
            continue

        # inactive agent skip
        if not is_agent_active(child):
            current = child
            continue

        chain.append({
            "user": child,
            "agent": agent
        })

        current = child

    return chain


def calculate_downline_distribution(root_user, seller_user, total_profit):

    payouts = []

    # condition 1
    if root_user != seller_user:
        return payouts

    # condition 2
    if detect_branch_anywhere(root_user):
        return payouts

    chain = get_full_chain(root_user)

    #no downline
    if len(chain) <= 1:
        return payouts

    levels = MLMLevel.objects.all().order_by("level_number")

    for index, level_config in enumerate(levels):

        if index >= len(chain):
            break

        agent_data = chain[index]

        profit = total_profit * Decimal(str(level_config.percentage)) / Decimal("100")

        payouts.append({
            "level": level_config.level_number,
            "agent_id": agent_data["agent"].id,
            "user": agent_data["user"],
            "percentage": level_config.percentage,
            "profit": profit
        })

    return payouts


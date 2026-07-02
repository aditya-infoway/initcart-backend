# utils/upline_engine.py
from mlm.models.agent import Agent
from utils.agent_status import is_agent_active


def get_upline_agents(seller_user, current_order=None):
    """
    Build the upline commission chain for a given seller.

    Case 1 — Seller INACTIVE (minimum sales not done):
        parent(C) → level 1
        grandparent(B) → level 2
        great-grandparent(A) → level 3
        (seller D skipped)

    Case 2a — Seller ACTIVE but yeh wahi order jisme minimum achieve hua:
        parent(C) → level 1
        grandparent(B) → level 2  ← seller still skipped
        great-grandparent(A) → level 3

    Case 2b — Seller ACTIVE aur agle order se:
        parent(C) → level 1
        seller(D) → level 2
        grandparent(B) → level 3
        great-grandparent(A) → level 4

    current_order sirf seller ke liye check hota hai.
    Parent aur ancestors ke liye sirf is_active_agent check hota hai.
    """
    uplines = []
    level = 1

    # Fresh fetch — stale object se bachao
    from users.models import User
    try:
        seller_user = User.objects.get(pk=seller_user.pk)
    except User.DoesNotExist:
        return uplines

    parent = seller_user.referred_by

    # ── Step 1: Parent → L1 (no current_order check for parent) ─────────
    if parent:
        try:
            Agent.objects.get(user=parent, status="approved")
            if is_agent_active(parent):
                uplines.append({"level": level, "user": parent})
                level += 1
        except Agent.DoesNotExist:
            pass

    # ── Step 2: Seller → current_order check here ────────────────────────
    # Agar seller inactive hai ya jis order se minimum achieve hua → skip
    if is_agent_active(seller_user, current_order=current_order):
        uplines.append({"level": level, "user": seller_user})
        level += 1

    # ── Step 3: Grandparent aur upar (no current_order check) ───────────
    ancestor = parent.referred_by if parent else None

    while ancestor:
        try:
            Agent.objects.get(user=ancestor, status="approved")
            if is_agent_active(ancestor):
                uplines.append({"level": level, "user": ancestor})
                level += 1
        except Agent.DoesNotExist:
            pass
        ancestor = ancestor.referred_by

    return uplines


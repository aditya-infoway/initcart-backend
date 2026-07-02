# ============================================================
# FILE: pos/signals/branch_agent_signal.py
# ACTION: REPLACE entire file
# ============================================================
# CHANGE: Agent.create() mein is_pos_branch_agent=True set kiya
#         Yahi field decide karega ki agent already eligible hai
# ============================================================

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="pos.Branch")
def auto_create_pos_agent(sender, instance, created, **kwargs):
    """
    Jab bhi naya Branch bane, automatically POS Agent create karo.
    is_pos_branch_agent=True set karo taaki minimum sales bypass ho.
    """
    if not created:
        return

    if not instance.user:
        return

    from mlm.models.agent import Agent
    from users.models import User

    user = instance.user
    print(f"\n📝 Branch signal: {instance.branch_name}")

    # ── 1. Phone set karo user mein ─────────────────────────────────────
    phone_changed = False
    if not user.phone or user.phone != instance.phone:
        user.phone = instance.phone
        phone_changed = True
        print(f"  ✅ Phone set: {user.phone}")

    # ── 2. Username → phone number (mobile se login ke liye) ────────────
    username_changed = False
    if instance.phone and user.username != instance.phone:
        phone_taken = User.objects.filter(
            username=instance.phone
        ).exclude(id=user.id).exists()

        if not phone_taken:
            old = user.username
            user.username = instance.phone
            username_changed = True
            print(f"  ✅ Username: {old} → {user.username}")
        else:
            print(f"  ⚠ Phone username taken, keeping: {user.username}")

    # ── 3. User save ─────────────────────────────────────────────────────
    fields_to_save = []
    if phone_changed:    fields_to_save.append("phone")
    if username_changed: fields_to_save.append("username")

    if fields_to_save:
        user.save(update_fields=fields_to_save)

    # ── 4. Role upgrade: branch → branch_agent ──────────────────────────
    if user.role == "branch":
        user.upgrade_role("agent")   # User.save() mein referral_code bhi banta hai
        user.refresh_from_db()
        print(f"  ✅ Role: {user.role} | Referral: {user.referral_code}")

    # ── 5. Agent pehle se exist karta hai? Skip ─────────────────────────
    if Agent.objects.filter(user=user).exists():
        print(f"  ℹ Agent already exists — skipping")
        return

    # ── 6. POS Agent create — is_pos_branch_agent=True ──────────────────
    try:
        agent = Agent.objects.create(
            user                = user,
            agent_type          = "pos",
            status              = "approved",
            is_active_agent     = True,
            is_pos_branch_agent = True,    # ✅ KEY FLAG — minimum sales bypass
            full_name           = instance.owner_name or instance.branch_name,
            contact_number      = instance.phone or "",
            email               = instance.email or "",
            address             = instance.address or "",
            city                = instance.city or "",
            state               = instance.state or "",
            society_or_business_name = instance.branch_name,
            passport_photo      = "",
            id_proof            = "",
        )
        print(f"  ✅ POS Agent created: {agent.full_name}")
        print(f"  🔑 Login: {agent.contact_number} | Referral: {user.referral_code}")
        print(f"  ⚡ is_pos_branch_agent=True — already eligible")
    except Exception as e:
        print(f"  ❌ Agent creation failed: {e}")
        import traceback
        traceback.print_exc()
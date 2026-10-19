# pos/utils/branch_accounts.py
import re

from pos.models.account import Account

MAIN_CREDITOR_GROUP = "Sundry Creditor(Main)"


def _clean_mobile(value):
    """Sirf digits, last 10 (Account.mobile max_length=10)."""
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:]


def create_main_creditor_account(new_branch, source_branch=None, created_by=None):
    """
    Naye branch ki books me 'Sundry Creditor(Main)' account banata hai.

    source_branch:
      - Superadmin ne branch/franchise banayi  -> None (superadmin ki branch use hogi)
      - Franchise ne sub-branch banayi         -> parent franchise ki branch pass karo

    Data sirf creation ke waqt copy hota hai, baad me auto-sync nahi hota.

    - Source na mile, ya new_branch khud source ho -> None return.
    - Is branch ka Main creditor pehle se ho       -> wahi return (duplicate nahi banega).
    """
    from pos.models.branch import Branch  # lazy import (circular import se bachne ke liye)

    if source_branch is None:
        source_branch = Branch.get_superadmin_branch()

    if not source_branch or source_branch.pk == new_branch.pk:
        return None

    existing = Account.objects.filter(
        branch=new_branch, group=MAIN_CREDITOR_GROUP
    ).first()
    if existing:
        return existing

    data = dict(
        branch=new_branch,
        account_name=(source_branch.branch_name or "")[:100],
        group=MAIN_CREDITOR_GROUP,
        opening_balance=0,
        drcr="Cr",
        address=source_branch.address or "",
        country=(source_branch.country or "")[:50],
        state=(source_branch.state or "")[:50],
        city=(source_branch.city or "")[:50],
        pincode=(source_branch.pincode or "")[:6],
        phone=(source_branch.phone or "")[:15],
        mobile=_clean_mobile(source_branch.phone),
        email=source_branch.email or None,
        gst_no=(source_branch.gst_number or "").upper()[:15],
        pan_card=(source_branch.pan_number or "").upper()[:10],
    )
    if created_by is not None:
        data["created_by"] = created_by

    # Account.save() khud current_balance / current_drcr set kar deta hai
    return Account.objects.create(**data)
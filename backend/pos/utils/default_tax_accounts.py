from decimal import Decimal
from django.db import transaction
from pos.models.account import Account

TAX_GROUP = "Duties & Taxes"

# (system_key, account_name, drcr)
DEFAULT_TAX_ACCOUNTS = [
    ("PURCHASE_IGST", "Purchase IGST", "Dr"),
    ("PURCHASE_SGST", "Purchase SGST", "Dr"),
    ("PURCHASE_CGST", "Purchase CGST", "Dr"),
    ("SALES_IGST",    "Sales IGST",    "Cr"),
    ("SALES_SGST",    "Sales SGST",    "Cr"),
    ("SALES_CGST",    "Sales CGST",    "Cr"),
]

# system_key -> (kind, item field)
TAX_LEDGER_MAP = {
    "PURCHASE_IGST": ("purchase", "igst"),
    "PURCHASE_SGST": ("purchase", "sgst"),
    "PURCHASE_CGST": ("purchase", "cgst"),
    "SALES_IGST":    ("sales", "igst"),
    "SALES_SGST":    ("sales", "sgst"),
    "SALES_CGST":    ("sales", "cgst"),
}


def _branch_data(branch):
    return {
        "address": branch.address or "",
        "country": (branch.country or "")[:50],
        "state": (branch.state or "")[:50],
        "city": (branch.city or "")[:50],
        "pincode": (branch.pincode or "")[:6],
        "gst_no": (branch.gst_number or "")[:15],
        "pan_card": (branch.pan_number or "")[:10],
    }


def ensure_default_tax_accounts(branch, created_by=None):
    """
    Branch ke 6 default tax accounts create karta hai (agar nahi hain)
    aur agar hain to branch ke latest state/city/country/GST/PAN se sync + name/group restore.
    """
    data = _branch_data(branch)

    with transaction.atomic():
        for key, name, drcr in DEFAULT_TAX_ACCOUNTS:
            defaults = {
                "account_name": name,
                "group": TAX_GROUP,
                "drcr": drcr,
                "opening_balance": Decimal("0.00"),
                "current_balance": Decimal("0.00"),
                "current_drcr": drcr,
                "is_system_default": True,
                **data,
            }
            if created_by:
                defaults["created_by"] = created_by

            acc, created = Account.objects.get_or_create(
                branch=branch, system_key=key, defaults=defaults
            )
            if created:
                continue

            wanted = {"account_name": name, "group": TAX_GROUP, "drcr": drcr,
                      "is_system_default": True, **data}
            changes = {k: v for k, v in wanted.items() if getattr(acc, k) != v}
            if changes:
                Account.objects.filter(pk=acc.pk).update(**changes)


def post_tax_to_accounts(branch, kind, items):
    """
    Entry save hone ke baad tax accounts ka current_balance live update karta hai.
    kind = "purchase" (Debit) ya "sales" (Credit). Fail ho to entry ko nahi rokta.
    """
    try:
        from pos.models.salesentry import SalesMaster

        totals = {"IGST": Decimal("0"), "SGST": Decimal("0"), "CGST": Decimal("0")}
        for it in items:
            totals["IGST"] += Decimal(it.igst or 0)
            totals["SGST"] += Decimal(it.sgst or 0)
            totals["CGST"] += Decimal(it.cgst or 0)

        side = "Dr" if kind == "purchase" else "Cr"
        with transaction.atomic():
            for tax, amount in totals.items():
                if amount <= 0:
                    continue
                acc = Account.objects.filter(
                    branch=branch, system_key=f"{kind.upper()}_{tax}"
                ).first()
                if acc:
                    # Purchase accounts Dr-nature, Sales accounts Cr-nature => same side par amount badhta hai
                    SalesMaster.update_balance(acc, amount, side)
    except Exception as e:
        print(f"⚠ tax account balance update failed: {e}")
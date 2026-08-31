# pos/services/purchase_common_service.py
from datetime import datetime
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.models.settings import setting


def generate_cash_payment_voucher(branch):
    settings_obj = setting.objects.filter(branch=branch).first()
    prefix = getattr(settings_obj, "CP", "CP") if settings_obj else "CP"

    last_voucher = CashPayment.objects.filter(branch=branch).order_by("-id").first()
    last_no = 0
    if last_voucher and last_voucher.voucher_no:
        try:
            parts = last_voucher.voucher_no.split("/")
            if len(parts) >= 3:
                last_no = int(parts[-1])
        except (ValueError, IndexError):
            last_no = 0

    now = datetime.now()
    fy_start = now.year if now.month >= 4 else now.year - 1
    fy_end = fy_start + 1
    fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
    next_no = str(last_no + 1).zfill(4)
    return f"{prefix}/{fy}/{next_no}"


def generate_bank_payment_voucher(branch):
    settings_obj = setting.objects.filter(branch=branch).first()
    prefix = getattr(settings_obj, "BP", "BP") if settings_obj else "BP"

    last_voucher = BankPayment.objects.filter(branch=branch).order_by("-id").first()
    last_no = 0
    if last_voucher and last_voucher.voucher_no:
        try:
            parts = last_voucher.voucher_no.split("/")
            if len(parts) >= 3:
                last_no = int(parts[-1])
        except (ValueError, IndexError):
            last_no = 0

    now = datetime.now()
    fy_start = now.year if now.month >= 4 else now.year - 1
    fy_end = fy_start + 1
    fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
    next_no = str(last_no + 1).zfill(4)
    return f"{prefix}/{fy}/{next_no}"


def apply_purchase_terms_side_effects(purchase, request):
    """
    Manual Purchase Entry (PurchaseCreateView) jaisi hi logic — Credit/Cash/Bank
    terms ke hisaab se party balance update ya PCP/PBP create karta hai.
    """
    terms = purchase.terms.strip().lower() if purchase.terms else ""

    if terms == "credit":
        if purchase.partyName:
            purchase.update_balance(purchase.partyName, purchase.grand_total, "Cr")

    elif terms == "cash":
        cash_account = purchase.case_account
        if cash_account and purchase.partyName:
            branch = request.user.get_effective_branch()
            voucher = generate_cash_payment_voucher(branch)
            CashPayment.objects.create(
                date=purchase.date,
                voucher_no=voucher,
                cash_account=cash_account,
                op_account=purchase.partyName,
                branch=branch,
                amount=purchase.grand_total,
                mode="Cash",
                narration=f"Auto payment against Purchase {purchase.billNo}",
                type="PCP",
                purchase=purchase,
                created_by=request.user,
            )

    elif terms == "bank":
        bank_account = purchase.bank_account
        if bank_account and purchase.partyName:
            branch = request.user.get_effective_branch()
            voucher = generate_bank_payment_voucher(branch)
            BankPayment.objects.create(
                date=purchase.date,
                voucher_no=voucher,
                bank_account=bank_account,
                op_account=purchase.partyName,
                branch=branch,
                amount=purchase.grand_total,
                mode="Auto",
                narration=f"Auto payment against Purchase {purchase.billNo}",
                type="PBP",
                purchase=purchase,
                created_by=request.user,
            )
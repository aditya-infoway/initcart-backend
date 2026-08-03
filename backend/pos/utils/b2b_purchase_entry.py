# pos/utils/b2b_purchase_entry.py
# B2B Sale fully verify hone par franchise branch ke liye ek genuine
# Purchase Entry (credit) auto-create karta hai — party = us branch
# ka apna "Sundry Creditor(Main)" account. Isse Purchase list, Cash/Bank
# Payment page (Purchase Entry flow), aur Ledger — teeno automatically
# kaam karne lagte hain, bina kisi extra frontend change ke.

from datetime import datetime
from decimal import Decimal

from pos.models.purchaseentry import PurchaseMaster, PurchaseItem
from pos.models.settings import setting
from pos.models.account import Account


def generate_purchase_bill_no(branch):
    """
    Purchase Entry ki existing numbering pattern continue karta hai —
    jo bhi last purchase bill tha (manual ya auto), uske turant baad
    wala number milega.
    """
    settings_obj = setting.objects.filter(branch=branch).first()
    prefix = getattr(settings_obj, 'PI', 'PI') if settings_obj else 'PI'
    now = datetime.now()
    fy_start = now.year if now.month >= 4 else now.year - 1
    fy = f"{str(fy_start)[2:]}-{str(fy_start + 1)[2:]}"
    pattern = f"{prefix}/{fy}/"

    last = PurchaseMaster.objects.filter(
        branch=branch, billNo__startswith=pattern
    ).order_by('-id').first()

    last_no = 0
    if last and last.billNo:
        try:
            parts = last.billNo.split('/')
            if len(parts) >= 3:
                last_no = int(parts[-1])
        except (ValueError, IndexError):
            last_no = 0

    next_no = str(last_no + 1).zfill(4)
    return f"{prefix}/{fy}/{next_no}"


def create_purchase_entry_from_b2b_sale(sale):
    """
    ✅ Sirf isi function ko call karo jab B2BSale FULLY verified ho chuki ho
    (sab items is_stock_updated=True). Partial verify pe kabhi mat bulao.
    """
    # ✅ Duplicate-safe — dobara call hone par bhi dubara Purchase Entry nahi banega
    if PurchaseMaster.objects.filter(b2b_sale=sale).exists():
        return None

    branch = sale.to_branch

    # Verify hone se pehle hi enforce ho chuka hota hai ki ye account exist kare
    party_account = Account.objects.filter(
        branch=branch, group='Sundry Creditor(Main)'
    ).first()
    if not party_account:
        return None

    items = list(sale.items.all())
    if not items:
        return None

    total_basic = sum((Decimal(str(i.basic_amount or 0)) for i in items), Decimal('0'))
    total_tax = sum((Decimal(str(i.tax_amount or 0)) for i in items), Decimal('0'))
    total_net = sum((Decimal(str(i.net_amount or 0)) for i in items), Decimal('0'))

    bill_no = generate_purchase_bill_no(branch)

    purchase = PurchaseMaster.objects.create(
        date=sale.sale_date,
        partyName=party_account,
        branch=branch,
        billNo=bill_no,
        terms='credit',
        narration=f"Auto-generated from B2B Sale {sale.sale_no}",
        total_basic=total_basic,
        total_tax=total_tax,
        total_net=total_net,
        grand_total=total_net,
        purchasebill_no=sale.sale_no,
        frightcharge=0,
        otherexpnse=0,
        roundamount=0,
        b2b_sale=sale,
    )

    purchase_items = []
    for i in items:
        dest_variant = i.to_variant
        if not dest_variant:
            continue
        dest_item = dest_variant.item
        unit_label = "pcs"
        if getattr(dest_item, 'unit', None):
            unit_label = (
                getattr(dest_item.unit, 'symbol', None)
                or getattr(dest_item.unit, 'name', None)
                or "pcs"
            )

        purchase_items.append(PurchaseItem(
            purchase=purchase,
            itemName=dest_item,
            variant=dest_variant,
            hsnCode=getattr(dest_item, 'hsnCode', '') or '',
            quantity=Decimal(str(i.quantity)),
            altQuantity=Decimal(str(i.quantity)),
            price=Decimal(str(i.rate or 0)),
            per=unit_label,
            basicAmount=Decimal(str(i.basic_amount or 0)),
            discountPercent=Decimal('0'),
            discountAmount=Decimal('0'),
            taxAmount=Decimal(str(i.tax_amount or 0)),
            netValue=Decimal(str(i.net_amount or 0)),
            sgst=Decimal(str(i.sgst or 0)),
            cgst=Decimal(str(i.cgst or 0)),
            igst=Decimal(str(i.igst or 0)),
            rate=float(i.rate or 0),
        ))

    # ✅✅ bulk_create — CRITICAL: PurchaseItem.save() apne aap GST recalculate
    # karta hai (branch.state == partyName.state check karke). Chunki party
    # account (Sundry Creditor Main) issi branch ka hai, states hamesha match
    # honge aur wo hamesha CGST/SGST split kar dega — chahe original B2B Sale
    # me IGST tha. bulk_create() us overridden save() ko bypass karta hai,
    # isliye humare already-correct GST values (jo B2B Sale creation time pe
    # sahi calculate hue the) safe rehte hain.
    PurchaseItem.objects.bulk_create(purchase_items)

    return purchase
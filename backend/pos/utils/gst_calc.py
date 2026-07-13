# pos/utils/gst_calc.py
from decimal import Decimal, ROUND_HALF_UP


def _d(value, default=Decimal("0")):
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value).replace("%", "").strip())
    except Exception:
        return default


def calculate_gst_split(rate, quantity, tax_percent, gst_toggle, same_state):
    """
    Stock Transfer / Order Tracking GST calculation — Purchase module jaisa hi logic,
    bas discount yahan nahi hota, sirf rate x quantity par lagta hai.

    gst_toggle = True  -> EXCLUSIVE MODE: rate = BASIC price, GST upar add hota hai.
                           basic = rate*qty ; tax = basic * tax% / 100 ; net = basic + tax
    gst_toggle = False -> INCLUSIVE MODE: rate = NET price (GST already included).
                           net = rate*qty ; tax = net * tax% / 100 ; basic = net - tax

    same_state = True  -> tax CGST + SGST me split (half-half)
    same_state = False -> pura tax IGST
    """
    rate = _d(rate)
    quantity = _d(quantity, Decimal("1"))
    tax_percent = _d(tax_percent)

    total_price = (rate * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    cgst = sgst = igst = total_tax = Decimal("0.00")

    if tax_percent > 0:
        if gst_toggle:
            # EXCLUSIVE
            total_tax = (total_price * tax_percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            basic_amount = total_price
            net_amount = (basic_amount + total_tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            # INCLUSIVE
            total_tax = (total_price * tax_percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net_amount = total_price
            basic_amount = (net_amount - total_tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if same_state:
            half = (total_tax / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cgst = half
            sgst = half
            if cgst + sgst != total_tax:
                cgst += (total_tax - (cgst + sgst))
        else:
            igst = total_tax
    else:
        basic_amount = total_price
        net_amount = total_price

    return {
        "basic_amount": basic_amount,
        "tax_amount": total_tax,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "net_amount": net_amount,
    }
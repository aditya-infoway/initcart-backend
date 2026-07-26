from io import BytesIO
from reportlab.lib.pagesizes import mm
from reportlab.lib import colors
from reportlab.lib.units import mm as MM
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from pos.utils.sales_bill_display import get_display_branch_for_sale

# 80mm thermal receipt width, height auto (long roll — give generous height)
RECEIPT_WIDTH = 80 * MM
RECEIPT_HEIGHT = 297 * MM  # generous, content flows and page just ends where it ends


def _dashed_line():
    return Paragraph(
        "-" * 42,
        ParagraphStyle("dash", fontName="Courier", fontSize=8, alignment=TA_CENTER, spaceAfter=2, spaceBefore=2)
    )

from pos.utils.sales_bill_display import get_display_branch_for_sale
def generate_receipt_pdf(sales):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(RECEIPT_WIDTH, RECEIPT_HEIGHT),
        topMargin=4 * MM, bottomMargin=4 * MM,
        leftMargin=3 * MM, rightMargin=3 * MM,
    )

    styles = getSampleStyleSheet()
    branch_name_style = ParagraphStyle(
        "branchName", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=11, alignment=TA_CENTER, spaceAfter=1,
    )
    address_style = ParagraphStyle(
        "address", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8, alignment=TA_CENTER, spaceAfter=2,
    )
    info_style = ParagraphStyle(
        "info", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8, alignment=TA_LEFT, leading=11,
    )
    total_style = ParagraphStyle(
        "total", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8, alignment=TA_LEFT, leading=11,
    )
    net_payable_style = ParagraphStyle(
        "netPayable", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10, alignment=TA_LEFT,
    )
    thanks_style = ParagraphStyle(
        "thanks", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8, alignment=TA_CENTER, spaceBefore=2,
    )

    branch = get_display_branch_for_sale(sales.branch)  
    customer = sales.customer
    elements = []

    # ── Branch name + address ──
    elements.append(Paragraph(branch.branch_name, branch_name_style))
    if getattr(branch, "address", None):
        elements.append(Paragraph(branch.address, address_style))
    elements.append(_dashed_line())

    # ── Bill info ──
    elements.append(Paragraph(
        f"<b>Bill No:</b> {sales.bill_no}&nbsp;&nbsp;&nbsp;&nbsp;<b>Date:</b> {sales.date.strftime('%d-%m-%Y') if hasattr(sales.date, 'strftime') else sales.date}",
        info_style
    ))
    elements.append(Paragraph(
        f"<b>Customer:</b> {customer.account_name}&nbsp;&nbsp;&nbsp;&nbsp;<b>Time:</b> {sales.created_at.strftime('%H:%M:%S')}",
        info_style
    ))
    if getattr(customer, "mobile", None):
        elements.append(Paragraph(f"<b>Mobile:</b> {customer.mobile}", info_style))
    elements.append(Paragraph(f"<b>Payment Mode:</b> {sales.payment_terms.capitalize()}", info_style))
    elements.append(_dashed_line())

    # ── Items table ──
    data = [["SR", "Item", "Qty", "Price", "Amount"]]
    for i, item in enumerate(sales.items.all(), start=1):
        data.append([
            str(i),
            item.item_name.itemName,
            str(item.qty).rstrip("0").rstrip(".") if "." in str(item.qty) else str(item.qty),
            f"{item.price:.2f}",
            f"{item.net_amount:.2f}",
        ])

    table = Table(data, colWidths=[8 * MM, 25 * MM, 10 * MM, 14 * MM, 17 * MM])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(table)
    elements.append(_dashed_line())

    # ── Totals ──
    elements.append(Paragraph(f"<b>Taxable Amount:</b>{sales.total_basic:.2f}", total_style))
    elements.append(Paragraph(f"<b>Discount:</b>-{sales.total_discount:.2f}", total_style))
    elements.append(Paragraph(f"<b>Tax (GST):</b>{sales.total_tax:.2f}", total_style))
    if sales.frightcharge:
        elements.append(Paragraph(f"<b>Freight:</b>{sales.frightcharge:.2f}", total_style))
    if sales.otherexpnse:
        elements.append(Paragraph(f"<b>Other Expense:</b>{sales.otherexpnse:.2f}", total_style))
    elements.append(Paragraph(f"<b>Round Off:</b>{sales.roundamount:.2f}", total_style))
    elements.append(_dashed_line())

    elements.append(Paragraph(f"NET PAYABLE:&#8377;{sales.grand_total:.2f}", net_payable_style))
    elements.append(_dashed_line())

    # ── Thanks ──
    elements.append(Paragraph(f"THANKS FOR SHOPPING {customer.account_name}", thanks_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
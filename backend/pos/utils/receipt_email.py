from django.core.mail import EmailMessage
from django.conf import settings
from pos.utils.receipt_pdf import generate_receipt_pdf


def send_sale_receipt_email(sales):
    customer = sales.customer
    email = getattr(customer, "email", None)
    if not email:
        return False, "Customer email not set"

    try:
        pdf_bytes = generate_receipt_pdf(sales)
    except Exception as e:
        return False, f"PDF generation failed: {e}"

    subject = f"Your Receipt - Bill No {sales.bill_no}"
    body = (
        f"Dear {customer.account_name},\n\n"
        f"Thank you for shopping with {sales.branch.branch_name}.\n"
        f"Please find your receipt attached (Bill No: {sales.bill_no}).\n\n"
        f"Grand Total: Rs. {sales.grand_total}\n\nRegards,\n{sales.branch.branch_name}"
    )

    try:
        msg = EmailMessage(
            subject=subject, body=body,
            from_email=settings.DEFAULT_FROM_EMAIL, to=[email],
        )
        msg.attach(
            f"Receipt_{sales.bill_no.replace('/', '_')}.pdf",
            pdf_bytes, "application/pdf",
        )
        msg.send(fail_silently=False)
        return True, "sent"
    except Exception as e:
        return False, str(e)
import json
import hmac
import hashlib
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ecommerce.models.order import PendingCheckout
from ecommerce.utils.order_service import process_order_from_pending


@csrf_exempt
@api_view(["POST"])
def razorpay_webhook(request):
    """
    Production-ready Razorpay webhook
    - Signature verification (if secret present)
    - Idempotent safe
    - Transaction protected
    """

    try:
        webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", None)
        received_signature = request.headers.get("X-Razorpay-Signature", "")

        body = request.body

        # ✅ Signature Verification (only if secret exists)
        if webhook_secret:
            expected_signature = hmac.new(
                webhook_secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(received_signature, expected_signature):
                return Response(
                    {"status": "invalid_signature"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        payload = json.loads(body.decode("utf-8"))
        event = payload.get("event")

        # ✅ We only care about payment.captured
        if event != "payment.captured":
            return Response({"status": "ignored"})

        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        razorpay_order_id = payment.get("order_id")
        razorpay_payment_id = payment.get("id")

        if not razorpay_order_id:
            return Response(
                {"status": "invalid_payload"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ Transaction-safe + idempotent
        with transaction.atomic():

            try:
                pending = (
                    PendingCheckout.objects
                    .select_for_update()
                    .select_related("user")
                    .get(razorpay_order_id=razorpay_order_id)
                )

            except PendingCheckout.DoesNotExist:
                return Response({"status": "no_pending_found"})

            # ✅ Idempotency check
            if pending.payment_completed:
                return Response({"status": "already_processed"})

            # 🔥 Process Order
            result = process_order_from_pending(pending, payment)

            # Mark payment completed
            pending.payment_completed = True
            pending.razorpay_payment_id = razorpay_payment_id
            pending.save(update_fields=["payment_completed", "razorpay_payment_id"])

        return Response({"status": "success"})

    except Exception as e:
        return Response(
            {"status": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
# ecommerce/models/refund.py  (FULL FILE — replace your existing one — adds commission_reversed field)
import uuid
from django.db import models
from django.utils import timezone
from ecommerce.models.order import Order, OrderItem
from ecommerce.models.return_request import ReturnRequest


class OrderRefund(models.Model):
    """
    One row per accepted ONLINE (razorpay) return request.
    Created automatically the moment a return becomes vendor_approved
    or admin_approved — see ecommerce/utils/refund_helpers.py.
    COD (self-delivery) returns never get a row here — there is no
    Razorpay payment to refund for those.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),      # accepted, Razorpay call not made yet
        ('processed', 'Processed'),  # money returned to customer
        ('failed', 'Failed'),        # Razorpay call failed / no payment id — needs admin retry
    ]

    refund_id = models.CharField(max_length=50, unique=True, editable=False)

    return_request = models.OneToOneField(
        ReturnRequest, on_delete=models.CASCADE, related_name='refund'
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refunds')
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='refunds')

    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    razorpay_refund_id = models.CharField(max_length=255, blank=True, null=True)
    
    failure_reason = models.TextField(blank=True, null=True)

    # ✅ NEW — tracks whether MLM commission (agent wallet + total_sales) for
    # this specific returned item has already been reversed, so it only
    # ever happens once even if process_refund() gets called again.
    commission_reversed = models.BooleanField(default=False)

    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.refund_id:
            self.refund_id = f"RFD{timezone.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.refund_id} - {self.order.order_number} ({self.status})"
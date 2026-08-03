# ecommerce/models/payment_request.py
import uuid
from django.db import models
from django.utils import timezone
from ecommerce.models.vendor import Vendor
from ecommerce.models.order import Order, OrderItem


class VendorPaymentRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ]

    payment_request_id = models.CharField(max_length=50, unique=True, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='payment_requests')

    date_from = models.DateField(blank=True,null=True)
    date_to = models.DateField(blank=True,null=True)

    # Orders vendor originally requested payment for
    orders = models.ManyToManyField(Order, related_name='payment_requests', blank=True)
    # Subset admin actually approved (== orders on full approval)
    approved_orders = models.ManyToManyField(Order, related_name='approved_payment_requests', blank=True)

    # As requested by vendor
    total_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    online_platform_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cod_platform_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_platform_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    release_payment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # As finalized by admin (may equal requested figures on full approval)
    approved_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    approved_online_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_remarks = models.TextField(blank=True, null=True)

    approved_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.payment_request_id:
            self.payment_request_id = f"PR{timezone.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.payment_request_id} - {self.vendor.business_name}"


class VendorCODRecovery(models.Model):
    """
    Tracks which COD (self-delivery) order-items' platform charge has already
    been recovered against some payment request, so it's never deducted twice.
    Freed up again if the request is rejected.
    """
    payment_request = models.ForeignKey(
        VendorPaymentRequest, on_delete=models.CASCADE, related_name='cod_recoveries'
    )
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE)
    platform_charge_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['order_item']
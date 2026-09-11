import uuid
from django.db import models
from django.utils import timezone
from ecommerce.models.order import Order, OrderItem
from ecommerce.models.vendor import Vendor
from users.models import User


class ReturnRequest(models.Model):
    STATUS_CHOICES = [
        ('requested', 'Requested'),          # vendor ki queue me
        ('vendor_approved', 'Vendor Approved'),
        ('vendor_rejected', 'Vendor Rejected'),   # customer ko "Request Again" dikhega
        ('re_requested', 're-Requested'),     # ab superadmin ki queue me
        ('admin_approved', 'Admin Approved'),
        ('admin_rejected', 'Admin Rejected'), # final — no more action
    ]

    REASON_CHOICES = [
        ('damaged', 'Damaged Product'),
        ('wrong_item', 'Wrong Item Delivered'),
        ('not_as_described', 'Not as Described'),
        ('size_issue', 'Size/Fit Issue'),
        ('quality_issue', 'Quality Issue'),
        ('changed_mind', 'Changed My Mind'),
        ('other', 'Other'),
    ]

    return_id = models.CharField(max_length=50, unique=True, editable=False)

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='return_requests')
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='return_requests')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='return_requests')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='return_requests')

    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField(blank=True, null=True)
    images = models.JSONField(blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')

    vendor_remarks = models.TextField(blank=True, null=True)
    admin_remarks = models.TextField(blank=True, null=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    vendor_responded_at = models.DateTimeField(blank=True, null=True)
    re_requested_at = models.DateTimeField(blank=True, null=True)
    admin_responded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-requested_at']

    def save(self, *args, **kwargs):
        if not self.return_id:
            self.return_id = f"RTN{timezone.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.return_id} - {self.order.order_number}"
    
class ReturnRequestImage(models.Model):
    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name='return_images'
    )
    image = models.ImageField(upload_to='returns/%Y/%m/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.return_request.return_id}"    
import uuid
from django.db import models
from django.utils import timezone
from ecommerce.models.vendor import Vendor


class TopSellerRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    BANNER_SOURCE_CHOICES = [
        ('vendor', 'Vendor'),
        ('admin', 'Admin'),
    ]

    request_id = models.CharField(max_length=50, unique=True, editable=False) 
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='top_seller_requests')

    # Vendor side
    message = models.TextField(blank=True, default='')

    # Banner shown in the website slider (auto-resized to 600x300)
    banner = models.ImageField(upload_to='top_seller_banners/', blank=True, null=True)
    banner_uploaded_by = models.CharField(
        max_length=10, choices=BANNER_SOURCE_CHOICES, blank=True, default=''
    )

    # Admin side
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_active = models.BooleanField(default=False)  # toggle: show on website or not
    display_order = models.PositiveIntegerField(default=0)  # lower number = shown first
    admin_remarks = models.TextField(blank=True, null=True)

    approved_at = models.DateTimeField(blank=True, null=True)
    rejected_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.request_id:
            self.request_id = f"TS{timezone.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.request_id} - {self.vendor.business_name}"
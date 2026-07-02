from django.db import models
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import Vendor
from services.models.subcategory import ServiceSubcategory
from services.models.base import ServiceBaseModel

User = get_user_model()


class HealthcareService(ServiceBaseModel):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="healthcare_services")
    subcategory = models.ForeignKey(ServiceSubcategory, on_delete=models.SET_NULL, null=True, blank=True)

    # Basic Info
    business_name = models.CharField(max_length=255)
    address = models.TextField()
    location = models.CharField(max_length=500, help_text="Google Maps link")

    # Location fields
    country = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)

    contact_no = models.CharField(max_length=20)
    whatsapp_no = models.CharField(max_length=20, blank=True, null=True)
    gmail_id = models.EmailField(max_length=255, blank=True, null=True)
    description = models.TextField()

    # Images
    main_image = models.ImageField(upload_to='healthcare_services/', null=True, blank=True)
    multi_images = models.ManyToManyField('HealthcareServiceImage', blank=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_healthcare_services'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'healthcare_service'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business_name} ({self.vendor.user.username})"


class HealthcareServiceImage(models.Model):
    image = models.ImageField(upload_to='healthcare_services/multi/')

    def __str__(self):
        return f"Image {self.id}"
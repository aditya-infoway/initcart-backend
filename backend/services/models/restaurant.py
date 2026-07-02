from django.db import models
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import Vendor
from services.models.subcategory import ServiceSubcategory
from services.models.base import ServiceBaseModel

User = get_user_model()


class RestaurantService(ServiceBaseModel):
    """
    Restaurant Service Model - Complete fields as requested
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    # Vendor & Category
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="restaurant_services")
    subcategory = models.ForeignKey(ServiceSubcategory, on_delete=models.SET_NULL, null=True, blank=True)

    # Basic Info
    restaurant_name = models.CharField(max_length=255, help_text="Restaurant business name")
    address = models.TextField()
    location = models.CharField(max_length=500, help_text="Google Maps link")

    # Location fields
    country = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)

    # Contact Info
    contact_no = models.CharField(max_length=20)
    whatsapp_no = models.CharField(max_length=20, blank=True, null=True)
    gmail_id = models.EmailField(max_length=255, blank=True, null=True)

    # Restaurant Specific Fields
    restaurant_rating = models.DecimalField(
        max_digits=3, decimal_places=1, 
        blank=True, null=True,
        help_text="Restaurant rating out of 5"
    )
    description = models.TextField(help_text="Restaurant description with HTML/Tax editor support")
    
    # Tax Editor field - stores rich text with tax information
    tax_description = models.TextField(
        blank=True, null=True,
        help_text="Tax information with rich text editing"
    )

    # Images
    main_image = models.ImageField(upload_to='restaurant_services/', null=True, blank=True)
    multi_images = models.ManyToManyField('RestaurantServiceImage', blank=True)

    # Status & Timestamps
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_active = models.BooleanField(default=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_restaurant_services'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'restaurant_service'
        ordering = ['-created_at']
        verbose_name = 'Restaurant Service'
        verbose_name_plural = 'Restaurant Services'

    def __str__(self):
        return f"{self.restaurant_name} ({self.vendor.user.username})"


class RestaurantServiceImage(models.Model):
    """
    Multi images for restaurant service
    """
    image = models.ImageField(upload_to='restaurant_services/multi/')
    restaurant_service = models.ForeignKey(
        RestaurantService, 
        on_delete=models.CASCADE, 
        related_name='restaurant_multi_images',
        null=True,  # Temporary for migration, will remove after
        blank=True
    )

    def __str__(self):
        return f"Restaurant Image {self.id}"
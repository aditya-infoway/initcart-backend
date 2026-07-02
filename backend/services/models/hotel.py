from django.db import models
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import Vendor
from services.models.subcategory import ServiceSubcategory
from services.models.base import ServiceBaseModel

User = get_user_model()


class HotelService(ServiceBaseModel):
    """
    Hotel Service Model - Complete fields as requested
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    ROOM_CATEGORY_CHOICES = (
        ('manual', 'Manual'),
        ('premium', 'Premium'),
    )

    # Vendor & Category
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="hotel_services")
    subcategory = models.ForeignKey(ServiceSubcategory, on_delete=models.SET_NULL, null=True, blank=True)

    # Basic Info
    hotel_name = models.CharField(max_length=255, help_text="Hotel business name")
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

    # Hotel Specific Fields
    hotel_rating = models.DecimalField(
        max_digits=3, decimal_places=1, 
        blank=True, null=True,
        help_text="Hotel rating out of 5"
    )
    description = models.TextField(help_text="Hotel description with rich text editor")

    # Room Category
    room_category = models.CharField(
        max_length=20, 
        choices=ROOM_CATEGORY_CHOICES, 
        default='manual',
        help_text="Room category type - Manual or Premium"
    )

    # Images
    main_image = models.ImageField(upload_to='hotel_services/', null=True, blank=True)
    multi_images = models.ManyToManyField('HotelServiceImage', blank=True)

    # Status & Timestamps
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_active = models.BooleanField(default=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_hotel_services'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hotel_service'
        ordering = ['-created_at']
        verbose_name = 'Hotel Service'
        verbose_name_plural = 'Hotel Services'

    def __str__(self):
        return f"{self.hotel_name} ({self.vendor.user.username})"


class HotelServiceImage(models.Model):
    """
    Multi images for hotel service
    """
    image = models.ImageField(upload_to='hotel_services/multi/')

    def __str__(self):
        return f"Hotel Image {self.id}"


class HotelRoomType(models.Model):
    """
    Room types for hotel - Grid: Room Type, Person, Rate
    """
    service = models.ForeignKey(
        HotelService, 
        on_delete=models.CASCADE, 
        related_name="room_types"
    )
    room_type = models.CharField(max_length=100, help_text="e.g., Deluxe Room, Suite, Standard Room")
    person = models.PositiveIntegerField(help_text="Number of persons")
    rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price per night in INR")

    class Meta:
        db_table = 'hotel_room_type'
        ordering = ['id']

    def __str__(self):
        return f"{self.room_type} - {self.person} person(s) - ₹{self.rate}"
# services/models/real_estate.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid
from django.utils.text import slugify
from ecommerce.models.vendor import Vendor
from services.models.subcategory import ServiceSubcategory
import os

User = get_user_model()

def generate_property_id():
    return str(uuid.uuid4())[:20]

def property_main_image_path(instance, filename):
    """Path for main images: services/real_estate/main/"""
    timestamp = int(timezone.now().timestamp())
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.{ext}"
    return f"services/real_estate/main/{unique_filename}"

def property_thumbnail_image_path(instance, filename):
    """Path for thumbnail images: services/real_estate/thumbnail/"""
    timestamp = int(timezone.now().timestamp())
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.{ext}"
    return f"services/real_estate/thumbnail/{unique_filename}"

def property_additional_image_path(instance, filename):
    """Path for additional images: services/real_estate/additional/"""
    timestamp = int(timezone.now().timestamp())
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.{ext}"
    return f"services/real_estate/additional/{unique_filename}"

def property_document_path(instance, filename):
    """Path for documents: services/real_estate/documents/"""
    timestamp = int(timezone.now().timestamp())
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.{ext}"
    return f"services/real_estate/documents/{unique_filename}"

class Property(models.Model):
    TRANSACTION_TYPES = [
        ('sale', 'For Sale'),
        ('rent', 'For Rent'),
        ('lease', 'For Lease'),
    ]
    
    
    FURNISHING_STATUS = [
        ('fully_furnished', 'Fully Furnished'),
        ('semi_furnished', 'Semi Furnished'),
        ('unfurnished', 'Unfurnished'),
    ]
    
    OWNERSHIP_TYPES = [
        ('freehold', 'Freehold'),
        ('leasehold', 'Leasehold'),
        ('cooperative', 'Co-operative'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('sold_rented', 'Sold/Rented'),
        ('expired', 'Expired'),
    ]
    
    FACING_DIRECTIONS = [
        ('east', 'East'),
        ('west', 'West'),
        ('north', 'North'),
        ('south', 'South'),
        ('north_east', 'North-East'),
        ('north_west', 'North-West'),
        ('south_east', 'South-East'),
        ('south_west', 'South-West'),
    ]
    
    DOCUMENTS_AVAILABLE = [
        ('all', 'All'),
        ('partial', 'Partial'),
        ('none', 'None'),
    ]
    
    CONTACT_TYPES = [
        ('owner', 'Owner'),
        ('broker', 'Broker'),
        ('builder', 'Builder'),
    ]
    
    # Basic Information
    property_id = models.CharField(max_length=50, default=generate_property_id, unique=True, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='properties')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='user_properties')
    
    # Title fields
    title = models.CharField(max_length=255)
    property_type = models.ForeignKey(
    ServiceSubcategory,
    on_delete=models.SET_NULL,
    null=True,
    blank=True
    )
    subcategory = models.ForeignKey(ServiceSubcategory,on_delete=models.SET_NULL,null=True,blank=True,db_constraint=False)   # 🔥 MOST IMPORTANT 
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPES)
    description = models.TextField()
    address = models.TextField()
    google_map_url = models.URLField(max_length=500, blank=True, null=True)
    
    # Location
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=20)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, blank=True, null=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, blank=True, null=True)
    
    # Specifications
    total_area_size = models.DecimalField(max_digits=10, decimal_places=2)
    carpet_area = models.DecimalField(max_digits=10, decimal_places=2)
    built_up_area = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    bedrooms = models.PositiveIntegerField()
    bathrooms = models.CharField(max_length=10)
    balconies = models.PositiveIntegerField()
    furnishing_status = models.CharField(max_length=50, choices=FURNISHING_STATUS)
    floor_number = models.PositiveIntegerField()
    total_floors = models.PositiveIntegerField()
    facing_direction = models.CharField(max_length=50, choices=FACING_DIRECTIONS)
    property_age = models.CharField(max_length=50)
    
    # Legal & Ownership
    ownership_type = models.CharField(max_length=50, choices=OWNERSHIP_TYPES)
    encumbrance_certificate = models.TextField(blank=True, null=True)
    rea_number = models.CharField(max_length=100, blank=True, null=True)
    rera_number = models.CharField(max_length=100, blank=True, null=True)
    rera_registered = models.BooleanField(default=False)
    loan_availability = models.BooleanField(default=False)
    documents_available = models.CharField(max_length=50, choices=DOCUMENTS_AVAILABLE, default='all')
    negotiable = models.BooleanField(default=True)
    
    # Price Information
    price = models.DecimalField(max_digits=15, decimal_places=2)
    maintenance_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    booking_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Contact Information
    contact_type = models.CharField(max_length=20, choices=CONTACT_TYPES, default='owner')
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    contact_mobile = models.CharField(max_length=20, blank=True, null=True)
    contact_whatsapp = models.CharField(max_length=20, blank=True, null=True)
    contact_email = models.EmailField(max_length=254, blank=True, null=True)
    contact_preferred_time = models.CharField(max_length=100, blank=True, null=True)
    use_vendor_info = models.BooleanField(default=True)
    
    # Status & Metadata
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)
    enquiry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)
    
    # SEO & Additional Info
    short_description = models.CharField(max_length=200, blank=True, null=True)
    seo_title = models.CharField(max_length=255, blank=True, null=True)
    seo_description = models.TextField(blank=True, null=True)
    seo_keywords = models.TextField(blank=True, null=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    virtual_tour_url = models.URLField(max_length=200, blank=True, null=True)
    floor_plan = models.CharField(max_length=100, blank=True, null=True)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    construction_status = models.CharField(max_length=50, default='ready_to_move')
    
    # JSON Fields
    amenities = models.JSONField(default=list)
    nearby_facilities = models.JSONField(default=dict)
    
    # Documents
    documents = models.FileField(
        upload_to=property_document_path,
        blank=True,
        null=True,
        max_length=500
    )
    
    # Approval fields
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_properties')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Properties"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['price']),
            models.Index(fields=['created_at']),
            models.Index(fields=['vendor']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['city']),
            models.Index(fields=['property_type']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-calculate price per sqft
        if self.total_area_size and self.price and self.total_area_size > 0:
            self.price_per_sqft = self.price / self.total_area_size
        
        # Auto-set published_at when approved
        if self.status == 'approved' and not self.published_at:
            self.published_at = timezone.now()
        
        # Auto-generate slug
        if not self.slug and self.title:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Property.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        # If using vendor info
        if self.use_vendor_info and self.vendor:
            self.contact_name = self.vendor.owner_name or self.vendor.business_name
            self.contact_mobile = self.vendor.phone
            self.contact_email = self.vendor.email
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.title} - {self.get_transaction_type_display()}"
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def is_available(self):
        return self.status == 'approved' and self.status not in ['sold_rented', 'expired']
    
    @property
    def is_active(self):
        """For website display - only approved and not sold/expired"""
        return self.status == 'approved' and self.status not in ['sold_rented', 'expired']
    
    def approve(self, approved_by_user, admin_notes=""):
        """Approve the property"""
        self.status = 'approved'
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.published_at = timezone.now()
        self.save()
    
    def reject(self, rejected_by_user, admin_notes=""):
        """Reject the property"""
        self.status = 'rejected'
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        self.save()

class PropertyImage(models.Model):
    IMAGE_TYPE_CHOICES = [
        ('main', 'Main Image'),
        ('thumbnail', 'Thumbnail Image'),
        ('additional', 'Additional Image'),
    ]
    
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image_type = models.CharField(max_length=20, choices=IMAGE_TYPE_CHOICES, default='additional')
    
    # Dynamic upload_to based on image_type
    def get_upload_path(self, filename):
        if self.image_type == 'main':
            return property_main_image_path(self, filename)
        elif self.image_type == 'thumbnail':
            return property_thumbnail_image_path(self, filename)
        else:
            return property_additional_image_path(self, filename)
    
    image = models.ImageField(upload_to=get_upload_path)
    alt_text = models.CharField(max_length=255, blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
        verbose_name = "Property Image"
        verbose_name_plural = "Property Images"
    
    def __str__(self):
        return f"{self.get_image_type_display()} for {self.property.title}"
    
    def save(self, *args, **kwargs):
        # Ensure image_type is set before saving
        if not self.image_type:
            self.image_type = 'additional'
        super().save(*args, **kwargs)

class PropertyEnquiry(models.Model):
    ENQUIRY_TYPES = [
        ('general', 'General Enquiry'),
        ('visit', 'Site Visit Request'),
        ('price', 'Price Negotiation'),
        ('document', 'Document Request'),
    ]
    
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='enquiries')
    name = models.CharField(max_length=255)
    email = models.EmailField()
    mobile = models.CharField(max_length=15)
    enquiry_type = models.CharField(max_length=50, choices=ENQUIRY_TYPES, default='general')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    responded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    response_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Property Enquiries"
    
    def __str__(self):
        return f"Enquiry from {self.name} for {self.property.title}"
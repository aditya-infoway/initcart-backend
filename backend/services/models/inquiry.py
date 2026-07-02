#services/models/inquiry.py
from django.db import models
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import Vendor
import uuid
from django.utils import timezone

User = get_user_model()

def generate_inquiry_id():
    return str(uuid.uuid4())[:15]

class ServiceCategory(models.TextChoices):
    SALON = 'salon', 'Salon'
    GYM = 'gym', 'Gym'
    REAL_ESTATE = 'real_estate', 'Real Estate'
    TRAVEL_AGENCY = 'travel_agency', 'Travel Agency'
    FINANCE = 'finance', 'Finance'
    TECH = 'tech', 'Tech Industry'
    HOTEL = 'hotel', 'Hotel'
    HEALTHCARE = 'healthcare', 'Healthcare'
    EDUCATION = 'education', 'Education'
    PROFESSIONAL = 'professional', 'Professional'
    WORK_PLACE = 'work_place', 'Work Place'
    RESTAURANT = 'restaurant', 'Restaurant'

class InquiryType(models.TextChoices):
    GENERAL = 'general', 'General Inquiry'
    QUOTE = 'quote', 'Quote Request'
    BOOKING = 'booking', 'Booking'
    CONSULTATION = 'consultation', 'Consultation'
    SUPPORT = 'support', 'Support'
    COMPLAINT = 'complaint', 'Complaint'
    FEEDBACK = 'feedback', 'Feedback'

class InquiryStatus(models.TextChoices):
    NEW = 'new', 'New'
    IN_PROGRESS = 'in_progress', 'In Progress'
    RESPONDED = 'responded', 'Responded'
    RESOLVED = 'resolved', 'Resolved'
    CLOSED = 'closed', 'Closed'
    SPAM = 'spam', 'Spam'

class ServiceInquiry(models.Model):
    """Common inquiry model for all service vendors"""
    inquiry_id = models.CharField(max_length=50, default=generate_inquiry_id, unique=True, editable=False)
    
    # Service Information
    service_category = models.CharField(max_length=50, choices=ServiceCategory.choices)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='service_inquiries')
    
    # Foreign key to specific service (optional)
    service_id = models.IntegerField(null=True, blank=True, help_text="ID of the specific service/property/product")
    service_name = models.CharField(max_length=255, blank=True, null=True)
    service_url = models.URLField(max_length=500, blank=True, null=True)
    
    # Customer Information
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    customer_address = models.TextField(blank=True, null=True)
    customer_city = models.CharField(max_length=100, blank=True, null=True)
    customer_state = models.CharField(max_length=100, blank=True, null=True)
    
    # Inquiry Details
    inquiry_type = models.CharField(max_length=50, choices=InquiryType.choices, default='general')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    
    # Additional Fields
    preferred_date = models.DateField(null=True, blank=True)
    preferred_time = models.TimeField(null=True, blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quantity = models.IntegerField(null=True, blank=True, default=1)
    custom_fields = models.JSONField(default=dict, blank=True, help_text="Additional custom fields in JSON format")
    
    # Status and Tracking
    status = models.CharField(max_length=50, choices=InquiryStatus.choices, default='new')
    priority = models.IntegerField(default=1, help_text="1=Low, 2=Medium, 3=High, 4=Urgent")
    is_read = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    
    # Admin/Vendor Response
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_inquiries')
    response_notes = models.TextField(blank=True, null=True)
    response_date = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=100, default='website', help_text="website, mobile_app, phone, email, etc.")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Service Inquiries"
        indexes = [
            models.Index(fields=['service_category']),
            models.Index(fields=['vendor']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['customer_email']),
        ]
    
    def __str__(self):
        return f"Inquiry #{self.inquiry_id} - {self.customer_name} - {self.get_service_category_display()}"
    
    def mark_as_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])
    
    def respond(self, notes, responded_by=None):
        self.status = InquiryStatus.RESPONDED
        self.response_notes = notes
        self.response_date = timezone.now()
        self.assigned_to = responded_by
        self.save()
    
    def resolve(self, resolution_notes, resolved_by=None):
        self.status = InquiryStatus.RESOLVED
        self.resolution_notes = resolution_notes
        self.assigned_to = resolved_by
        self.save()
    
    def close(self):
        self.status = InquiryStatus.CLOSED
        self.save()

class InquiryAttachment(models.Model):
    """Attachments for service inquiries"""
    inquiry = models.ForeignKey(ServiceInquiry, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='inquiry_attachments/%Y/%m/%d/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_size = models.IntegerField(help_text="Size in bytes")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['uploaded_at']
    
    def __str__(self):
        return f"Attachment: {self.file_name} for Inquiry #{self.inquiry.inquiry_id}"

class InquiryNote(models.Model):
    """Internal notes for inquiries (visible to admin/vendor only)"""
    inquiry = models.ForeignKey(ServiceInquiry, on_delete=models.CASCADE, related_name='internal_notes')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='inquiry_notes')
    note = models.TextField()
    is_internal = models.BooleanField(default=True, help_text="If True, only visible to admin/vendor")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note by {self.user} on Inquiry #{self.inquiry.inquiry_id}"
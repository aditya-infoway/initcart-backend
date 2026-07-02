from django.db import models
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import Vendor
import uuid
import os
import time
from django.utils import timezone

User = get_user_model()

def education_service_image_path(instance, filename):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    vendor_id = instance.vendor.id if instance.vendor else "temp"
    return f"education_services/{vendor_id}_{timestamp}.{ext}"

class EducationService(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('inactive', 'Inactive'),
    ]
    
    EDUCATION_TYPE_CHOICES = [
        ('school', 'School'),
        ('coaching', 'Coaching'),
        ('tuition', 'Tuition'),
        ('college', 'College'),
        ('university', 'University'),
        ('online_course', 'Online Course'),
        ('workshop', 'Workshop'),
        ('other', 'Other'),
    ]
    
    MODE_OF_CLASS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('hybrid', 'Hybrid'),
    ]
    
    # Vendor Reference
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='education_services')
    
    # Basic Information
    service_name = models.CharField(max_length=255)
    short_description = models.TextField()
    full_description = models.TextField()
    image = models.ImageField(upload_to=education_service_image_path, null=True, blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    offer_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gst_percentage = models.CharField(max_length=10, default="18%")
    
    # Contact Information
    contact_person = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=20)
    email = models.EmailField()
    
    # Address
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=20)
    landmark = models.CharField(max_length=255, null=True, blank=True)
    
    # Education Specific Fields
    education_type = models.CharField(max_length=50, choices=EDUCATION_TYPE_CHOICES)
    subjects_courses = models.TextField(help_text="Comma separated subjects or courses")
    mode_of_class = models.CharField(max_length=20, choices=MODE_OF_CLASS_CHOICES)
    class_duration = models.CharField(max_length=100, null=True, blank=True, help_text="e.g., 2 hours per day")
    batch_timings = models.CharField(max_length=255, help_text="e.g., 9 AM - 11 AM, 4 PM - 6 PM")
    faculty_details = models.TextField(null=True, blank=True)
    facilities = models.TextField(null=True, blank=True, help_text="Available facilities")
    eligibility_criteria = models.TextField(null=True, blank=True)
    
    # Media
    video_url = models.URLField(null=True, blank=True)
    
    # Terms & Conditions
    terms_conditions = models.TextField()
    
    # Approval Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    submitted_for_approval_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_education_services')
    rejection_reason = models.TextField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    # Active/Inactive
    is_active = models.BooleanField(default=True)
    
    # Additional fields
    is_featured = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)
    
    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Education Service"
        verbose_name_plural = "Education Services"
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['city', 'education_type']),
            models.Index(fields=['status', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.service_name} - {self.vendor.business_name}"
    
    @property
    def final_price(self):
        """Return offer price if available, else regular price"""
        return self.offer_price if self.offer_price else self.price
    
    @property
    def image_url(self):
        """Return image URL if exists"""
        if self.image and hasattr(self.image, 'url'):
            return self.image.url
        return None
    
    @property
    def can_be_edited_by_vendor(self):
        """Check if vendor can edit this service"""
        return self.status in ['draft', 'rejected']
    
    @property
    def can_be_submitted_for_approval(self):
        """Check if service can be submitted for approval"""
        return self.status in ['draft', 'rejected']
    
    def submit_for_approval(self):
        """Submit service for admin approval"""
        if self.can_be_submitted_for_approval:
            self.status = 'pending'
            self.submitted_for_approval_at = timezone.now()
            self.save()
            return True
        return False
    
    def approve(self, approved_by_user):
        """Approve service by admin"""
        self.status = 'approved'
        self.approved_at = timezone.now()
        self.approved_by = approved_by_user
        self.is_active = True
        self.save()
    
    def reject(self, rejection_reason):
        """Reject service by admin"""
        self.status = 'rejected'
        self.rejection_reason = rejection_reason
        self.rejected_at = timezone.now()
        self.is_active = False
        self.save()
    
    def toggle_active(self):
        """Toggle service active/inactive"""
        self.is_active = not self.is_active
        if not self.is_active and self.status == 'approved':
            self.status = 'inactive'
        elif self.is_active and self.status == 'inactive':
            self.status = 'approved'
        self.save()
    
    def increment_views(self):
        """Increment view count"""
        self.views_count += 1
        self.save(update_fields=['views_count'])
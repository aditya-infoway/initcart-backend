#services/models/subcategory.py
from django.db import models
from django.conf import settings
import uuid
import os
import time

def generate_subcategory_id():
    return str(uuid.uuid4())[:8].upper()

def subcategory_image_path(instance, filename):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    return f"service_subcategories/{instance.id}_{timestamp}.{ext}"

class ServiceSubcategory(models.Model):
    SERVICE_CATEGORIES = [
        ('Gym', 'Gym'),
        ('Salon', 'Salon'),
        ('Hotel', 'Hotel'),
        ('Travel', 'Travel'),
        ('Finance', 'Finance'),
        ('Healthcare', 'Healthcare'),
        ('Education', 'Education'),
        ('Tech Industry', 'Tech Industry'),
        ('Restaurant', 'Restaurant'),
        ('Professional', 'Professional'),
        ('Real-Estate', 'Real-Estate'),
    ]
    
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]
    
    id = models.CharField(
        primary_key=True,
        max_length=20,
        default=generate_subcategory_id,
        editable=False
    )
    parent_service = models.CharField(
        max_length=50,
        choices=SERVICE_CATEGORIES,
        verbose_name="Parent Service"
    )
    subcategory_name = models.CharField(
        max_length=255,
        verbose_name="Subcategory Name"
    )
    description = models.TextField(
        verbose_name="Description"
    )
    image = models.ImageField(
        upload_to=subcategory_image_path,
        null=True,
        blank=True,
        verbose_name="Subcategory Image"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Active'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_subcategories'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Service Subcategory"
        verbose_name_plural = "Service Subcategories"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.subcategory_name} ({self.parent_service})"
    
    @property
    def service_type(self):
        """Map to Vendor model's service category choices"""
        category_mapping = {
            'Gym': 'gym',
            'Salon': 'salon',
            'Hotel': 'hotel',
            'Travel': 'travel_agency',
            'Finance': 'finance',
            'Healthcare': 'healthcare',
            'Education': 'education',
            'Tech Industry': 'tech',
            'Restaurant': 'restaurant',
            'Professional': 'professional',
            'Real-Estate': 'real_estate',
        }
        return category_mapping.get(self.parent_service, 'other')
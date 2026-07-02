from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import Vendor
from services.models.subcategory import ServiceSubcategory
from services.models.base import ServiceBaseModel

User = get_user_model()

class TechIndustryService(ServiceBaseModel):
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="tech_services")
    subcategory = models.ForeignKey(ServiceSubcategory, on_delete=models.SET_NULL, null=True, blank=True)
    business_name = models.CharField(max_length=255)
    address = models.CharField(max_length=251)
    location = models.CharField(max_length=500)
    country = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    city = models.CharField(max_length=50)
    open_time = models.TimeField()
    close_time = models.TimeField()
    contact_no = models.CharField(max_length=20)
    whatsapp_no = models.CharField(max_length=20)
    description = models.TextField()
    main_image = models.ImageField(upload_to='tech_industry_services/', null=True, blank=True)
    second_image = models.ImageField(upload_to='tech_industry_services/', null=True, blank=True)
    multi_images = models.ManyToManyField('TechIndustryImage', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_date = models.DateTimeField(blank=True, null=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_tech_services')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.business_name} ({self.vendor.user.username})"

class TechIndustryImage(models.Model):
    image = models.ImageField(upload_to='tech_industry_services/multi/')
    
class TechIndustryItem(models.Model):
    service = models.ForeignKey(TechIndustryService, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
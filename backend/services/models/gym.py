# services/models.py
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import Vendor
from services.models.subcategory import ServiceSubcategory
from services.models.base import ServiceBaseModel

User = get_user_model()

# class Country(models.Model):
#     id = models.AutoField(primary_key=True)
#     name = models.CharField(max_length=100)

#     class Meta:
#         db_table = 'country'
#         managed = False

#     def __str__(self):
#         return self.name

# class State(models.Model):
#     id = models.AutoField(primary_key=True)
#     name = models.CharField(max_length=100, db_column='stateName')

#     country = models.ForeignKey(
#         Country,
#         db_column='countryId',   # ✅ DB COLUMN NAME
#         on_delete=models.DO_NOTHING,
#         related_name='states'
#     )

#     class Meta:
#         db_table = 'state'
#         managed = False

#     def __str__(self):
#         return self.name

# class City(models.Model):
#     id = models.AutoField(primary_key=True)
#     name = models.CharField(max_length=100, db_column='cityName')

#     state = models.ForeignKey(
#         State,
#         db_column='stateId',   # ✅ DB COLUMN NAME
#         on_delete=models.DO_NOTHING,
#         related_name='cities'
#     )

#     class Meta:
#         db_table = 'city'
#         managed = False

#     def __str__(self):
#         return self.name

class GymService(ServiceBaseModel):
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="services")
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
    main_image = models.ImageField(upload_to='services/', null=True, blank=True)
    second_image = models.ImageField(upload_to='services/', null=True, blank=True)
    multi_images = models.ManyToManyField('ServiceImage', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_date = models.DateTimeField(blank=True, null=True)

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_properties')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.business_name} ({self.vendor.user.username})"

class ServiceImage(models.Model):
    image = models.ImageField(upload_to='services/multi/')
    
class ServiceItem(models.Model):
    service = models.ForeignKey(GymService, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

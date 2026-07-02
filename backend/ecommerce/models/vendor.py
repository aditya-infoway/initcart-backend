#ecommerce/models/vendor.py
from django.db import models
from django.contrib.auth import get_user_model
import uuid
import os
import time
from django.utils import timezone
from django.conf import settings

User = get_user_model()

def generate_request_id():
    return str(uuid.uuid4())[:20]

def unique_filename(instance, filename, doc_type):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    vendor_id = instance.id if instance.id else "temp"
    return f"{vendor_id}_{doc_type}_{timestamp}.{ext}"

def brand_logo_path(instance, filename):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    return f"brands/{instance.brand_name}_{timestamp}.{ext}"

def vendor_gst_path(instance, filename):
    return os.path.join("gst", unique_filename(instance, filename, "gst"))

def store_logo_path(instance, filename):
    return os.path.join("storelogo", unique_filename(instance, filename,"storelogo"))

def vendor_idproof_path(instance, filename):
    return os.path.join("idproof", unique_filename(instance, filename, "idproof"))

def vendor_licence_path(instance, filename):
    return os.path.join("license", unique_filename(instance, filename, "license"))

class Vendor(models.Model):
    VENDOR_TYPE_CHOICES = [
        ('product', 'Product Vendor'),
        ('service', 'Service Vendor'),
    ]

    PRODUCT_SUBTYPE_CHOICES = [
        ('retailer', 'Retailer'),
        ('wholesaler', 'Wholesaler'),
    ]

    SERVICE_CATEGORY_CHOICES = [
        ('salon', 'Salon'),
        ('gym', 'Gym'),
        ('real_estate', 'Real Estate'),
        ('travel_agency', 'Travel Agency'),
        ('finance', 'Finance'),
        ('tech', 'Tech Industry'),
        ('hotel', 'hotel'),
        ('healthcare', 'Healthcare'),
        ('education', 'Education'),
        ('professional', 'Professional'),
        ('restaurant', 'Restaurant'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
    ]

    VERIFICATION_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Verification Failed'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    vendor_type = models.CharField(max_length=20, choices=VENDOR_TYPE_CHOICES, default="product")
    vendor_subtype = models.CharField(max_length=50, blank=True, null=True)
    business_name = models.CharField(max_length=255)
    owner_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    password = models.CharField(max_length=255, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    ifsc_code = models.CharField(max_length=50, blank=True, null=True)
    upi_id = models.CharField(max_length=100, blank=True, null=True)
    licence_file = models.FileField(upload_to=vendor_licence_path, blank=True, null=True)
    gst_certificate = models.FileField(upload_to=vendor_gst_path, blank=True, null=True)
    store_logo = models.FileField(upload_to=store_logo_path, blank=True, null=True)
    id_proof = models.FileField(upload_to=vendor_idproof_path, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    verification_label = models.CharField(max_length=100, choices=VERIFICATION_CHOICES, default='pending')
    is_approved = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_vendors')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.is_approved = self.status == 'active'
        super().save(*args, **kwargs)

    def __str__(self):
        subtype_display = f" ({self.vendor_subtype})" if self.vendor_subtype else ""
        return f"{self.business_name} [{self.vendor_type}]{subtype_display}"

    @property
    def service_type(self):
        if self.vendor_type == 'service' and self.vendor_subtype:
            return self.vendor_subtype
        return None

class VendorApprovalRequest(models.Model):
    REQUEST_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='approval_request')
    request_id = models.CharField(max_length=100, primary_key=True, default=generate_request_id)
    date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=REQUEST_STATUS, default='pending')
    admin_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Approval Request - {self.vendor.business_name}"

class VendorWallet(models.Model):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='wallet')
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.vendor.business_name} - ₹{self.wallet_balance}"

class VendorWithdrawalRequest(models.Model):
    WITHDRAWAL_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
    ]
    PAYMENT_MODES = [
        ('bank_transfer', 'Bank Transfer'),
        ('upi', 'UPI'),
        ('paypal', 'PayPal'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='withdrawal_requests')
    request_id = models.CharField(max_length=100, unique=True, default=generate_request_id)
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    request_date = models.DateTimeField(auto_now_add=True)
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODES)
    status = models.CharField(max_length=20, choices=WITHDRAWAL_STATUS, default='pending')
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    paid_date = models.DateTimeField(blank=True, null=True)
    admin_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.vendor.business_name} - ₹{self.requested_amount}"

class Brand(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    brand_name = models.CharField(max_length=100, unique=True)
    brand_logo = models.ImageField(upload_to=brand_logo_path, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.brand_name
    
    @property
    def product_count(self):
        """Return count of approved products for this brand"""
        from ecommerce.models.product import Product
        return Product.objects.filter(brand=self, status="approved").count()
    
    @property
    def total_products(self):
        """Return total products (all status) for this brand"""
        from ecommerce.models.product import Product
        return Product.objects.filter(brand=self).count()

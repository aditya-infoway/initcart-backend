# pos/models/branch.py
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
import uuid
import os
import time
from django.utils import timezone

from ecommerce.models import vendor

User = get_user_model()

def generate_request_id():
    return str(uuid.uuid4())[:20]

def unique_filename(instance, filename, doc_type):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    vendor_id = instance.id if instance.id else "temp"
    return f"{doc_type}_{timestamp}.{ext}"

def branch_gst_path(instance, filename):
    return os.path.join("branch-gst", unique_filename(instance, filename, "branch-gst"))

def branch_logo_path(instance, filename):
    return os.path.join("branchlogo", unique_filename(instance, filename,"branchlogo"))

def branch_idproof_path(instance, filename):
    return os.path.join("branch-idproof", unique_filename(instance, filename, "branch-idproof"))

def branch_licence_path(instance, filename):
    return os.path.join("branch-license", unique_filename(instance, filename, "branch-license"))

class Branch(models.Model):
    BRANCH_TYPE_CHOICES = [
        ('fashion', 'Fashion'),
        ('mart', 'Mart'),
        ('electronics', 'Electronics'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    branch_type = models.CharField(max_length=20, choices=BRANCH_TYPE_CHOICES, default="fashion")
    branch_name = models.CharField(max_length=255)
    branch_code = models.CharField(
        max_length=3, blank=True, null=True, unique=True,
        help_text="3-letter branch code"
    )    
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
    licence_file = models.FileField(upload_to=branch_licence_path, blank=True, null=True)
    gst_certificate = models.FileField(upload_to=branch_gst_path, blank=True, null=True)
    branch_logo = models.FileField(upload_to=branch_logo_path, blank=True, null=True)
    id_proof = models.FileField(upload_to=branch_idproof_path, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_logged_in = models.BooleanField(default=False)
    last_active = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.branch_name
    
    def save(self, *args, **kwargs):
        # Normalize: uppercase, trim, empty string ko None bana do (unique constraint ke liye)
        if self.branch_code:
            code = self.branch_code.strip().upper()[:3]
            self.branch_code = code if code else None
        else:
            self.branch_code = None
        super().save(*args, **kwargs)
    def get_or_create_vendor(self):
        """Get or create vendor for this branch"""
        from ecommerce.models.vendor import Vendor
        
        # Check if vendor already exists
        if hasattr(self.user, 'vendor'):
            return self.user.vendor
        
        # Create vendor if not exists
        try:
            vendor = Vendor.objects.create(
                user=self.user,
                vendor_type='product',  # Default to product vendor
                business_name=self.branch_name,
                owner_name=self.owner_name,
                email=self.email,
                phone=self.phone,
                address=self.address,
                city=self.city,
                state=self.state,
                pincode=self.pincode,
                bank_name=self.bank_name,
                account_number=self.account_number,
                ifsc_code=self.ifsc_code,
                upi_id=self.upi_id,
                status='active',
                is_approved=True,
                verification_label='verified'
            )
            return vendor
        except Exception as e:
            print(f"Error creating vendor for branch {self.id}: {e}")
            return None


# SIGNAL - Automatically create vendor when branch is created
@receiver(post_save, sender=Branch)
def create_vendor_for_branch(sender, instance, created, **kwargs):
    """Create vendor automatically when branch is created"""
    if created and instance.user:
        vendor = instance.get_or_create_vendor()
        
        if vendor and instance.branch_logo: 
            vendor.store_logo = instance.branch_logo
            vendor.save(update_fields=['store_logo'])
            print(f"✅ Logo copied from branch to vendor: {instance.branch_logo.url}")


@receiver(post_delete, sender=Branch)
def delete_branch_user(sender, instance, **kwargs):
    """Delete associated Django User when branch is deleted"""
    if instance.user:
        try:
            user_id = instance.user_id
            user_email = instance.user.email if instance.user.email else "unknown"
            instance.user.delete()
            print(f" Deleted user {user_email} (ID: {user_id}) associated with branch '{instance.branch_name}'")
        except User.DoesNotExist:
            print(f" User already deleted for branch '{instance.branch_name}'")
        except Exception as e:
            print(f" Error deleting user for branch '{instance.branch_name}': {str(e)}")
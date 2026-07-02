# ecommerce/models/product.py

from decimal import Decimal
from django.db import models
from ecommerce.models.vendor import Vendor, Brand
from ecommerce.models.category import Category, SubCategory, SubSubCategory
import time 
import os 

# IMAGE PATHS (same as before)
def product_main_image_path(instance, filename):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    if instance.id and instance.product_name:
        product_name = instance.product_name.replace(" ", "_").lower()
        return f"products/main/{product_name}_{timestamp}.{ext}"
    else:
        return f"products/main/temp_{timestamp}.{ext}"

def product_thumbnail_path(instance, filename):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    if instance.id and instance.product_name:
        product_name = instance.product_name.replace(" ", "_").lower()
        return f"products/thumbnail/{product_name}_{timestamp}.{ext}"   
    else:
        return f"products/thumbnail/temp_{timestamp}.{ext}"
    
def product_gallery_path(instance, filename):
    timestamp = int(time.time())
    ext = filename.split('.')[-1]
    product_name = instance.product.product_name.replace(" ", "_").lower() if instance.product and instance.product.product_name else "product"
    return f"products/gallery/{product_name}_{timestamp}.{ext}"

class Product(models.Model):
    PRODUCT_STATUS = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    PRODUCT_TYPE = [
        ("simple", "Simple Product"),
        ("variant", "Variant Product"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="products")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)

    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, unique=True)

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    subcategory = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True)
    subsubcategory = models.ForeignKey(SubSubCategory, on_delete=models.SET_NULL, null=True, blank=True)

    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE, default="simple")

    keywords = models.TextField(blank=True, null=True)
    short_description = models.TextField(blank=True, null=True)
    full_description = models.TextField(blank=True, null=True)
    product_video_url = models.CharField(max_length=500, blank=True, null=True)

    main_image = models.ImageField(upload_to=product_main_image_path, blank=True, null=True)
    thumbnail_image = models.ImageField(upload_to=product_thumbnail_path, blank=True, null=True)

    product_condition = models.CharField(max_length=120, blank=True, null=True)
    manufacturing_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)
    return_policy = models.CharField(max_length=300, blank=True, null=True)
    estimated_delivery_time = models.CharField(max_length=120, blank=True, null=True)
    
    # NEW FIELDS
    description_features = models.JSONField(default=list, blank=True, null=True)
    specifications = models.JSONField(default=list, blank=True, null=True)
    
    # NEW: Warranty fields
    warranty_available = models.BooleanField(default=False)
    warranty_period = models.CharField(max_length=50, blank=True, null=True)
    warranty_type = models.CharField(max_length=100, blank=True, null=True)
    warranty_description = models.TextField(blank=True, null=True)

    free_shipping = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=PRODUCT_STATUS, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Add this method to get platform charge from category
    def get_platform_charge(self):
        """Get platform charge percentage from category"""
        if self.category:
            return self.category.platform_charge
        return Decimal('0.00')

    def calculate_vendor_receivable(self, final_price):
        """Calculate vendor receivable after platform charge on final price"""
        platform_charge = self.get_platform_charge()
        if platform_charge > 0:
            deduction = (final_price * platform_charge) / 100
            return final_price - deduction
        return final_price

    def __str__(self):
        vendor_name = self.vendor.business_name if hasattr(self.vendor, "business_name") else str(self.vendor)
        return f"{self.product_name} ({vendor_name})"


class ProductStock(models.Model):
    DISCOUNT_TYPES = [
        ("flat", "Flat"),
        ("percentage", "Percentage"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stocks")

    mrp = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    production_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, blank=True, null=True)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_quantity = models.IntegerField(default=0)

    color = models.CharField(max_length=120, blank=True, null=True)
    size = models.CharField(max_length=120, blank=True, null=True)

    barcode = models.CharField(max_length=255, blank=True, null=True)
    unit = models.CharField(max_length=120, blank=True, null=True)
    weight = models.CharField(max_length=120, blank=True, null=True)

    # NEW: Variant image
    variant_image = models.ImageField(upload_to='products/variants/', blank=True, null=True)

    final_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    maximum_order_quantity = models.IntegerField(default=10)

    # NEW FIELD: Store platform charge at time of product creation
    platform_charge_percent = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Platform charge percentage at time of product creation"
    )
    
    # NEW FIELD: Vendor receivable amount (after platform charge)
    vendor_receivable = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Amount vendor receives after platform charge"
    )

    def save(self, *args, **kwargs):
        """Auto-calculate final price and vendor receivable before saving"""
        try:
            selling_price = float(self.selling_price)
            tax_rate = float(self.tax)
            
            #  STEP 1: Calculate final price (with tax)
            if selling_price > 0:
                tax_amount = (selling_price * tax_rate) / 100
                self.final_price = round(selling_price + tax_amount, 2)
            else:
                self.final_price = 0
            
            #  STEP 2: Calculate vendor receivable on FINAL PRICE (including tax)
            if self.final_price > 0 and self.platform_charge_percent > 0:
                platform_deduction = (self.final_price * float(self.platform_charge_percent)) / 100
                self.vendor_receivable = round(self.final_price - platform_deduction, 2)
            else:
                self.vendor_receivable = self.final_price
                
        except (ValueError, TypeError):
            self.final_price = 0
            self.vendor_receivable = 0
            
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.product.product_name} - {self.color or '-'} / {self.size or '-'}"


class ProductGallery(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(upload_to=product_gallery_path)

    def __str__(self):
        return self.product.product_name
    
    
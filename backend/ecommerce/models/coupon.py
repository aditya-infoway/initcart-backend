# ecommerce/models/coupon.py - UPDATED
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from ecommerce.models.product import Product
from django.core.exceptions import ValidationError
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from ecommerce.models.vendor import Vendor
from ecommerce.models.order import Order
    
from decimal import Decimal
import json
from django.utils import timezone

User = get_user_model()


class Coupon(models.Model):
    COUPON_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('flat', 'Flat Discount'),
    ]
    
    APPLY_ON_CHOICES = [
        ('all_products', 'All Products'),
        ('category', 'Category'),
        ('product', 'Product'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    # Basic Information
    vendor = models.ForeignKey(
        Vendor, 
        on_delete=models.CASCADE, 
        related_name='coupons',
        help_text="Vendor who created this coupon"
    )
    coupon_type = models.CharField(max_length=20, choices=COUPON_TYPES, default='percentage')
    title = models.CharField(max_length=255, default='Default Coupon')
    code = models.CharField(max_length=50, unique=True)
    
    # Usage Limits
    limit_per_user = models.PositiveIntegerField(
        default=1,
        help_text="Maximum times a single user can use this coupon"
    )
    max_count = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Maximum total usage count (optional)"
    )
    used_count = models.PositiveIntegerField(default=0)
    
    # Discount Details
    discount_percent = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    discount_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Minimum Order Requirements
    min_order_value = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0
    )
    max_discount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True, 
        blank=True,
        help_text="Maximum discount amount (for percentage coupons)"
    )
    
    # Application Scope
    apply_on = models.CharField(max_length=20, choices=APPLY_ON_CHOICES, default='all_products')
    
    # NEW: Multiple selection fields (M2M)
    categories = models.ManyToManyField(
        Category, 
        related_name='coupons_by_category',
        blank=True
    )
    subcategories = models.ManyToManyField(
        SubCategory, 
        related_name='coupons_by_subcategory',
        blank=True
    )
    subsubcategories = models.ManyToManyField(
        SubSubCategory, 
        related_name='coupons_by_subsubcategory',
        blank=True
    )
    products = models.ManyToManyField(
        Product, 
        related_name='coupons_by_product',
        blank=True
    )
        
    # Validity Period
    start_date = models.DateTimeField(null=True, blank=True)  # Allow NULL
    expire_date = models.DateTimeField(null=True, blank=True)  # Allow NULL
    
    # Display & Status
    display_message = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Multiple selections JSON field (for easy access)
    multiple_selections = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['start_date', 'expire_date']),
        ]
    
    def __str__(self):
        vendor_name = self.vendor.business_name if self.vendor else "No Vendor"
        return f"{self.code} - {self.title} ({vendor_name})"
    
    def clean(self):
        # PRODUCT COUPON → product required
        if self.apply_on == "product":
            if not self.pk:
                return  # pehle save hone do, M2M baad me attach hota hai

            if not self.products.exists():
                raise ValidationError({
                    "products": "Product coupon must have at least one product."
                })
                
    def is_valid(self):
        """Check if coupon is currently valid"""
        now = timezone.now()
        
        # Check basic conditions
        if self.status != 'active':
            return False
            
        # Check validity period
        if self.start_date and self.expire_date:
            if not (self.start_date <= now <= self.expire_date):
                return False
        else:
            # If no validity period set, it's always valid if active
            pass
            
        # Check usage limits
        if self.max_count and self.used_count >= self.max_count:
            return False
            
        return True
    
    def is_valid_for_user(self, user):
        """Check if coupon is valid for specific user"""
        if not self.is_valid():
            return False
            
        # Check per user limit
        if self.limit_per_user:
            usage_count = CouponUsage.objects.filter(
                coupon=self,
                user=user
            ).count()
            if usage_count >= self.limit_per_user:
                return False
                
        return True
    
    def can_be_applied_to_product(self, product):
        """Check if coupon can be applied to a specific product"""
        if not product:
            return False
        
        # ✅ FIX 1: FIRST check if product belongs to coupon vendor
        if product.vendor_id != self.vendor_id:
            return False

        if self.apply_on == 'all_products':
            return True

        if self.apply_on == 'category':
            # Check category chain
            if self.subsubcategories.exists():
                return product.subsubcategory_id in self.subsubcategories.values_list('id', flat=True)

            if self.subcategories.exists():
                return product.subcategory_id in self.subcategories.values_list('id', flat=True)

            if self.categories.exists():
                return product.category_id in self.categories.values_list('id', flat=True)

            return False

        if self.apply_on == 'product':
            return self.products.filter(id=product.id).exists()

        return False


    def calculate_discount(self, amount):
        """
        Decimal-safe discount calculation
        """
        if not self.is_valid():
            return Decimal("0.00")

        amount = Decimal(str(amount))

        if self.coupon_type == 'percentage' and self.discount_percent:
            percent = Decimal(str(self.discount_percent)) / Decimal("100")
            discount = amount * percent
    
            if self.max_discount:
                max_discount = Decimal(str(self.max_discount))
                if discount > max_discount:
                    return max_discount

            return discount

        elif self.coupon_type == 'flat' and self.discount_amount:
            flat_amount = Decimal(str(self.discount_amount))
            return flat_amount if flat_amount < amount else amount

        return Decimal("0.00")
    
    def get_discount_display(self):
        """Get discount display text"""
        if self.coupon_type == 'percentage':
            return f"{self.discount_percent}% "
        elif self.coupon_type == 'flat':
            return f"₹{self.discount_amount} "
        return ""


class CouponUsage(models.Model):
    """Track coupon usage by customers"""
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True)
    used_at = models.DateTimeField(auto_now_add=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        unique_together = [['coupon', 'user', 'order']]
        indexes = [
            models.Index(fields=['coupon', 'user']),
        ]
    
    def __str__(self):
        return f"{self.user.email} used {self.coupon.code}"
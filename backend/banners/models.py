# models.py
from django.db import models

class SliderImage(models.Model):
    image = models.ImageField(upload_to="slider/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Slider {self.id}"
    
class BigAd(models.Model):
    image = models.ImageField(upload_to="ads/big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class SmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]  # only 2 fixed slots

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"
    
class SuperAdminProfile(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    
    profile_image = models.ImageField(
        upload_to="admin_profile/",
        blank=True,
        null=True
    )
    
        # ✅ NEW: Brochure PDF field
    brochure_pdf = models.FileField(
        upload_to="brochures/",
        blank=True,
        null=True,
        help_text="Upload company brochure (PDF only)"
    )

    youtube = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    whatsapp = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# models.py - Mobile Banner Model (Simple)

# models.py - Ensure model is correct

class MobileBanner(models.Model):
    """Mobile banner - simple, no validation"""
    image = models.ImageField(upload_to="mobile/banners/", null=True, blank=True)
    title = models.CharField(max_length=200, blank=True, default='')
    subtitle = models.CharField(max_length=200, blank=True, default='')
    button_text = models.CharField(max_length=50, blank=True, default='')
    button_url = models.URLField(blank=True, default='')
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order']
        db_table = 'mobile_banner'
    
    def __str__(self):
        return f"Mobile Banner {self.id} - {self.title or 'No Title'}"


class MobileCategoryCard(models.Model):
    """Mobile shop by category cards with gradient colors"""
    subcategory = models.ForeignKey('ecommerce.Subcategory', on_delete=models.CASCADE, related_name='mobile_cards')
    gradient_start = models.CharField(max_length=20, default="#E8F4FD")
    gradient_end = models.CharField(max_length=20, default="#BBDEFB")
    accent_color = models.CharField(max_length=20, default="#1565C0")
    header_color = models.CharField(max_length=20, default="#1565C0")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"Card: {self.subcategory.name}"


class MobileDealCard(models.Model):
    """Mobile deal cards (Flash/Featured)"""
    DEAL_TYPES = [
        ('flash', 'Flash Deal'),
        ('featured', 'Featured Deal'),
    ]
    deal_type = models.CharField(max_length=20, choices=DEAL_TYPES, default='flash')
    product = models.ForeignKey('ecommerce.Product', on_delete=models.CASCADE, related_name='mobile_deal_cards')
    discount_percentage = models.PositiveSmallIntegerField(default=0)
    gradient_start = models.CharField(max_length=20, default="#FFF3E0")
    gradient_end = models.CharField(max_length=20, default="#FFE0B2")
    accent_color = models.CharField(max_length=20, default="#E65100")
    header_color = models.CharField(max_length=20, default="#BF360C")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['deal_type', 'order']
    
    
    def __str__(self):
        return f"{self.get_deal_type_display()}: {self.product.product_name}"

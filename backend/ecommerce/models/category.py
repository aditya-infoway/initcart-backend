#ecommerce/models/category.py
from decimal import Decimal
import os
from django.db import models
import time
import uuid
from django.core.validators import RegexValidator

# -------------------- ICON PATHS --------------------
def category_icon_path(instance, filename):
    ext = os.path.splitext(filename)[1]  # .jpg, .png
    unique_name = f"{int(time.time())}_{uuid.uuid4().hex}{ext}"
    return f"category/{unique_name}"

def subcategory_icon_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    unique_name = f"{int(time.time())}_{uuid.uuid4().hex}{ext}"
    return f"subcategory/{unique_name}"

def subsubcategory_icon_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    unique_name = f"{int(time.time())}_{uuid.uuid4().hex}{ext}"
    return f"subsubcategory/{unique_name}"

def category_banner_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f"category_banner/{int(time.time())}_{uuid.uuid4().hex}{ext}"

def subcategory_banner_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f"subcategory_banner/{int(time.time())}_{uuid.uuid4().hex}{ext}"

# -------------------- MODELS --------------------

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    icon = models.ImageField(upload_to=category_icon_path, null=True, blank=True)
    status = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    featured_order = models.IntegerField(default=0)
    banner_image = models.ImageField(upload_to=category_banner_path, null=True, blank=True)

    #  New fields for homepage slider and platform charge
    web_home = models.BooleanField(
        default=False, 
        help_text="Show this category on homepage sliders"
    )
    platform_charge = models.DecimalField(
        max_digits=5,  # 99.99% max
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Platform charge percentage for products in this category"
    )

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['-web_home', 'name']

class SubCategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=150, blank=True, default="")
    icon = models.ImageField(upload_to=subcategory_icon_path, null=True, blank=True)
    banner_image = models.ImageField(upload_to=subcategory_banner_path, null=True, blank=True)
    status = models.BooleanField(default=True)


    class Meta:
        unique_together = ("category", "name")

    def __str__(self):
        return f"{self.category.name} → {self.name}"


class SubSubCategory(models.Model):
    subcategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name="subsubcategories")
    name = models.CharField(max_length=255)
    icon = models.ImageField(upload_to=subsubcategory_icon_path, null=True, blank=True)
    status = models.BooleanField(default=True)

    class Meta:
        unique_together = ("subcategory", "name")

    def __str__(self):
        return f"{self.subcategory.category.name} → {self.subcategory.name} → {self.name}"


class CategorySectionSetting(models.Model):
    """Homepage 'Shop by category' section ka heading. Sirf ek row use hoti hai."""
    eyebrow = models.CharField(max_length=100, blank=True, default="Shop by category")
    heading = models.CharField(max_length=255, default="Curated for retailers and shoppers")

    def __str__(self):
        return self.heading

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SubCategorySectionSetting(models.Model):
    """Sab subcategory cards ka common layer colour. Sirf ek row use hoti hai."""
    overlay_color = models.CharField(
        max_length=7,
        default="#000000",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Enter Valid hex colour, Like #1a1a1a")],
    )

    def __str__(self):
        return self.overlay_color

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj    
#ecommerce/models/category.py
from decimal import Decimal
import os
from django.db import models
import time
import uuid

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

# -------------------- MODELS --------------------

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    icon = models.ImageField(upload_to=category_icon_path, null=True, blank=True)
    status = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    featured_order = models.IntegerField(default=0)

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
    icon = models.ImageField(upload_to=subcategory_icon_path, null=True, blank=True)
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

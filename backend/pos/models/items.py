# pos/models/items.py
from django.db import models
from pos.models.branch import Branch
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from ecommerce.models.vendor import Brand
from django.core.validators import MinValueValidator

ENTRY_TYPE_CHOICES = [
    ('company', 'Company'),
    ('manual', 'Manual'),
]

class items(models.Model):
    # Basic fields
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    itemName = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    brand = models.CharField(max_length=50, blank=True, null=True)
    c_brand = models.ForeignKey(Brand, on_delete=models.CASCADE, blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True)
    subCategory = models.CharField(max_length=50, blank=True, null=True)
    subSubCategory = models.CharField(max_length=50, blank=True, null=True)
    c_category = models.ForeignKey(Category, on_delete=models.CASCADE, blank=True, null=True)
    c_subCategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE, blank=True, null=True)
    c_subSubCategory = models.ForeignKey(SubSubCategory, on_delete=models.CASCADE, blank=True, null=True)
    group = models.ForeignKey(
        'pos.ItemGroup', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='items'
    )
    unit = models.ForeignKey(
        'pos.ItemUnit', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='items'
    )
    created_by_superadmin= models.BooleanField(default=False)
    hsnCode = models.CharField(max_length=20, blank=True, null=True)
    taxSlab = models.CharField(max_length=20, blank=True, null=True)
    website_display = models.BooleanField(default=False)
    
    # Product description fields
    short_description = models.TextField(blank=True, null=True)
    full_description = models.TextField(blank=True, null=True)
    keywords = models.TextField(blank=True, null=True)
    
    # Product images
    main_image = models.ImageField(upload_to='items/product_images/', blank=True, null=True)
    thumbnail_image = models.ImageField(upload_to='items/product_images/', blank=True, null=True)
    gallery = models.JSONField(default=list, blank=True, null=True)
    
    # Product meta
    product_condition = models.CharField(max_length=120, blank=True, null=True, default='New')
    return_policy = models.CharField(max_length=300, blank=True, null=True)
    estimated_delivery_time = models.CharField(max_length=120, blank=True, null=True)
    free_shipping = models.BooleanField(default=False)   
    
    # Warranty fields
    warranty_available = models.BooleanField(default=False)
    warranty_period = models.CharField(max_length=50, blank=True, null=True)
    warranty_type = models.CharField(max_length=100, blank=True, null=True)
    warranty_description = models.TextField(blank=True, null=True)
    
    # JSON fields for dynamic data
    description_features = models.JSONField(default=list, blank=True, null=True)
    specifications = models.JSONField(default=list, blank=True, null=True)
    
    # Status for website approval
    website_status = models.CharField(
        max_length=20, 
        choices=[
            ('pending', 'Pending Approval'),
            ('approved', 'Approved '),
            ('rejected', 'Rejected'),
            ('draft', 'Draft')
        ],
        default='draft'
    )

    #  FIX: Use string reference to avoid circular import issues
    linked_product = models.ForeignKey(
        'ecommerce.product',  # Use string reference instead of direct import
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='linked_items'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.itemName
    
    def get_vendor_for_branch(self):
        """Get vendor associated with this branch"""
        # Assuming branch has a user, and user has a vendor
        if self.branch and hasattr(self.branch.user, 'vendor'):
            return self.branch.user.vendor
        return None


class itemvariants(models.Model):
    item = models.ForeignKey(items, related_name="variants", on_delete=models.CASCADE)
    purchasePrice = models.FloatField(default=0, validators=[MinValueValidator])
    salesPrice = models.FloatField(default=0, validators=[MinValueValidator])
    mrp = models.FloatField(default=0, validators=[MinValueValidator])
    barcode = models.CharField(max_length=100, blank=True, null=True)
    opStock = models.IntegerField(default=0,validators=[MinValueValidator(0)])
    basicAmount = models.FloatField(default=0)
    discountAmount = models.FloatField(default=0)
    taxAmount = models.FloatField(default=0)
    netValue = models.FloatField(default=0)
    current_stock = models.IntegerField(default=0)
    branchPrice = models.FloatField(default=0)
    
    # Dynamic fields like size, color, etc.
    size = models.CharField(max_length=20, blank=True, null=True)
    color = models.CharField(max_length=20, blank=True, null=True)
    srno = models.CharField(max_length=50, blank=True, null=True)
    warrantydate = models.DateField(blank=True, null=True)

    variant_image = models.ImageField(upload_to='items/variant_images/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.item.itemName} - {self.color or ''} {self.size or ''}"
    
    
    
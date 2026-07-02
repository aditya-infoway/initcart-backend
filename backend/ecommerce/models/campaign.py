# ecommerce/models/campaign.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from datetime import date, datetime, timedelta

class Campaign(models.Model):
    CAMPAIGN_TYPES = [
        ('Flash', 'Flash Deal'),
        ('Deal of the Day', 'Deal of the Day'),
        ('Featured', 'Featured Products'),
    ]
    
    DEAL_OF_DAY_PLACEMENTS = [
        ('main', 'Main Section'),
        ('banner', 'Banner'),
        ('product_list', 'Product List'),
    ]
    
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
        ('Expired', 'Expired'),
    ]
    
    campaign_name = models.CharField(max_length=255)
    campaign_type = models.CharField(max_length=50, choices=CAMPAIGN_TYPES)
    
    # Deal of the Day specific fields
    deal_of_day_placement = models.CharField(
        max_length=20, 
        choices=DEAL_OF_DAY_PLACEMENTS, 
        null=True, 
        blank=True
    )
    
    # Super admin settings
    minimum_discount = models.IntegerField(default=0, help_text="Minimum discount percentage for deals")
    minimum_product_limit = models.IntegerField(default=1, help_text="Minimum products required per vendor")
    
    categories = models.ManyToManyField('Category', related_name='campaigns', blank=True)
    subcategory = models.ForeignKey('SubCategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='campaigns')
    subsubcategory = models.ForeignKey('SubSubCategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='campaigns')
    
    # Vendor selection
    selected_vendors = models.ManyToManyField(
        'Vendor', 
        related_name='selected_campaigns', 
        blank=True,
        help_text="Vendors selected for participation"
    )
    
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    description = models.TextField(blank=True)
    max_products_per_vendor = models.IntegerField(default=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def clean(self):
        """Validation based on campaign type"""
        
        # 🔴 FLASH DEAL: No date validation (can start and end same day)
        if self.campaign_type == 'Flash':
            # Flash deals can be for few hours, no date validation needed
            # Just ensure it's not negative duration (end after start)
            if self.end_datetime <= self.start_datetime:
                # For flash deals, allow same day/hour deals but not negative duration
                if self.end_datetime <= self.start_datetime:
                    raise ValidationError("End datetime must be after start datetime")
            pass
            
        # 🔴 DEAL OF THE DAY: Must be at least 24 hours, can't overlap
        elif self.campaign_type == 'Deal of the Day':
            # Validate minimum duration (at least 24 hours)
            if self.end_datetime <= self.start_datetime:
                raise ValidationError("End datetime must be after start datetime")
            
            duration = self.end_datetime - self.start_datetime
            if duration < timedelta(hours=24) and self.status == 'Active':
                raise ValidationError("Deal of the Day must be active for at least 24 hours")
            
            # Check for overlapping active Deal of the Day campaigns
            if self.status in ['Active', 'Draft']:
                now = timezone.now()
                overlapping = Campaign.objects.filter(
                    campaign_type='Deal of the Day',
                    status__in=['Active', 'Draft'],
                    start_datetime__lte=self.end_datetime,
                    end_datetime__gte=self.start_datetime
                ).exclude(id=self.id)
                
                if overlapping.exists():
                    campaign_names = [c.campaign_name for c in overlapping]
                    raise ValidationError(
                        f"Cannot have overlapping Deal of the Day campaigns. "
                        f"Already active/draft: {', '.join(campaign_names)}"
                    )
        
        # 🔴 FEATURED: Standard validation
        elif self.campaign_type == 'Featured':
            if self.end_datetime <= self.start_datetime:
                raise ValidationError("End datetime must be after start datetime")
            
            # Check for overlapping active Featured campaigns
            if self.status == 'Active':
                overlapping_active = Campaign.objects.filter(
                    campaign_type='Featured',
                    status='Active',
                    start_datetime__lte=self.end_datetime,
                    end_datetime__gte=self.start_datetime
                ).exclude(id=self.id)
                
                if overlapping_active.exists():
                    raise ValidationError(
                        f"Cannot have overlapping active Featured campaigns. "
                        f"Another Featured campaign is already active during this period."
                    )
        
        # Validate minimum discount
        if self.minimum_discount < 0 or self.minimum_discount > 100:
            raise ValidationError("Minimum discount must be between 0 and 100")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        now = timezone.now()
        return self.status == 'Active' and self.start_datetime <= now <= self.end_datetime
    
    @property
    def vendor_count(self):
        return self.participations.count()
    
    @property
    def approved_products_count(self):
        try:
            return CampaignProduct.objects.filter(
                participation__campaign=self,
                status='Approved'
            ).count()
        except:
            return 0
    
    @property
    def upcoming_deals_count(self):
        """Count of upcoming deals after current time"""
        now = timezone.now()
        return Campaign.objects.filter(
            start_datetime__gt=now,
            status__in=['Draft', 'Active']
        ).count()
    
    @property
    def next_upcoming_deal(self):
        """Get the next upcoming deal"""
        now = timezone.now()
        return Campaign.objects.filter(
            start_datetime__gt=now,
            status__in=['Draft', 'Active']
        ).order_by('start_datetime').first()
    @property
    def is_currently_active(self):
       """Check if campaign is currently active based on date/time"""
       now = timezone.now()
       return self.status == 'Active' and self.start_datetime <= now <= self.end_datetime
    def get_available_vendors_for_date(self, target_date=None):
        """Get vendors available for selection on a specific date"""
        if target_date is None:
            target_date = date.today()
        
        # Get all active vendors
        from ecommerce.models.vendor import Vendor
        all_vendors = Vendor.objects.filter(status='active', is_approved=True)
        
        # Get vendors who have already been sent participation request today
        vendors_with_request_today = CampaignParticipation.objects.filter(
            campaign=self,
            vendor_type='product',
            applied_at__date=target_date
        ).values_list('vendor_id', flat=True)
        
        # Exclude vendors who already have request today
        available_vendors = all_vendors.exclude(id__in=vendors_with_request_today)
        
        return available_vendors
        
 
    def save(self, *args, **kwargs):
        # ✅ AUTO-EXPIRE: pehle check karo
        if self.end_datetime < timezone.now():
            self.status = 'Expired'
        
        # ✅ VALIDATION: Expired campaign ko Active nahi kar sakte
        if self.pk:  # Existing campaign
            try:
                old = Campaign.objects.get(pk=self.pk)
                if old.status == 'Expired' and self.status == 'Active':
                    if self.end_datetime < timezone.now():
                        raise ValidationError(
                            "Cannot activate an expired campaign. "
                            "Extend the end date first."
                        )
            except Campaign.DoesNotExist:
                pass
        
        self.clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def bulk_expire_check(cls):
        """Safety net - saari campaigns ek saath check karo"""
        now = timezone.now()
        expired = cls.objects.filter(
            end_datetime__lt=now,
            status='Active'
        )
        count = expired.count()
        if count:
            print(f"⚠️ Found {count} expired campaigns still active!")
            expired.update(status='Expired')
            print(f"✅ Fixed: {count} campaigns expired")
        return count
    
    @classmethod
    def auto_expire(cls):
        """सभी expired campaigns को expire करो"""
        now = timezone.now()
        count = cls.objects.filter(
            end_datetime__lt=now,
            status='Active'
        ).update(status='Expired')
        return count
    
    @property
    def duration(self):
        return f"{self.start_datetime.strftime('%Y-%m-%d %H:%M')} to {self.end_datetime.strftime('%Y-%m-%d %H:%M')}"
    
    def __str__(self):
        return f"{self.campaign_name} ({self.campaign_type})"

    
class CampaignParticipation(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='participations')
    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE, related_name='campaign_participations')
    products = models.ManyToManyField('Product', through='CampaignProduct')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    applied_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_participations')
    rejection_reason = models.TextField(blank=True, null=True)
    
        # नया field - Deal of the Day के लिए hero banner configure किया गया है कि नहीं
    is_banner_configured = models.BooleanField(default=False)
    
    # नया field - Vendor ने discount update किया है कि नहीं
    discount_updated = models.BooleanField(default=False)
    
    # नया field - Vendor द्वारा update करने पर product फिर से pending हो जाएगा
    vendor_updated_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['campaign', 'vendor']
        ordering = ['-applied_at']
    
    @property
    def product_count(self):
        return self.campaign_products.count()
    
    @property
    def approved_products_count(self):
        return self.campaign_products.filter(status='Approved').count()
    
    @property
    def pending_products_count(self):
        return self.campaign_products.filter(status='Pending').count()
    
    @property
    def meets_minimum_requirements(self):
        """Check if vendor meets minimum requirements"""
        campaign = self.campaign
        
        # Check minimum product count
        if self.campaign_products.count() < campaign.minimum_product_limit:
            return False, f"Minimum {campaign.minimum_product_limit} products required"
        
        # Check minimum discount for approved products
        approved_products = self.campaign_products.filter(status='Approved')
        for cp in approved_products:
            if cp.discount_percentage and cp.discount_percentage < campaign.minimum_discount:
                return False, f"Minimum {campaign.minimum_discount}% discount required"
        
        return True, "Meets all requirements"
    
    def __str__(self):
        return f"{self.vendor.business_name} - {self.campaign.campaign_name}"


class CampaignProduct(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    
    participation = models.ForeignKey(CampaignParticipation, on_delete=models.CASCADE, related_name='campaign_products')
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='campaign_participations')
    special_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_percentage = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    added_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Deal of the Day placement
    deal_of_day_placement = models.CharField(
        max_length=20, 
        choices=Campaign.DEAL_OF_DAY_PLACEMENTS, 
        null=True, 
        blank=True
    )
    
    class Meta:
        unique_together = ['participation', 'product']
        ordering = ['-added_at']
        
    # Hero Banner specific fields
    banner_image = models.ImageField(
        upload_to='deal_of_day_banners/', 
        null=True, 
        blank=True,
        help_text="Banner image for hero section (1970x700 pixels)"
    )
    banner_title = models.CharField(max_length=255, null=True, blank=True)
    banner_subtitle = models.CharField(max_length=500, null=True, blank=True)
    banner_button_url = models.URLField(max_length=500, null=True, blank=True)
    
    @property
    def has_banner_details(self):
        """Check if banner details are filled"""
        return bool(self.banner_image and self.banner_title)
    
    @property
    def original_price(self):
        try:
            if self.product.stocks.first():
                return float(self.product.stocks.first().selling_price)
        except:
            pass
        return 0
    
    @property
    def final_price(self):
        try:
            if self.special_price:
                return float(self.special_price)
            elif self.discount_percentage and self.original_price > 0:
                discount = (self.original_price * self.discount_percentage) / 100
                return round(self.original_price - discount, 2)
            return self.original_price
        except:
            return 0
    
    @property
    def discount_amount(self):
        """Calculate actual discount amount"""
        try:
            if self.discount_percentage:
                return (self.original_price * self.discount_percentage) / 100
            elif self.special_price:
                return self.original_price - float(self.special_price)
        except:
            pass
        return 0
    
    def __str__(self):
        return f"{self.product.product_name} in {self.participation.campaign.campaign_name}"
    
    @property
    def vendor_name(self):
        """Get vendor name for admin panel"""
        try:
            return self.product.vendor.business_name if self.product.vendor else ''
        except:
            return ''
    
    @property
    def product_details(self):
        """Get minimal product details"""
        try:
            return {
                'id': self.product.id,
                'product_name': self.product.product_name,
                'main_image': self.product.main_image.url if self.product.main_image else None,
                'category': {
                    'name': self.product.category.name if self.product.category else None
                }
            }
        except:
            return {
                'id': 0,
                'product_name': 'Unknown Product',
                'main_image': None,
                'category': {'name': 'No Category'}
            }
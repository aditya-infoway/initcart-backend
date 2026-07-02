# ecommerce/serializers/campaign_serializers.py
from rest_framework import serializers
from ecommerce.models.campaign import Campaign, CampaignParticipation, CampaignProduct
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.category_serializers import CategorySerializer
from ecommerce.serializers.product_serializers import ProductSerializer
from ecommerce.serializers.vendor_serializers import VendorSerializer
from django.utils import timezone
from datetime import date, timedelta

class CampaignSerializer(serializers.ModelSerializer):
    categories_details = CategorySerializer(source='categories', many=True, read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    duration = serializers.CharField(read_only=True)
    vendor_count = serializers.IntegerField(read_only=True)
    approved_products_count = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    start_datetime = serializers.DateTimeField(format="%Y-%m-%dT%H:%M")
    end_datetime = serializers.DateTimeField(format="%Y-%m-%dT%H:%M")
    
    # New fields
    selected_vendors_details = VendorSerializer(source='selected_vendors', many=True, read_only=True)
    available_vendors = serializers.SerializerMethodField()
    upcoming_deals_count = serializers.IntegerField(read_only=True)
    next_upcoming_deal = serializers.SerializerMethodField()
    
    class Meta:
        model = Campaign
        fields = [
            'id', 'campaign_name', 'campaign_type', 'deal_of_day_placement',
            'categories', 'subcategory', 'subsubcategory',
            'categories_details', 'start_datetime', 'end_datetime', 'description',
            'max_products_per_vendor', 'minimum_discount', 'minimum_product_limit',
            'selected_vendors', 'selected_vendors_details', 'available_vendors',
            'status', 'created_by', 'created_by_name', 'created_at', 'updated_at',
            'is_active', 'duration', 'vendor_count', 'approved_products_count',
            'upcoming_deals_count', 'next_upcoming_deal'
        ]
        extra_kwargs = {
            'created_by': {'read_only': True},
        }
        
    def validate(self, data):
        """
        Additional validation for campaign based on campaign type
        """
        # Get values from data or existing instance
        campaign_type = data.get('campaign_type', getattr(self.instance, 'campaign_type', None))
        status = data.get('status', getattr(self.instance, 'status', None))
        start_datetime = data.get('start_datetime', getattr(self.instance, 'start_datetime', None))
        end_datetime = data.get('end_datetime', getattr(self.instance, 'end_datetime', None))
        
        # Basic validation: end datetime must be after start datetime for ALL campaign types
        if start_datetime and end_datetime:
            if end_datetime <= start_datetime:
                raise serializers.ValidationError({
                    'end_datetime': 'End datetime must be after start datetime'
                })
        
        # 🔴 FLASH DEAL: No additional validations
        if campaign_type == 'Flash':
            # Flash deals can be created for any duration
            # No overlapping checks needed
            pass
            
        # 🔴 DEAL OF THE DAY: Must be at least 24 hours, can't overlap
        elif campaign_type == 'Deal of the Day':
            if status == 'Active' or status == 'Draft':
                now = timezone.now()
                
                # Check duration (at least 24 hours for active deals)
                if status == 'Active' and start_datetime and end_datetime:
                    duration = end_datetime - start_datetime
                    if duration < timedelta(hours=24):
                        raise serializers.ValidationError({
                            'non_field_errors': [
                                f"Deal of the Day must be active for at least 24 hours. "
                                f"Current duration: {duration.total_seconds() / 3600:.1f} hours"
                            ]
                        })
                
                # Check for overlapping Deal of the Day campaigns
                active_deals = Campaign.objects.filter(
                    campaign_type='Deal of the Day',
                    status__in=['Active', 'Draft'],
                    start_datetime__lte=end_datetime,
                    end_datetime__gte=start_datetime
                )
                
                # Exclude current instance if updating
                if self.instance:
                    active_deals = active_deals.exclude(id=self.instance.id)
                
                if active_deals.exists():
                    deal_names = [deal.campaign_name for deal in active_deals]
                    raise serializers.ValidationError({
                        'non_field_errors': [
                            f"Cannot have overlapping Deal of the Day campaigns. "
                            f"Already active/draft: {', '.join(deal_names)}"
                        ]
                    })
        
        # 🔴 FEATURED: Standard validation with no overlap
        elif campaign_type == 'Featured':
            if status == 'Active':
                # Check for overlapping active Featured campaigns
                active_featured = Campaign.objects.filter(
                    campaign_type='Featured',
                    status='Active',
                    start_datetime__lte=end_datetime,
                    end_datetime__gte=start_datetime
                )
                
                if self.instance:
                    active_featured = active_featured.exclude(id=self.instance.id)
                
                if active_featured.exists():
                    raise serializers.ValidationError({
                        'non_field_errors': [
                            "Cannot have overlapping active Featured campaigns"
                        ]
                    })
        
        return data

    def get_approved_products_count(self, obj):
        return obj.approved_products_count
    
    def get_available_vendors(self, obj):
        """Get available vendors for current date"""
        today = date.today()
        try:
            available_vendors = obj.get_available_vendors_for_date(today)
            return VendorSerializer(available_vendors, many=True).data
        except:
            return []
    
    def get_next_upcoming_deal(self, obj):
        try:
            next_deal = Campaign.objects.filter(
                start_datetime__gt=timezone.now(),
                status__in=['Draft', 'Active']
            ).exclude(id=obj.id).order_by('start_datetime').first()
            
            if next_deal:
                return {
                    'id': next_deal.id,
                    'campaign_name': next_deal.campaign_name,
                    'start_datetime': next_deal.start_datetime,
                    'campaign_type': next_deal.campaign_type
                }
        except:
            pass
        return None


class CampaignProductSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    original_price = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(source='product.vendor.business_name', read_only=True)
    discount_amount = serializers.SerializerMethodField()
    has_banner_details = serializers.BooleanField(read_only=True)
    banner_image_url = serializers.SerializerMethodField()
    is_banner_configured = serializers.BooleanField(read_only=True)
    discount_updated = serializers.BooleanField(read_only=True)
    vendor_updated_at = serializers.DateTimeField(read_only=True)
    
    # Add these fields directly from model
    banner_title = serializers.CharField(read_only=True)
    banner_subtitle = serializers.CharField(read_only=True, allow_blank=True)
    banner_button_url = serializers.URLField(read_only=True, allow_blank=True)
    
    class Meta:
        model = CampaignProduct
        fields = [
            'id', 'product', 'product_details', 'original_price', 'special_price',
            'discount_percentage', 'final_price', 'discount_amount', 'deal_of_day_placement',
            'has_banner_details', 'banner_image_url', 'is_banner_configured', 
            'discount_updated', 'vendor_updated_at',
            'banner_title', 'banner_subtitle', 'banner_button_url',
            'status', 'vendor_name', 'added_at', 'approved_at', 'rejection_reason'
        ]
        read_only_fields = ['added_at', 'approved_at', 'banner_title', 'banner_subtitle', 'banner_button_url']
        
    def get_banner_image_url(self, obj):
        """Build absolute URL for banner image"""
        if obj.banner_image and obj.banner_image.name:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None
    
    def get_original_price(self, obj):
        return obj.original_price
    
    def get_final_price(self, obj):
        return obj.final_price
    
    def get_discount_amount(self, obj):
        return obj.discount_amount
    def validate_deal_of_day_placement(self, value):
        """Ensure only Deal of the Day products can have placement"""
        if value:
            campaign = self.instance.participation.campaign if self.instance else None
            if campaign and campaign.campaign_type != 'Deal of the Day':
                raise serializers.ValidationError(
                    "Placement can only be set for Deal of the Day products"
                )
        return value
    def validate(self, data):
        # Validate minimum discount for campaign
        instance = self.instance
        if instance:
            campaign = instance.participation.campaign
            discount_percentage = data.get('discount_percentage', instance.discount_percentage)
            
            if discount_percentage and campaign.minimum_discount > 0:
                if discount_percentage < campaign.minimum_discount:
                    raise serializers.ValidationError(
                        f"Discount must be at least {campaign.minimum_discount}%"
                    )
        
        return data


class CampaignParticipationSerializer(serializers.ModelSerializer):
    campaign_details = CampaignSerializer(source='campaign', read_only=True)
    vendor_details = VendorSerializer(source='vendor', read_only=True)
    product_count = serializers.IntegerField(source='campaign_products.count', read_only=True)
    approved_products_count = serializers.IntegerField(read_only=True)
    pending_products_count = serializers.IntegerField(read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    meets_minimum_requirements = serializers.SerializerMethodField()
    
    class Meta:
        model = CampaignParticipation
        fields = [
            'id', 'campaign', 'campaign_details', 'vendor', 'vendor_details',
            'status', 'applied_at', 'approved_at', 'approved_by', 'approved_by_name',
            'rejection_reason', 'product_count', 'approved_products_count',
            'pending_products_count', 'meets_minimum_requirements'
        ]
        read_only_fields = ['applied_at', 'approved_at']
    
    def get_meets_minimum_requirements(self, obj):
        meets, message = obj.meets_minimum_requirements
        return {'meets': meets, 'message': message}


class VendorCampaignParticipationSerializer(serializers.ModelSerializer):
    campaign_details = CampaignSerializer(source='campaign', read_only=True)
    selected_products = serializers.SerializerMethodField()
    available_products = serializers.SerializerMethodField()
    remaining_slots = serializers.SerializerMethodField()
    meets_minimum_requirements = serializers.SerializerMethodField()
    
    class Meta:
        model = CampaignParticipation
        fields = [
            'id', 'campaign', 'campaign_details', 'status', 'applied_at',
            'selected_products', 'available_products', 'remaining_slots',
            'meets_minimum_requirements'
        ]
        read_only_fields = ['status', 'applied_at']
    
    def get_selected_products(self, obj):
        return CampaignProductSerializer(
            obj.campaign_products.all(),
            many=True
        ).data
    
    def get_available_products(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return []
        
        campaign = obj.campaign
        
        # Get vendor's approved products
        products = vendor.products.filter(status='approved')
        
        # Filter by campaign categories
        campaign_categories = campaign.categories.all()
        if campaign_categories.exists():
            products = products.filter(category__in=campaign_categories)
        
        # Exclude already selected products
        selected_product_ids = obj.campaign_products.values_list('product_id', flat=True)
        products = products.exclude(id__in=selected_product_ids)
        
        return ProductSerializer(products, many=True).data
    
    def get_remaining_slots(self, obj):
        selected_count = obj.campaign_products.count()
        return max(0, obj.campaign.max_products_per_vendor - selected_count)
    
    def get_meets_minimum_requirements(self, obj):
        meets, message = obj.meets_minimum_requirements
        return {'meets': meets, 'message': message}


class SuperAdminCampaignParticipationDetailSerializer(serializers.ModelSerializer):
    campaign_details = CampaignSerializer(source='campaign', read_only=True)
    vendor_details = VendorSerializer(source='vendor', read_only=True)
    campaign_products = CampaignProductSerializer(many=True, read_only=True)
    total_products = serializers.IntegerField(source='campaign_products.count', read_only=True)
    meets_minimum_requirements = serializers.SerializerMethodField()
    
    class Meta:
        model = CampaignParticipation
        fields = [
            'id', 'campaign', 'campaign_details', 'vendor', 'vendor_details',
            'status', 'applied_at', 'approved_at', 'approved_by', 'rejection_reason',
            'campaign_products', 'total_products', 'meets_minimum_requirements'
        ]
    
    def get_meets_minimum_requirements(self, obj):
        meets, message = obj.meets_minimum_requirements
        return {'meets': meets, 'message': message}
    
    

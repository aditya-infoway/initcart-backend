#ecommerce/serializers/public_serializers.py
from datetime import timezone
from rest_framework import serializers
from django.db.models import Q, F  
from ecommerce.models.coupon import Coupon, CouponUsage
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from ecommerce.models.product import Product, ProductStock, ProductGallery
from ecommerce.models.vendor import Vendor , Brand
from ecommerce.serializers.category_serializers import (
    CategorySerializer as BaseCategorySerializer,
    SubCategorySerializer as BaseSubCategorySerializer, 
    SubSubCategorySerializer as BaseSubSubCategorySerializer

)
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from ecommerce.utils.campaign_utils import get_campaign_price_for_product

class PublicCategorySerializer(BaseCategorySerializer):
    """Extends existing CategorySerializer with product_count and web_home fields"""
    product_count = serializers.SerializerMethodField()
    
    class Meta(BaseCategorySerializer.Meta):
        # Add web_home and platform_charge to public fields
        fields = BaseCategorySerializer.Meta.fields + [
            "product_count", 
            "web_home", 
            "platform_charge"
        ]
    
    def get_product_count(self, obj):
        """Count approved products in this category"""
        try:
            return Product.objects.filter(category=obj, status="approved").count()
        except:
            return 0

class PublicProductStockSerializer(serializers.ModelSerializer):
    variant_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductStock
        fields = [
            "id", "mrp", "selling_price", "final_price", "tax",
            "stock_quantity", "color", "size", "unit", "weight",
            "maximum_order_quantity",
            "variant_image",
            "variant_image_url",
        ]

    def get_variant_image_url(self, obj):
        request = self.context.get("request")
        if obj.variant_image and request:
            return request.build_absolute_uri(obj.variant_image.url)
        return None

class PublicProductGallerySerializer(serializers.ModelSerializer):
    """Simplified gallery serializer for public API"""
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductGallery
        fields = ["id", "image_url"]
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

class PublicBrandSerializer(serializers.ModelSerializer):
    """Public API के लिए Brand Serializer"""
    brand_logo_url = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Brand
        fields = [
            'id', 
            'brand_name', 
            'description', 
            'brand_logo', 
            'brand_logo_url',
            'status', 
            'product_count'
        ]
    
    def get_brand_logo_url(self, obj):
        request = self.context.get('request')
        if obj.brand_logo and request:
            return request.build_absolute_uri(obj.brand_logo.url)
        return None
    
    def get_product_count(self, obj):
        """Count approved products for this brand"""
        try:
            return Product.objects.filter(brand=obj, status="approved").count()
        except:
            return 0

class PublicVendorSimpleSerializer(serializers.ModelSerializer):
    """Simplified vendor serializer for public API"""
    class Meta:
        model = Vendor
        fields = ['id', 'business_name']

class PublicCategorySimpleSerializer(serializers.ModelSerializer):
    """Simplified category serializer for public API"""
    class Meta:
        model = Category
        fields = ['id', 'name']

class PublicSubCategorySimpleSerializer(serializers.ModelSerializer):
    """Simplified subcategory serializer for public API"""
    class Meta:
        model = SubCategory
        fields = ['id', 'name']

class PublicSubSubCategorySimpleSerializer(serializers.ModelSerializer):
    """Simplified subsubcategory serializer for public API"""
    class Meta:
        model = SubSubCategory
        fields = ['id', 'name']

class PublicSubCategorySerializer(BaseSubCategorySerializer):
    """Extends existing SubCategorySerializer with product_count"""
    product_count = serializers.SerializerMethodField()
    
    class Meta(BaseSubCategorySerializer.Meta):
        fields = BaseSubCategorySerializer.Meta.fields + ["product_count"]
    
    def get_product_count(self, obj):
        """Count approved products in this subcategory"""
        try:
            return Product.objects.filter(subcategory=obj, status="approved").count()
        except:
            return 0


class PublicSubSubCategorySerializer(BaseSubSubCategorySerializer):
    """Extends existing SubSubCategorySerializer with product_count"""
    product_count = serializers.SerializerMethodField()
    
    class Meta(BaseSubSubCategorySerializer.Meta):
        fields = BaseSubSubCategorySerializer.Meta.fields + ["product_count"]
    
    def get_product_count(self, obj):
        """Count approved products in this subsubcategory"""
        try:
            return Product.objects.filter(subsubcategory=obj, status="approved").count()
        except:
            return 0
        

#public serializer for product vendors  
class PublicVendorSerializer(serializers.ModelSerializer):
    store_logo_url = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Vendor
        fields = [
            'id', 'business_name', 'owner_name', 'email', 'phone',
            'vendor_type', 'vendor_subtype', 'store_logo', 'store_logo_url',
            'city', 'state', 'status', 'is_approved', 'product_count',
            'created_at'
        ]
    
    def get_store_logo_url(self, obj):
        request = self.context.get('request')
        if obj.store_logo and request:
            return request.build_absolute_uri(obj.store_logo.url)
        return None
    
    def get_product_count(self, obj):
        from ecommerce.models.product import Product
        return Product.objects.filter(vendor=obj, status="approved").count()   
    
class PublicProductSerializer(serializers.ModelSerializer):
    """Public APIProduct Serializer with all necessary fields"""
    gallery = PublicProductGallerySerializer(many=True, read_only=True)
    stocks = PublicProductStockSerializer(many=True, read_only=True)
    
        # Add campaign fields
    campaign_price = serializers.SerializerMethodField()
    is_in_campaign = serializers.SerializerMethodField()
    campaign_details = serializers.SerializerMethodField()
    # Related field details
    vendor_details = PublicVendorSimpleSerializer(source='vendor', read_only=True)
    brand_details = PublicBrandSerializer(source='brand', read_only=True)
    category_details = PublicCategorySimpleSerializer(source='category', read_only=True, allow_null=True)
    subcategory_details = PublicSubCategorySimpleSerializer(source='subcategory', read_only=True , allow_null = True)
    subsubcategory_details = PublicSubSubCategorySimpleSerializer(source='subsubcategory', read_only=True, allow_null=True)
    warranty_available = serializers.BooleanField(read_only=True)
    
    # Image URLs
    main_image_url = serializers.SerializerMethodField()
    thumbnail_image_url = serializers.SerializerMethodField()
    
    # Calculated fields
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            "id", 
            "vendor", "vendor_details",
            "brand", "brand_details", 
            "product_name", "sku", 
            "category", "category_details",
            "subcategory", "subcategory_details",
            "subsubcategory", "subsubcategory_details",
            "product_type", "short_description",
            "keywords", "full_description", "product_video_url",
            "main_image", "main_image_url",
            "thumbnail_image", "thumbnail_image_url",
            "product_condition", "manufacturing_date", "expiry_date",
            "return_policy", "estimated_delivery_time", "free_shipping",
            "status", "created_at", "updated_at",
            "gallery", "stocks",
            "min_price", "max_price", "in_stock", "discount_percentage",
            "campaign_price",
            "is_in_campaign",
            "campaign_details",
            "warranty_period",
            "warranty_available",
            "warranty_description",
            "warranty_type","description_features",
            "specifications",
            
            
            
        ]
    def get_campaign_price(self, obj):
        campaign_data = get_campaign_price_for_product(obj, self.context.get('request'))
        if campaign_data:
            return campaign_data['campaign_price']
        return None
    
    def get_is_in_campaign(self, obj):
        campaign_data = get_campaign_price_for_product(obj)
        return campaign_data is not None
    
    def get_campaign_details(self, obj):
        campaign_data = get_campaign_price_for_product(obj, self.context.get('request'))
        if campaign_data:
            return {
                'campaign_id': campaign_data['campaign_id'],
                'campaign_name': campaign_data['campaign_name'],
                'campaign_type': campaign_data['campaign_type'],
                'discount_percentage': campaign_data['discount_percentage'],
                'original_price': campaign_data['original_price'],
                'final_price': campaign_data['campaign_price'],
                'deal_of_day_placement': campaign_data.get('deal_of_day_placement'),
                'end_datetime': campaign_data.get('end_datetime'),
                'campaign_product_id': campaign_data.get('campaign_product_id')
            }
        return None
    def get_main_image_url(self, obj):
        request = self.context.get('request')
        if obj.main_image and request:
            return request.build_absolute_uri(obj.main_image.url)
        return None
    
    def get_thumbnail_image_url(self, obj):
        request = self.context.get('request')
        if obj.thumbnail_image and request:
            return request.build_absolute_uri(obj.thumbnail_image.url)
        return None
    
    def get_min_price(self, obj):
        """Override to show campaign price if available"""
        campaign_data = get_campaign_price_for_product(obj)
        if campaign_data:
            return campaign_data['campaign_price']
        
        if obj.stocks.exists():
            prices = [stock.final_price for stock in obj.stocks.all() if stock.final_price]
            return min(prices) if prices else 0
        return 0
    
    def get_max_price(self, obj):
        """Get maximum price from all stocks"""
        if obj.stocks.exists():
            prices = [stock.final_price for stock in obj.stocks.all() if stock.final_price]
            return max(prices) if prices else 0
        return 0
    
    def get_in_stock(self, obj):
        """Check if any stock is available"""
        if obj.stocks.exists():
            return any(stock.stock_quantity > 0 for stock in obj.stocks.all())
        return False

    
    def get_discount_percentage(self, obj):
        """Override to show campaign discount if available"""
        campaign_data = get_campaign_price_for_product(obj)
        if campaign_data and campaign_data['discount_percentage']:
            return campaign_data['discount_percentage']
        
        # Original discount calculation
        if obj.stocks.exists():
            stock = obj.stocks.first()
            if stock.mrp and stock.selling_price and stock.mrp > 0:
                discount = ((float(stock.mrp) - float(stock.selling_price)) / float(stock.mrp)) * 100
                return round(discount, 2)
        return 0
    
    
class PublicCouponSerializer(serializers.ModelSerializer):
    """Serializer for public coupon display"""
    discount_display = serializers.SerializerMethodField()
    validity_display = serializers.SerializerMethodField()
    conditions = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    
    vendor = serializers.IntegerField(source='vendor.id', read_only=True)
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    
    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'title', 'coupon_type', 'discount_display',
            'min_order_value', 'max_discount', 'display_message',
            'validity_display', 'conditions', 'apply_on', 'is_valid',
            'start_date', 'expire_date', 'vendor', 'vendor_name'
        ]
    
    def get_discount_display(self, obj):
        return obj.get_discount_display()
    
    def get_validity_display(self, obj):
        if obj.expire_date:
            return f"Valid till {obj.expire_date.strftime('%d %b %Y')}"
        return "No expiry"
    
    def get_conditions(self, obj):
        conditions = []
        
        if obj.min_order_value > 0:
            conditions.append(f"Min. order: ₹{obj.min_order_value}")
        
        if obj.apply_on != 'all_products':
            if obj.apply_on == 'category':
                if obj.categories.exists():
                    category_names = [c.name for c in obj.categories.all()[:2]]
                    conditions.append(f"On {', '.join(category_names)} categories")
            elif obj.apply_on == 'product':
                if obj.products.exists():
                    product_names = [p.product_name for p in obj.products.all()[:2]]
                    conditions.append(f"On {', '.join(product_names)}")
        
        if obj.max_count:
            remaining = obj.max_count - obj.used_count
            if remaining > 0:
                conditions.append(f"{remaining} uses left")
        
        return conditions
    
    def get_is_valid(self, obj):
        return obj.is_valid()


class ApplyCouponSerializer(serializers.Serializer):
    """Serializer for applying coupon"""
    coupon_code = serializers.CharField(max_length=50, required=True)
    
    def validate_coupon_code(self, value):
        """Validate coupon code"""
        try:
            coupon = Coupon.objects.get(code=value.upper())
        except Coupon.DoesNotExist:
            raise serializers.ValidationError("Invalid coupon code.")
        
        if not coupon.is_valid():
            raise serializers.ValidationError("This coupon is not valid or has expired.")
        
        return coupon


class CartItemCouponSerializer(serializers.Serializer):
    """Serializer for cart items with coupon applicability"""
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    quantity = serializers.IntegerField()
    is_applicable = serializers.BooleanField()
    applicable_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class CouponValidationResponseSerializer(serializers.Serializer):
    """Serializer for coupon validation response"""
    valid = serializers.BooleanField()
    message = serializers.CharField()
    coupon = PublicCouponSerializer(required=False)
    applicable_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)


class ProductCouponSerializer(serializers.ModelSerializer):
    """Serializer for product with applicable coupons"""
    applicable_coupons = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = ['id', 'product_name', 'price', 'main_image', 'applicable_coupons']
    
    def get_applicable_coupons(self, obj):
        # Get all active coupons that can be applied to this product
        now = timezone.now()
        coupons = Coupon.objects.filter(
            status='active',
            start_date__lte=now,
            expire_date__gte=now
        ).filter(
            Q(max_count__isnull=True) | Q(used_count__lt=F('max_count'))
        )
        
        applicable_coupons = []
        for coupon in coupons:
            if coupon.can_be_applied_to_product(obj):
                applicable_coupons.append(coupon)
        
        return PublicCouponSerializer(applicable_coupons, many=True).data   
    
    
     

    
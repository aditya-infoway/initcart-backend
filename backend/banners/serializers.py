# serializers.py
from rest_framework import serializers
from .models import MobileBanner, MobileCategoryCard, MobileDealCard, SliderImage
from .models import BigAd, SmallAd
from .models import SuperAdminProfile

class SliderImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SliderImage
        fields = ["id", "image", "created_at"]
        
        def get_image(self, obj):
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url


class BigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = BigAd
        fields = "__all__"


class SmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = SmallAd
        fields = "__all__"
        
class SuperAdminProfileSerializer(serializers.ModelSerializer):
    profile_image = serializers.SerializerMethodField()
    brochure_pdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = SuperAdminProfile
        fields = [
            "name", "email", "phone", "address", 
            "profile_image", "brochure_pdf", "brochure_pdf_url",
            "youtube", "instagram", "twitter", "facebook", "whatsapp"
        ]
        extra_kwargs = {
            'brochure_pdf': {'required': False}
        }
    
    def get_profile_image(self, obj):
        if obj.profile_image:
            request = self.context.get("request")
            if request:  # ✅ Safety check
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url  # Fallback to relative URL
        return ""
    
    def get_brochure_pdf_url(self, obj):
        if obj.brochure_pdf:
            request = self.context.get("request")
            if request:  # ✅ Safety check
                return request.build_absolute_uri(obj.brochure_pdf.url)
            return obj.brochure_pdf.url  # Fallback to relative URL
        return ""


class initAdminFooterSerializer(serializers.ModelSerializer):
    brochure_pdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = SuperAdminProfile
        fields = [
            "phone", "email", "address",
            "youtube", "instagram", "twitter", "facebook", "whatsapp",
            "brochure_pdf_url"
        ]
    
    def get_profile_image(self, obj):
        if obj.profile_image:
            request = self.context.get("request")
            if request:  # ✅ Safety check
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return ""
    
    def get_brochure_pdf_url(self, obj):
        if obj.brochure_pdf:
            request = self.context.get("request")
            if request:  # ✅ Safety check
                return request.build_absolute_uri(obj.brochure_pdf.url)
            return obj.brochure_pdf.url
        return ""
        


# serializers.py

# serializers.py

class MobileBannerSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    
    class Meta:
        model = MobileBanner
        fields = ['id', 'image', 'title', 'subtitle', 'button_text', 'button_url', 'order', 'is_active', 'created_at', 'updated_at']
    
    def get_image(self, obj):
        if obj.image and obj.image.name:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    
    def create(self, validated_data):
        return MobileBanner.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        instance.title = validated_data.get('title', instance.title)
        instance.subtitle = validated_data.get('subtitle', instance.subtitle)
        instance.button_text = validated_data.get('button_text', instance.button_text)
        instance.button_url = validated_data.get('button_url', instance.button_url)
        instance.order = validated_data.get('order', instance.order)
        instance.is_active = validated_data.get('is_active', instance.is_active)
        if validated_data.get('image'):
            instance.image = validated_data.get('image')
        instance.save()
        return instance

class MobileCategoryCardSerializer(serializers.ModelSerializer):
    subcategory_name = serializers.CharField(source='subcategory.name', read_only=True)
    subcategory_id = serializers.IntegerField(source='subcategory.id', read_only=True)
    icon_url = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()
    
    class Meta:
        model = MobileCategoryCard
        fields = ['id', 'subcategory', 'subcategory_name', 'subcategory_id', 'icon_url', 
                  'product_count', 'products', 'gradient_start', 'gradient_end', 
                  'accent_color', 'header_color', 'order']
    
    def get_icon_url(self, obj):
        if obj.subcategory.icon:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.subcategory.icon.url)
        return None
    
    def get_product_count(self, obj):
        return obj.subcategory.products.filter(is_active=True).count()
    
    def get_products(self, obj):
        products = obj.subcategory.products.filter(is_active=True)[:4]
        from ecommerce.serializers import ProductListSerializer
        return ProductListSerializer(products, many=True, context=self.context).data


class MobileDealCardSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    original_price = serializers.DecimalField(source='product.original_price', max_digits=10, decimal_places=2, read_only=True)
    product_image = serializers.SerializerMethodField()
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    
    class Meta:
        model = MobileDealCard
        fields = ['id', 'deal_type', 'product', 'product_id', 'product_name', 'product_price',
                  'original_price', 'product_image', 'discount_percentage', 'gradient_start',
                  'gradient_end', 'accent_color', 'header_color', 'order']
    
    def get_product_image(self, obj):
        if obj.product.main_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.product.main_image.url)
        return None        
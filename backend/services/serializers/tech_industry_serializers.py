from rest_framework import serializers
from services.models.tech_industry import TechIndustryService, TechIndustryItem, TechIndustryImage
from services.models.subcategory import ServiceSubcategory

class TechIndustryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechIndustryItem
        fields = ['id', 'name', 'description', 'price']

class TechIndustryImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = TechIndustryImage
        fields = ['id', 'image']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None

class TechIndustryServiceSerializer(serializers.ModelSerializer):
    subcategory_name = serializers.SerializerMethodField()
    subcategory = serializers.PrimaryKeyRelatedField(
        queryset=ServiceSubcategory.objects.all(),
        required=False,
        allow_null=True
    )
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    vendor = serializers.PrimaryKeyRelatedField(read_only=True)
    category = serializers.SerializerMethodField()
    items = TechIndustryItemSerializer(many=True, required=False)
    multi_images = TechIndustryImageSerializer(many=True, required=False)
    main_image = serializers.SerializerMethodField()
    second_image = serializers.SerializerMethodField()
    approved_date = serializers.DateTimeField(read_only=True)

    class Meta:
        model = TechIndustryService
        fields = [
            'id','category', 'subcategory', 'subcategory_name', 'business_name','address', 'location','country','state',
            'city','open_time', 'close_time', 'contact_no', 'whatsapp_no', 'description', 
            'main_image', 'second_image', 'multi_images', 'status', 'items','approved_by','vendor','approved_date',
        ]

    def get_subcategory_name(self, obj):
        return obj.subcategory.subcategory_name if obj.subcategory else None

    def get_main_image(self, obj):
        request = self.context.get('request')
        if obj.main_image and request:
            return request.build_absolute_uri(obj.main_image.url)
        elif obj.main_image:
            return obj.main_image.url
        return None

    def get_second_image(self, obj):
        request = self.context.get('request')
        if obj.second_image and request:
            return request.build_absolute_uri(obj.second_image.url)
        elif obj.second_image:
            return obj.second_image.url
        return None
    
    def get_category(self, obj):
        if obj.vendor and obj.vendor.vendor_subtype:
            return obj.vendor.vendor_subtype
        return None
    
    
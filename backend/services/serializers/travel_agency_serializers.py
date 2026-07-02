from rest_framework import serializers
from services.models.travel_agency import TravelAgencyService, TravelAgencyItem, TravelAgencyImage

# from services.models.gym import Country, State, City
from services.models.subcategory import ServiceSubcategory
class TravelAgencyItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelAgencyItem
        fields = ['id', 'name', 'description', 'price']

class TravelAgencyImageSerializer(serializers.ModelSerializer):
    # Return full URL
    image = serializers.SerializerMethodField()

    class Meta:
        model = TravelAgencyImage
        fields = ['id', 'image']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None

class TravelAgencyServiceSerializer(serializers.ModelSerializer):
    subcategory_name = serializers.SerializerMethodField()
    subcategory = serializers.PrimaryKeyRelatedField(
        queryset=ServiceSubcategory.objects.all(),
        required=False,
        allow_null=True
    )
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    vendor = serializers.PrimaryKeyRelatedField(read_only=True)
    category = serializers.SerializerMethodField()
    items = TravelAgencyItemSerializer(many=True, required=False)
    multi_images = TravelAgencyImageSerializer(many=True, required=False)
    main_image = serializers.SerializerMethodField()
    second_image = serializers.SerializerMethodField()
    approved_date = serializers.DateTimeField(read_only=True)

    class Meta:
        model = TravelAgencyService
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
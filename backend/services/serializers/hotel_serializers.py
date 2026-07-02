from rest_framework import serializers
from services.models.hotel import HotelService, HotelServiceImage, HotelRoomType
from services.models.subcategory import ServiceSubcategory


class HotelServiceImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = HotelServiceImage
        fields = ['id', 'image']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None


class HotelRoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = HotelRoomType
        fields = ['id', 'room_type', 'person', 'rate']


class HotelServiceSerializer(serializers.ModelSerializer):
    """
    Complete Hotel Service Serializer
    """
    subcategory_name = serializers.SerializerMethodField()
    subcategory = serializers.PrimaryKeyRelatedField(
        queryset=ServiceSubcategory.objects.all(),
        required=False,
        allow_null=True
    )
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    vendor = serializers.PrimaryKeyRelatedField(read_only=True)
    category = serializers.SerializerMethodField()
    multi_images = HotelServiceImageSerializer(many=True, required=False, read_only=True)
    room_types = HotelRoomTypeSerializer(many=True, required=False, read_only=True)
    main_image = serializers.SerializerMethodField()
    approved_date = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = HotelService
        fields = [
            'id', 'category', 'subcategory', 'subcategory_name',
            'hotel_name', 'address', 'location', 
            'country', 'state', 'city',
            'contact_no', 'whatsapp_no', 'gmail_id',
            'hotel_rating', 'description', 'room_category',
            'main_image', 'multi_images', 'room_types',
            'status', 'is_active', 'approved_by', 'vendor', 
            'approved_date', 'created_at', 'updated_at'
        ]
        read_only_fields = ['status', 'approved_date', 'approved_by', 'vendor', 'created_at', 'updated_at']

    def get_subcategory_name(self, obj):
        return obj.subcategory.subcategory_name if obj.subcategory else None

    def get_main_image(self, obj):
        request = self.context.get('request')
        if obj.main_image and request:
            return request.build_absolute_uri(obj.main_image.url)
        elif obj.main_image:
            return obj.main_image.url
        return None

    def get_category(self, obj):
        if obj.vendor and obj.vendor.vendor_subtype:
            return obj.vendor.vendor_subtype
        return None


class HotelServiceListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views
    """
    subcategory_name = serializers.SerializerMethodField()
    main_image = serializers.SerializerMethodField()
    city = serializers.CharField()
    contact_no = serializers.CharField()
    hotel_rating = serializers.DecimalField(max_digits=3, decimal_places=1)

    class Meta:
        model = HotelService
        fields = [
            'id', 'hotel_name', 'subcategory_name', 
            'main_image', 'city', 'contact_no', 'status',
            'created_at', 'hotel_rating'
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
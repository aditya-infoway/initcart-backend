from rest_framework import serializers
from services.models.restaurant import RestaurantService, RestaurantServiceImage
from services.models.subcategory import ServiceSubcategory


class RestaurantServiceImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantServiceImage
        fields = ['id', 'image']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None


class RestaurantServiceSerializer(serializers.ModelSerializer):
    """
    Complete Restaurant Service Serializer
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
    multi_images = RestaurantServiceImageSerializer(many=True, required=False, read_only=True)
    main_image = serializers.SerializerMethodField()
    approved_date = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = RestaurantService
        fields = [
            'id', 'category', 'subcategory', 'subcategory_name',
            'restaurant_name', 'address', 'location', 
            'country', 'state', 'city',
            'contact_no', 'whatsapp_no', 'gmail_id',
            'restaurant_rating', 'description', 'tax_description',
            'main_image', 'multi_images',
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

    def create(self, validated_data):
        # Handle multi_images if passed in request
        request = self.context.get('request')
        if request and request.FILES.getlist('multi_images'):
            # Multi images will be handled in view
            pass
        return super().create(validated_data)


class RestaurantServiceListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views
    """
    subcategory_name = serializers.SerializerMethodField()
    main_image = serializers.SerializerMethodField()
    city = serializers.CharField()
    contact_no = serializers.CharField()

    class Meta:
        model = RestaurantService
        fields = [
            'id', 'restaurant_name', 'subcategory_name', 
            'main_image', 'city', 'contact_no', 'status',
            'created_at', 'restaurant_rating'
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
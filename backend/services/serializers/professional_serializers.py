# services/serializers/professional_serializers.py

from rest_framework import serializers
from services.models.professional import ProfessionalService, ProfessionalServiceImage
from services.models.subcategory import ServiceSubcategory


class ProfessionalServiceImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProfessionalServiceImage
        fields = ['id', 'image']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None


class ProfessionalServiceSerializer(serializers.ModelSerializer):
    subcategory_name = serializers.SerializerMethodField()
    subcategory = serializers.PrimaryKeyRelatedField(
        queryset=ServiceSubcategory.objects.all(),
        required=False,
        allow_null=True
    )
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    vendor = serializers.PrimaryKeyRelatedField(read_only=True)
    category = serializers.SerializerMethodField()
    multi_images = ProfessionalServiceImageSerializer(many=True, required=False)
    main_image = serializers.SerializerMethodField()
    approved_date = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ProfessionalService
        fields = [
            'id', 'category', 'subcategory', 'subcategory_name',
            'business_name', 'address', 'location', 'country', 'state', 'city',  # Added country, state, city
            'contact_no', 'whatsapp_no', 'gmail_id',
            'description', 'main_image', 'multi_images',
            'status', 'approved_by', 'vendor', 'approved_date',
            'created_at',
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

    def get_category(self, obj):
        if obj.vendor and obj.vendor.vendor_subtype:
            return obj.vendor.vendor_subtype
        return None
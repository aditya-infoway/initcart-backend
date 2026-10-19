from rest_framework import serializers
from ecommerce.models.top_seller import TopSellerRequest
from ecommerce.utils.top_seller_helpers import (
    validate_banner_file, process_banner, get_banner_url,
)


def get_vendor_logo(vendor, request=None):
    """Handles both store_logo_url (property) and store_logo (ImageField)."""
    url = getattr(vendor, 'store_logo_url', None)
    if url:
        return url
    logo = getattr(vendor, 'store_logo', None)
    if logo:
        try:
            return request.build_absolute_uri(logo.url) if request else logo.url
        except Exception:
            return None
    return None


def _first_attr(obj, names):
    for n in names:
        val = getattr(obj, n, None)
        if val:
            return val
    return None


class TopSellerRequestSerializer(serializers.ModelSerializer):
    vendor_id = serializers.IntegerField(source='vendor.id', read_only=True)
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    vendor_city = serializers.SerializerMethodField()
    vendor_state = serializers.SerializerMethodField()
    vendor_email = serializers.SerializerMethodField()
    vendor_phone = serializers.SerializerMethodField()
    vendor_logo = serializers.SerializerMethodField()
    vendor_joined = serializers.SerializerMethodField()
    total_requests = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()

    class Meta:
        model = TopSellerRequest
        fields = [
            'id', 'request_id', 'vendor_id', 'vendor_name', 'vendor_email', 'vendor_phone',
            'vendor_city', 'vendor_state', 'vendor_logo', 'vendor_joined',
            'message', 'banner_url', 'banner_uploaded_by',
            'status', 'is_active', 'display_order', 'admin_remarks',
            'total_requests', 'created_at', 'approved_at', 'rejected_at',
        ]

    def get_vendor_city(self, obj):
        return getattr(obj.vendor, 'city', '') or ''

    def get_vendor_state(self, obj):
        return getattr(obj.vendor, 'state', '') or ''

    def get_vendor_email(self, obj):
        user = getattr(obj.vendor, 'user', None)
        return getattr(user, 'email', '') or _first_attr(obj.vendor, ['email', 'business_email']) or ''

    def get_vendor_phone(self, obj):
        return _first_attr(obj.vendor, ['phone', 'mobile', 'phone_number', 'contact_number']) or ''

    def get_vendor_logo(self, obj):
        return get_vendor_logo(obj.vendor, self.context.get('request'))

    def get_vendor_joined(self, obj):
        joined = getattr(obj.vendor, 'created_at', None)
        if not joined:
            user = getattr(obj.vendor, 'user', None)
            joined = getattr(user, 'date_joined', None)
        return joined

    def get_total_requests(self, obj):
        return TopSellerRequest.objects.filter(vendor=obj.vendor).count()

    def get_banner_url(self, obj):
        return get_banner_url(obj, self.context.get('request'))


class CreateTopSellerRequestSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    # Remove required=True (use required=False) if you want the banner to be optional for vendors
    banner = serializers.ImageField(
        required=True,
        error_messages={
            'required': 'Please upload a banner image',
            'empty': 'The uploaded banner file is empty',
            'invalid_image': 'Please upload a valid image file',
        },
    )

    def validate_banner(self, value):
        return validate_banner_file(value)

    def validate(self, data):
        vendor = self.context['vendor']

        if not getattr(vendor, 'is_approved', False):
            raise serializers.ValidationError("Your store must be approved before requesting Top Seller status")

        existing = TopSellerRequest.objects.filter(vendor=vendor, status__in=['pending', 'approved'])
        if existing.filter(status='pending').exists():
            raise serializers.ValidationError("You already have a pending Top Seller request")
        if existing.filter(status='approved').exists():
            raise serializers.ValidationError("Your store is already approved as a Top Seller")
        return data

    def create(self, validated_data):
        obj = TopSellerRequest(
            vendor=self.context['vendor'],
            message=validated_data.get('message', ''),
        )
        banner = validated_data.get('banner')
        if banner:
            obj.banner = process_banner(banner)
            obj.banner_uploaded_by = 'vendor'
        obj.save()
        return obj


class BannerUploadSerializer(serializers.Serializer):
    banner = serializers.ImageField(
        required=True,
        error_messages={
            'required': 'Please choose a banner image',
            'invalid_image': 'Please upload a valid image file',
        },
    )

    def validate_banner(self, value):
        return validate_banner_file(value)


class ApproveTopSellerSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, default=True)
    display_order = serializers.IntegerField(required=False, min_value=0)

    def validate(self, data):
        if self.context['top_seller'].status != 'pending':
            raise serializers.ValidationError("Only pending requests can be approved")
        return data


class RejectTopSellerSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=True, allow_blank=False)

    def validate(self, data):
        if self.context['top_seller'].status != 'pending':
            raise serializers.ValidationError("Only pending requests can be rejected")
        return data
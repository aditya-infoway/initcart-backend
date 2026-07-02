#services/serializers/inquiry_serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from services.models.inquiry import (
    ServiceInquiry, InquiryAttachment, InquiryNote, 
    ServiceCategory, InquiryType, InquiryStatus
)
from ecommerce.serializers.vendor_serializers import VendorListSerializer
from ecommerce.models.vendor import Vendor

User = get_user_model()

class InquiryAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = InquiryAttachment
        fields = ['id', 'file', 'file_url', 'file_name', 'file_type', 'file_size', 'uploaded_at']
        read_only_fields = ['file_name', 'file_type', 'file_size', 'uploaded_at']
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

class InquiryNoteSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = InquiryNote
        fields = ['id', 'user', 'user_name', 'user_email', 'note', 'is_internal', 'created_at']
        read_only_fields = ['created_at']
    
    def validate(self, data):
        request = self.context.get('request')
        if request and not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        return data

class ServiceInquiryCreateSerializer(serializers.ModelSerializer):
    attachments = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        default=list
    )
    
    class Meta:
        model = ServiceInquiry
        fields = [
            'service_category', 'vendor', 'service_id', 'service_name', 'service_url',
            'customer_name', 'customer_email', 'customer_phone', 'customer_address',
            'customer_city', 'customer_state', 'inquiry_type', 'subject', 'message',
            'preferred_date', 'preferred_time', 'budget', 'quantity', 'custom_fields',
            'attachments', 'source'
        ]
    
    def validate(self, data):
        # Validate vendor exists and is a service vendor
        vendor = data.get('vendor')
        if vendor:
            if vendor.vendor_type != 'service':
                raise serializers.ValidationError({"vendor": "Only service vendors can receive inquiries"})
            if not vendor.is_approved or vendor.status != 'active':
                raise serializers.ValidationError({"vendor": "Vendor is not active or approved"})
        
        # Validate service category
        if data.get('service_category') not in dict(ServiceCategory.choices):
            raise serializers.ValidationError({"service_category": "Invalid service category"})
        
        return data
    
    def create(self, validated_data):
        attachments = validated_data.pop('attachments', [])
        request = self.context.get('request')
        
        # Get IP address and user agent if available
        if request:
            validated_data['ip_address'] = request.META.get('REMOTE_ADDR')
            validated_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
        
        # Create inquiry
        inquiry = ServiceInquiry.objects.create(**validated_data)
        
        # Save attachments
        for attachment in attachments:
            InquiryAttachment.objects.create(
                inquiry=inquiry,
                file=attachment,
                file_name=attachment.name,
                file_type=attachment.content_type,
                file_size=attachment.size
            )
        
        return inquiry

class ServiceInquiryListSerializer(serializers.ModelSerializer):
    vendor_details = VendorListSerializer(source='vendor', read_only=True)
    service_category_display = serializers.CharField(source='get_service_category_display', read_only=True)
    inquiry_type_display = serializers.CharField(source='get_inquiry_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    attachments_count = serializers.SerializerMethodField()
    has_attachments = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceInquiry
        fields = [
            'id', 'inquiry_id', 'service_category', 'service_category_display',
            'vendor', 'vendor_details', 'service_id', 'service_name',
            'customer_name', 'customer_email', 'customer_phone',
            'inquiry_type', 'inquiry_type_display', 'subject','message',
            'status', 'status_display', 'priority', 'is_read', 'is_archived',
            'created_at', 'updated_at', 'attachments_count', 'has_attachments',
            'assigned_to', 'response_date'
        ]
    
    def get_attachments_count(self, obj):
        return obj.attachments.count()
    
    def get_has_attachments(self, obj):
        return obj.attachments.exists()

class ServiceInquiryDetailSerializer(serializers.ModelSerializer):
    vendor_details = VendorListSerializer(source='vendor', read_only=True)
    attachments = InquiryAttachmentSerializer(many=True, read_only=True)
    internal_notes = InquiryNoteSerializer(many=True, read_only=True)
    service_category_display = serializers.CharField(source='get_service_category_display', read_only=True)
    inquiry_type_display = serializers.CharField(source='get_inquiry_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    
    class Meta:
        model = ServiceInquiry
        fields = [
            'id', 'inquiry_id', 'service_category', 'service_category_display',
            'vendor', 'vendor_details', 'service_id', 'service_name', 'service_url',
            'customer_name', 'customer_email', 'customer_phone',
            'customer_address', 'customer_city', 'customer_state',
            'inquiry_type', 'inquiry_type_display', 'subject', 'message',
            'preferred_date', 'preferred_time', 'budget', 'quantity', 'custom_fields',
            'status', 'status_display', 'priority', 'is_read', 'is_archived',
            'assigned_to', 'assigned_to_name', 'response_notes', 'response_date',
            'resolution_notes', 'attachments', 'internal_notes',
            'created_at', 'updated_at', 'ip_address', 'source'
        ]
        read_only_fields = ['inquiry_id', 'created_at', 'updated_at']

class ServiceInquiryUpdateSerializer(serializers.ModelSerializer):
    """Serializer for vendor/admin to update inquiry status"""
    
    class Meta:
        model = ServiceInquiry
        fields = [
            'status', 'priority', 'is_read', 'is_archived',
            'assigned_to', 'response_notes', 'resolution_notes'
        ]
    
    def validate(self, data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        
        # Only admin or vendor owner can update
        inquiry = self.instance
        user = request.user
        
        if not user.is_superuser:
            if hasattr(user, 'vendor') and user.vendor != inquiry.vendor:
                raise serializers.ValidationError("You can only update your own inquiries")
        
        return data

class VendorInquiryDashboardSerializer(serializers.Serializer):
    """Serializer for vendor inquiry dashboard"""
    total_inquiries = serializers.IntegerField()
    new_inquiries = serializers.IntegerField()
    in_progress_inquiries = serializers.IntegerField()
    responded_inquiries = serializers.IntegerField()
    resolved_inquiries = serializers.IntegerField()
    total_by_category = serializers.DictField()
    recent_inquiries = ServiceInquiryListSerializer(many=True)
    top_service_categories = serializers.ListField()

class InquiryStatsSerializer(serializers.Serializer):
    """Serializer for inquiry statistics"""
    total_inquiries = serializers.IntegerField()
    inquiries_by_status = serializers.DictField()
    inquiries_by_category = serializers.DictField()
    inquiries_by_month = serializers.ListField()
    average_response_time = serializers.FloatField(help_text="In hours")
    resolution_rate = serializers.FloatField(help_text="Percentage")

class PublicServiceInquirySerializer(serializers.ModelSerializer):
    """Serializer for public inquiry submission (without vendor details)"""
    
    class Meta:
        model = ServiceInquiry
        fields = [
            'service_category', 'service_id', 'service_name', 'service_url',
            'customer_name', 'customer_email', 'customer_phone', 'customer_address',
            'customer_city', 'customer_state', 'inquiry_type', 'subject', 'message',
            'preferred_date', 'preferred_time', 'budget', 'quantity', 'custom_fields'
        ]
    
    def create(self, validated_data):
        # This should be used with a view that sets the vendor automatically
        return super().create(validated_data)


class SuperAdminInquiryListSerializer(serializers.ModelSerializer):
    """Serializer for Super Admin inquiry listing"""
    sr_no = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    service_name = serializers.CharField(read_only=True)
    user_name = serializers.CharField(source='customer_name', read_only=True)
    number = serializers.CharField(source='customer_phone', read_only=True)
    city = serializers.CharField(source='customer_city', read_only=True)
    message = serializers.CharField(read_only=True)
    create_date = serializers.SerializerMethodField()
    create_time = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceInquiry
        fields = [
            'sr_no', 'inquiry_id', 'vendor_name', 'service_name',
            'user_name', 'number', 'city', 'message', 
            'create_date', 'create_time'
        ]
    
    def get_sr_no(self, obj):
        """Generate serial number based on index"""
        queryset = self.context.get('queryset')
        if queryset is not None:
            try:
                return list(queryset).index(obj) + 1
            except (ValueError, AttributeError):
                pass
        return None
    
    def get_create_date(self, obj):
        """Format date from created_at"""
        if obj.created_at:
            return obj.created_at.strftime('%Y-%m-%d')
        return None
    
    def get_create_time(self, obj):
        """Format time from created_at"""
        if obj.created_at:
            return obj.created_at.strftime('%H:%M:%S')
        return None 
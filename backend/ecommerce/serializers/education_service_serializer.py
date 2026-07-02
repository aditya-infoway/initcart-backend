from rest_framework import serializers
from ecommerce.models.education_service import EducationService
from ecommerce.serializers.vendor_serializers import VendorListSerializer
from django.utils import timezone

class EducationServiceSerializer(serializers.ModelSerializer):
    vendor_details = VendorListSerializer(source='vendor', read_only=True)
    image_url = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    can_be_edited = serializers.SerializerMethodField()
    can_be_submitted = serializers.SerializerMethodField()
    
    class Meta:
        model = EducationService
        fields = [
            'id', 'vendor', 'vendor_details',
            'service_name', 'short_description', 'full_description',
            'image', 'image_url',
            'price', 'offer_price', 'final_price', 'gst_percentage',
            'contact_person', 'contact_number', 'email',
            'address', 'city', 'state', 'pincode', 'landmark',
            'education_type', 'subjects_courses', 'mode_of_class',
            'class_duration', 'batch_timings', 'faculty_details',
            'facilities', 'eligibility_criteria',
            'video_url', 'terms_conditions',
            'status', 'is_active', 'is_featured',
            'submitted_for_approval_at', 'approved_at', 'approved_by',
            'rejection_reason', 'rejected_at',
            'views_count', 'created_at', 'updated_at',
            'can_be_edited', 'can_be_submitted',
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'views_count', 
            'approved_at', 'approved_by', 'rejected_at',
            'submitted_for_approval_at', 'status'
        ]
    
    def get_image_url(self, obj):
        if obj.image and hasattr(obj.image, 'url'):
            return obj.image.url
        return None
    
    def get_final_price(self, obj):
        return obj.final_price
    
    def get_can_be_edited(self, obj):
        return obj.can_be_edited_by_vendor
    
    def get_can_be_submitted(self, obj):
        return obj.can_be_submitted_for_approval
    
    def validate(self, data):
        vendor = data.get('vendor') or self.instance.vendor if self.instance else None
        
        if vendor and vendor.vendor_type != 'service':
            raise serializers.ValidationError({"vendor": "Only service vendors can add education services"})
        
        if vendor and vendor.vendor_subtype != 'education':
            raise serializers.ValidationError({"vendor": "Vendor must be of education type"})
        
        if data.get('offer_price') and data.get('price'):
            if data['offer_price'] >= data['price']:
                raise serializers.ValidationError({"offer_price": "Offer price must be less than regular price"})
        
        return data

class EducationServiceCreateSerializer(EducationServiceSerializer):
    class Meta(EducationServiceSerializer.Meta):
        fields = EducationServiceSerializer.Meta.fields

class EducationServiceUpdateSerializer(EducationServiceSerializer):
    class Meta(EducationServiceSerializer.Meta):
        read_only_fields = EducationServiceSerializer.Meta.read_only_fields + ['vendor']

class EducationServiceListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    
    class Meta:
        model = EducationService
        fields = [
            'id', 'service_name', 'short_description',
            'image_url', 'final_price', 'city', 'state',
            'education_type', 'mode_of_class', 'batch_timings',
            'status', 'is_active', 'is_featured',
            'vendor_name', 'created_at', 'submitted_for_approval_at',
            'approved_at'
        ]
    
    def get_image_url(self, obj):
        if obj.image and hasattr(obj.image, 'url'):
            return obj.image.url
        return None
    
    def get_final_price(self, obj):
        return obj.final_price

class EducationServiceSubmitSerializer(serializers.Serializer):
    """Serializer for submitting service for approval"""
    pass

class EducationServiceApproveSerializer(serializers.Serializer):
    """Serializer for approving service"""
    pass

class EducationServiceRejectSerializer(serializers.Serializer):
    """Serializer for rejecting service"""
    rejection_reason = serializers.CharField(required=True)

class EducationServiceStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating service status"""
    status = serializers.ChoiceField(choices=['active', 'inactive'])
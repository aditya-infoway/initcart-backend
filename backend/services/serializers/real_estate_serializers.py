# services/serializers/real_estate_serializers.py
import json
import logging
from rest_framework import serializers
from django.contrib.auth import get_user_model
from services.models.real_estate import Property, PropertyImage, PropertyEnquiry
from ecommerce.serializers.vendor_serializers import VendorListSerializer
from services.models.subcategory import ServiceSubcategory

logger = logging.getLogger(__name__)
User = get_user_model()

class PropertyImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PropertyImage
        fields = ['id', 'image', 'image_url', 'image_type', 'alt_text', 'display_order', 'created_at']
        read_only_fields = ['created_at']
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

class PropertyCreateSerializer(serializers.ModelSerializer):
    # File uploads
    main_image = serializers.FileField(write_only=True, required=True)
    thumbnail_image = serializers.FileField(write_only=True, required=True)
    additional_images = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
        default=list
    )
    document_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    property_type = serializers.PrimaryKeyRelatedField(
    queryset=ServiceSubcategory.objects.filter(
        parent_service='Real-Estate',
        status='Active'
    ),
    required=True
)
    
    # Add this new field for dynamic property types
    property_type_choices = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Property
        fields = [
            # Basic Information
            'title', 'description', 'transaction_type', 'property_type',
            
            # Address & Location
            'address', 'city', 'state', 'pincode',
            'latitude', 'longitude', 'google_map_url',
            
            # Specifications
            'total_area_size', 'carpet_area', 'built_up_area', 'bedrooms', 'bathrooms',
            'balconies', 'furnishing_status', 'floor_number', 'total_floors',
            'facing_direction', 'property_age', 'construction_status',
            
            # Legal & Ownership
            'ownership_type', 'encumbrance_certificate', 'rea_number', 'rera_number',
            'rera_registered', 'loan_availability', 'documents_available', 'negotiable',
            
            # Price Information
            'price', 'maintenance_charges', 'booking_amount', 'security_deposit',
            
            # Contact Information
            'contact_type', 'contact_name', 'contact_mobile', 'contact_whatsapp',
            'contact_email', 'contact_preferred_time', 'use_vendor_info',
            
            # SEO & Additional Info
            'short_description', 'seo_title', 'seo_description', 'seo_keywords',
            'virtual_tour_url', 'floor_plan', 'landmark',
            
            # Images & Documents
            'main_image', 'thumbnail_image', 'additional_images', 'document_file',
            
            # JSON Fields
            'amenities', 'nearby_facilities',
            
            # New field
            'property_type_choices',
            
            # Status (auto-set to pending)
            'status', 'subcategory',
        ]
    def get_property_type_choices(self, obj):
        """Get available property types from ServiceSubcategory"""
        from services.models.subcategory import ServiceSubcategory
        # Get real estate subcategories
        subcategories = ServiceSubcategory.objects.filter(
            parent_service='Real-Estate',
            status='Active'
        ).values('id', 'subcategory_name').distinct()
        
        # Convert to list of tuples (value, label) for dropdown
        choices = [(item['subcategory_name'].lower().replace(' ', '_'), item['subcategory_name']) 
                  for item in subcategories]
        
        # Add default choices if no subcategories found
        if not choices:
            choices = [
                ('apartment', 'Apartment'),
                ('house', 'House'),
                ('villa', 'Villa'),
                ('commercial', 'Commercial'),
                ('pg_coliving', 'PG/Co-living'),
                ('plots', 'Plots'),
            ]
        
        return choices
    # def validate_property_type(self, value):
    #     """Validate property type against available subcategories"""
    #     # Get available property types
    #     from services.models.subcategory import ServiceSubcategory
    #     subcategories = ServiceSubcategory.objects.filter(
    #         parent_service='Real-Estate',
    #         status='Active'
    #     ).values_list('subcategory_name', flat=True)
        
    #     # Convert to lowercase with underscores
    #     valid_types = [name.lower().replace(' ', '_') for name in subcategories]
        
    #     # Add default types if no subcategories
    #     if not valid_types:
    #         valid_types = ['apartment', 'house', 'villa', 'commercial', 'pg_coliving', 'plots']
        
    #     if value not in valid_types:
    #         raise serializers.ValidationError(
    #             f"Invalid property type. Available types: {', '.join(valid_types)}"
    #         )
        
    #     return value
    
    def validate_property_type(self, value):
        """
        Validate property_type using ServiceSubcategory ID
        """

        from services.models.subcategory import ServiceSubcategory

        # DRF instance hoy to
        if isinstance(value, ServiceSubcategory):
            subcategory_obj = value
        else:
            subcategory_obj = ServiceSubcategory.objects.filter(
                id=str(value),
                parent_service='Real-Estate',
                status='Active'
            ).first()

        if not subcategory_obj:
            raise serializers.ValidationError(
                "Invalid property type selected."
            )

        return subcategory_obj   # 🔥 OBJECT return karvanu
    
    def validate(self, data):
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        
        if not hasattr(request.user, 'vendor'):
            raise serializers.ValidationError("User must be a vendor")
        
        vendor = request.user.vendor
        
        # Check vendor type
        if vendor.vendor_type != 'service':
            raise serializers.ValidationError("Only service vendors can add properties")
        
        if vendor.vendor_subtype != 'real_estate':
            raise serializers.ValidationError("Only real estate vendors can add properties")
        
        # Validate price
        if data.get('price') and data['price'] <= 0:
            raise serializers.ValidationError({"price": "Price must be greater than zero"})

        # Auto-set status to pending for approval
        data['status'] = 'pending'
        
        # Add default values for required fields
        if 'built_up_area' not in data:
            data['built_up_area'] = data.get('carpet_area', 0)
        
        if 'security_deposit' not in data:
            data['security_deposit'] = 0
        
        if 'rera_registered' not in data:
            data['rera_registered'] = False
        
        if 'rera_number' not in data:
            data['rera_number'] = ''
        
        if 'construction_status' not in data:
            data['construction_status'] = 'ready_to_move'

        return data
    
    def create(self, validated_data):
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        
        if not hasattr(request.user, 'vendor'):
            raise serializers.ValidationError("User must be a vendor")
        
        vendor = request.user.vendor
        
        # Extract file data
        main_image = validated_data.pop('main_image', None)
        thumbnail_image = validated_data.pop('thumbnail_image', None)
        additional_images = validated_data.pop('additional_images', [])
        document_file = validated_data.pop('document_file', None)
        
        # Handle amenities and nearby_facilities
        amenities = validated_data.get('amenities', [])
        nearby_facilities = validated_data.get('nearby_facilities', {})
        
        # Convert if they are strings
        if isinstance(amenities, str):
            try:
                amenities = json.loads(amenities)
            except json.JSONDecodeError:
                amenities = []
        
        if isinstance(nearby_facilities, str):
            try:
                nearby_facilities = json.loads(nearby_facilities)
            except json.JSONDecodeError:
                nearby_facilities = {}
        
        validated_data['amenities'] = amenities
        validated_data['nearby_facilities'] = nearby_facilities
        
        # Create property
        try:
            property_obj = Property.objects.create(
                vendor=vendor,
                user=request.user,
                **validated_data
            )
        except Exception as e:
            logger.error(f"Error creating property object: {str(e)}")
            raise serializers.ValidationError(f"Error creating property: {str(e)}")
        
        # Save document if provided
        if document_file:
            property_obj.documents = document_file
            property_obj.save()
        
        # Save images
        try:
            if main_image:
                PropertyImage.objects.create(
                    property=property_obj,
                    image=main_image,
                    image_type='main',
                    display_order=1
                )
            
            if thumbnail_image:
                PropertyImage.objects.create(
                    property=property_obj,
                    image=thumbnail_image,
                    image_type='thumbnail',
                    display_order=2
                )
            
            for idx, img in enumerate(additional_images, start=3):
                PropertyImage.objects.create(
                    property=property_obj,
                    image=img,
                    image_type='additional',
                    display_order=idx
                )
        except Exception as e:
            # Rollback property creation if image saving fails
            property_obj.delete()
            logger.error(f"Error saving images: {str(e)}")
            raise serializers.ValidationError(f"Error saving images: {str(e)}")
        
        return property_obj

    def update(self, instance, validated_data):
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        
        if not hasattr(request.user, 'vendor'):
            raise serializers.ValidationError("User must be a vendor")
        
        # Check if vendor owns this property
        if instance.vendor != request.user.vendor:
            raise serializers.ValidationError("You can only update your own properties")
        
        # Extract file data
        main_image = validated_data.pop('main_image', None)
        thumbnail_image = validated_data.pop('thumbnail_image', None)
        additional_images = validated_data.pop('additional_images', [])
        document_file = validated_data.pop('document_file', None)
        
        # Handle amenities and nearby_facilities
        amenities = validated_data.get('amenities', instance.amenities)
        nearby_facilities = validated_data.get('nearby_facilities', instance.nearby_facilities)
        
        # Convert if they are strings
        if isinstance(amenities, str):
            try:
                amenities = json.loads(amenities)
            except json.JSONDecodeError:
                amenities = instance.amenities
        
        if isinstance(nearby_facilities, str):
            try:
                nearby_facilities = json.loads(nearby_facilities)
            except json.JSONDecodeError:
                nearby_facilities = instance.nearby_facilities
        
        validated_data['amenities'] = amenities
        validated_data['nearby_facilities'] = nearby_facilities
        
        # Update document if provided
        if document_file:
            instance.documents = document_file
        
        # Update the instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # Handle images if provided
        if main_image:
            # Delete existing main image
            PropertyImage.objects.filter(property=instance, image_type='main').delete()
            PropertyImage.objects.create(
                property=instance,
                image=main_image,
                image_type='main',
                display_order=1
            )
        
        if thumbnail_image:
            # Delete existing thumbnail image
            PropertyImage.objects.filter(property=instance, image_type='thumbnail').delete()
            PropertyImage.objects.create(
                property=instance,
                image=thumbnail_image,
                image_type='thumbnail',
                display_order=2
            )
        
        if additional_images:
            # Delete existing additional images if needed
            # Or you can keep them and add new ones
            existing_additional = PropertyImage.objects.filter(
                property=instance, 
                image_type='additional'
            )
            existing_count = existing_additional.count()
            
            for idx, img in enumerate(additional_images, start=existing_count + 1):
                PropertyImage.objects.create(
                    property=instance,
                    image=img,
                    image_type='additional',
                    display_order=idx
                )
        
        return instance

class PropertyListSerializer(serializers.ModelSerializer):
    vendor_details = VendorListSerializer(source='vendor', read_only=True)
    main_image = serializers.SerializerMethodField()
    thumbnail_image = serializers.SerializerMethodField()
    price_per_sqft = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Property
        fields = [
            'id', 'property_id', 'title', 'vendor', 'vendor_details',
            'transaction_type', 'property_type', 'price', 'price_per_sqft',
            'total_area_size', 'bedrooms', 'bathrooms', 'city', 'state',
            'main_image', 'thumbnail_image', 'status', 'is_featured', 'is_premium',
            'views_count', 'enquiry_count', 'created_at', 'description',
            'furnishing_status', 'construction_status', 'property_age'
        ]
        read_only_fields = ['property_id', 'created_at', 'updated_at']
    
    def get_main_image(self, obj):
        main_image = obj.images.filter(image_type='main').first()
        if main_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(main_image.image.url)
            return main_image.image.url
        return None
    
    def get_thumbnail_image(self, obj):
        thumbnail_image = obj.images.filter(image_type='thumbnail').first()
        if thumbnail_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(thumbnail_image.image.url)
            return thumbnail_image.image.url
        return None

class PropertyDetailSerializer(serializers.ModelSerializer):
    vendor_details = VendorListSerializer(source='vendor', read_only=True)
    images = PropertyImageSerializer(many=True, read_only=True)
    price_per_sqft = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    document_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'property_id', 'title', 'description', 'vendor', 'vendor_details',
            'transaction_type', 'property_type', 'address', 'google_map_url',
            'city', 'state', 'pincode', 'latitude', 'longitude',
            'total_area_size', 'carpet_area', 'built_up_area',
            'bedrooms', 'bathrooms', 'balconies', 'furnishing_status',
            'floor_number', 'total_floors', 'facing_direction', 'property_age',
            'ownership_type', 'encumbrance_certificate', 'rea_number', 'rera_number',
            'rera_registered', 'loan_availability', 'documents_available', 'negotiable',
            'price', 'maintenance_charges', 'booking_amount', 'security_deposit',
            'price_per_sqft', 'contact_type', 'contact_name', 'contact_mobile',
            'contact_whatsapp', 'contact_email', 'contact_preferred_time', 'use_vendor_info',
            'images', 'status', 'is_featured', 'is_verified', 'is_premium', 'is_approved',
            'is_available', 'views_count', 'enquiry_count', 'created_at',
            'updated_at', 'published_at', 'approved_by', 'approved_at',
            'short_description', 'seo_title', 'seo_description', 'seo_keywords',
            'slug', 'virtual_tour_url', 'floor_plan', 'landmark',
            'construction_status', 'amenities', 'nearby_facilities', 'documents', 'document_url'
        ]
        read_only_fields = ['property_id', 'created_at', 'updated_at', 'approved_by', 'approved_at']
    
    def get_document_url(self, obj):
        if obj.documents:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.documents.url)
            return obj.documents.url
        return None

class PropertyAdminSerializer(serializers.ModelSerializer):
    vendor_details = VendorListSerializer(source='vendor', read_only=True)
    images = PropertyImageSerializer(many=True, read_only=True)
    document_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = '__all__'
        read_only_fields = ['property_id', 'created_at', 'updated_at']
    
    def get_document_url(self, obj):
        if obj.documents:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.documents.url)
            return obj.documents.url
        return None

class PropertyStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('sold_rented', 'Sold/Rented'),
        ('expired', 'Expired')
    ])
    admin_notes = serializers.CharField(required=False, allow_blank=True)

class PropertyEnquirySerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source='property.title', read_only=True)
    vendor_name = serializers.CharField(source='property.vendor.business_name', read_only=True)
    
    class Meta:
        model = PropertyEnquiry
        fields = [
            'id', 'property', 'property_title', 'vendor_name',
            'name', 'email', 'mobile', 'enquiry_type', 'message',
            'is_read', 'responded_by', 'response_notes', 'created_at'
        ]
        read_only_fields = ['created_at']

class CreateEnquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyEnquiry
        fields = ['property', 'name', 'email', 'mobile', 'enquiry_type', 'message']
    
    def validate(self, data):
        property_obj = data.get('property')
        if property_obj and not property_obj.is_available:
            raise serializers.ValidationError(
                "This property is not available for enquiries"
            )
        
        # Increment enquiry count
        if property_obj:
            property_obj.enquiry_count += 1
            property_obj.save(update_fields=['enquiry_count'])
        
        return data

class VendorPropertyDashboardSerializer(serializers.Serializer):
    total_properties = serializers.IntegerField()
    approved_properties = serializers.IntegerField()
    pending_properties = serializers.IntegerField()
    draft_properties = serializers.IntegerField()
    sold_rented_properties = serializers.IntegerField()
    total_views = serializers.IntegerField()
    total_enquiries = serializers.IntegerField()
    recent_enquiries = PropertyEnquirySerializer(many=True)
    recent_properties = PropertyListSerializer(many=True)

class PropertyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = [
            'title', 'description', 'transaction_type', 'property_type',
            'address', 'city', 'state', 'pincode', 'latitude', 'longitude', 'google_map_url',
            'total_area_size', 'carpet_area', 'built_up_area', 'bedrooms', 'bathrooms',
            'balconies', 'furnishing_status', 'floor_number', 'total_floors',
            'facing_direction', 'property_age', 'construction_status',
            'ownership_type', 'encumbrance_certificate', 'rea_number', 'rera_number',
            'rera_registered', 'loan_availability', 'documents_available', 'negotiable',
            'price', 'maintenance_charges', 'booking_amount', 'security_deposit',
            'contact_type', 'contact_name', 'contact_mobile', 'contact_whatsapp',
            'contact_email', 'contact_preferred_time', 'use_vendor_info',
            'short_description', 'seo_title', 'seo_description', 'seo_keywords',
            'virtual_tour_url', 'floor_plan', 'landmark',
            'amenities', 'nearby_facilities', 'subcategory',
        ]
    
    def validate(self, data):
        # When updating, status should go back to pending if approved fields are changed
        if self.instance and self.instance.status == 'approved':
            # Important: When vendor edits approved property, it should go for re-approval
            self.instance.status = 'pending'
            self.instance.save()
        return data

# Public Property Serializers
class PublicPropertyListSerializer(serializers.ModelSerializer):
    main_image = serializers.SerializerMethodField()
    thumbnail_image = serializers.SerializerMethodField()
    price_per_sqft = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    transaction_type = serializers.CharField()
    property_type = serializers.CharField(source='property_type.subcategory_name', read_only=True)
    
    class Meta:
        model = Property
        fields = [
            'id', 'property_id', 'title', 'slug',
            'transaction_type', 'property_type', 'price', 'price_per_sqft',
            'total_area_size', 'bedrooms', 'bathrooms', 'city', 'state',
            'main_image', 'thumbnail_image', 'is_featured', 'is_premium',
            'short_description', 'furnishing_status', 'construction_status',
            'property_age', 'address', 'landmark','contact_name', 
            'contact_mobile','contact_email','contact_whatsapp','vendor',
        ]
    
    def get_main_image(self, obj):
        main_image = obj.images.filter(image_type='main').first()
        if main_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(main_image.image.url)
            return main_image.image.url
        return None
    
    def get_thumbnail_image(self, obj):
        thumbnail_image = obj.images.filter(image_type='thumbnail').first()
        if thumbnail_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(thumbnail_image.image.url)
            return thumbnail_image.image.url
        return None
# services/serializers/real_estate_serializers.py

class PublicPropertyDetailSerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)
    price_per_sqft = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    vendor_id = serializers.IntegerField(source='vendor.id', read_only=True)  
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    vendor_phone = serializers.CharField(source='vendor.phone', read_only=True)
    vendor_email = serializers.CharField(source='vendor.email', read_only=True)
    document_url = serializers.SerializerMethodField()
    normalized_nearby_facilities = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id','vendor_id', 'property_id', 'title', 'slug', 'description',
            'transaction_type', 'property_type', 'address', 'google_map_url',
            'city', 'state', 'pincode', 'latitude', 'longitude',
            'total_area_size', 'carpet_area', 'built_up_area',
            'bedrooms', 'bathrooms', 'balconies', 'furnishing_status',
            'floor_number', 'total_floors', 'facing_direction', 'property_age',
            'ownership_type', 'encumbrance_certificate', 'rea_number', 'rera_number',
            'rera_registered', 'loan_availability', 'documents_available', 'negotiable',
            'price', 'maintenance_charges', 'booking_amount', 'security_deposit',
            'price_per_sqft', 'contact_type', 'contact_name', 'contact_mobile',
            'contact_whatsapp', 'contact_email', 'contact_preferred_time',
            'images', 'is_featured', 'is_verified', 'is_premium',
            'short_description', 'virtual_tour_url', 'floor_plan', 'landmark',
            'construction_status', 'amenities', 'nearby_facilities','normalized_nearby_facilities',
            'vendor_name', 'vendor_phone', 'vendor_email', 'views_count',
            'documents', 'document_url'
        ]
    
    # ✅ CORRECT - This method should be at class level, not inside Meta
    def get_normalized_nearby_facilities(self, obj):
        """Normalize nearby facilities keys to lowercase with consistent names"""
        if not obj.nearby_facilities:
            return {}
        
        normalized = {}
        facilities = obj.nearby_facilities
        
        # Debug print
        print(f"DEBUG: nearby_facilities received: {facilities}")
        print(f"DEBUG: Type: {type(facilities)}")
        
        # Define mapping patterns
        mapping_patterns = {
            'hospitals': ['hospital', 'hospitals', 'medical'],
            'colleges': ['college', 'colleges', 'school', 'schools', 'university', 'universities'],
            'shopping': ['shopping', 'market', 'markets', 'mall', 'malls'],
            'transport': ['transport', 'bus', 'metro', 'train', 'station'],
            'parks': ['park', 'parks', 'garden', 'gardens'],
            'banks': ['bank', 'banks', 'atm'],
            'restaurants': ['restaurant', 'restaurants', 'cafe', 'cafes', 'food']
        }
        
        for norm_key, patterns in mapping_patterns.items():
            for pattern in patterns:
                # Find matching key in facilities
                matching_key = None
                if isinstance(facilities, dict):
                    for facility_key in facilities.keys():
                        if pattern.lower() in str(facility_key).lower():
                            matching_key = facility_key
                            break
                
                if matching_key:
                    normalized[norm_key] = facilities[matching_key]
                    break
        
        return normalized
    
    def get_document_url(self, obj):
        if obj.documents:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.documents.url)
            return obj.documents.url
        return None
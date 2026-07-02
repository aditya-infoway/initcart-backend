#services/serializers/subcategory_serializers.py
from rest_framework import serializers
from ..models.subcategory import ServiceSubcategory
import base64
from django.core.files.base import ContentFile

class ServiceSubcategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    image_base64 = serializers.CharField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = ServiceSubcategory
        fields = [
            'id',
            'parent_service',
            'subcategory_name',
            'description',
            'image',
            'image_url',
            'image_base64',
            'status',
            'created_by',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        if obj.image and hasattr(obj.image, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    
    def validate(self, data):
        # Check if subcategory with same name and parent service already exists
        parent_service = data.get('parent_service')
        subcategory_name = data.get('subcategory_name')
        
        if self.instance:
            # For update, exclude current instance
            exists = ServiceSubcategory.objects.filter(
                parent_service=parent_service,
                subcategory_name=subcategory_name
            ).exclude(id=self.instance.id).exists()
        else:
            # For create
            exists = ServiceSubcategory.objects.filter(
                parent_service=parent_service,
                subcategory_name=subcategory_name
            ).exists()
        
        if exists:
            raise serializers.ValidationError(
                f"Subcategory '{subcategory_name}' already exists for '{parent_service}'"
            )
        
        return data
    
    def create(self, validated_data):
        # Handle base64 image if provided
        image_base64 = validated_data.pop('image_base64', None)
        
        if image_base64:
            # Extract image data from base64 string
            if 'data:image' in image_base64:
                format, imgstr = image_base64.split(';base64,')
                ext = format.split('/')[-1]
                data = ContentFile(base64.b64decode(imgstr), name=f'{validated_data["subcategory_name"]}.{ext}')
                validated_data['image'] = data
        
        # Set created_by from request user
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Handle base64 image if provided
        image_base64 = validated_data.pop('image_base64', None)
        
        if image_base64 is not None:
            if image_base64:
                # Extract image data from base64 string
                if 'data:image' in image_base64:
                    format, imgstr = image_base64.split(';base64,')
                    ext = format.split('/')[-1]
                    data = ContentFile(base64.b64decode(imgstr), name=f'{validated_data.get("subcategory_name", instance.subcategory_name)}.{ext}')
                    validated_data['image'] = data
            else:
                # Clear image if empty string is sent
                validated_data['image'] = None
        
        return super().update(instance, validated_data)
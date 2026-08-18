# pos/serializers/group_unit_serializers.py

from rest_framework import serializers
from pos.models.group_unit import ItemGroup, ItemUnit
from pos.serializers.mixins_serializers import CreatedByReadMixin  


class ItemGroupSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    class Meta:
        model = ItemGroup
        fields = ['id', 'name', 'description', 'created_at','created_by', 'created_by_name']
        read_only_fields = ['created_at']


class ItemUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemUnit
        fields = ['id', 'name', 'symbol', 'unit_type', 'supports_fractional', 'created_at']
        read_only_fields = ['created_at']


class GroupCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemGroup
        fields = ['name', 'description']

    def validate_name(self, value):
        request = self.context.get('request')
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            raise serializers.ValidationError("No branch linked to this user")
        if ItemGroup.objects.filter(name__iexact=value, branch=branch).exists():
            raise serializers.ValidationError(f"Group '{value}' already exists for your branch")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)

class UnitCreateSerializer(serializers.ModelSerializer):
    """
    Admin ke liye naye global unit banane ka serializer.
    Branch validation nahi hai ab.
    """
    class Meta:
        model = ItemUnit
        fields = ['name', 'symbol', 'unit_type', 'supports_fractional', 'conversion_to_base', 'description']

    def validate_name(self, value):
        if ItemUnit.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError(f"Unit '{value}' already exists globally")
        return value

    def validate_symbol(self, value):
        if ItemUnit.objects.filter(symbol__iexact=value).exists():
            raise serializers.ValidationError(f"Symbol '{value}' already exists globally")
        return value
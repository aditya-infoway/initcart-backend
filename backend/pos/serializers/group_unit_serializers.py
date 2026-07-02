# pos/serializers/group_unit_serializers.py

from rest_framework import serializers
from pos.models.group_unit import ItemGroup, ItemUnit


class ItemGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemGroup
        fields = ['id', 'name', 'description', 'created_at']
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
        branch = request.user.branch
        if ItemGroup.objects.filter(name__iexact=value, branch=branch).exists():
            raise serializers.ValidationError(f"Group '{value}' already exists for your branch")
        return value


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
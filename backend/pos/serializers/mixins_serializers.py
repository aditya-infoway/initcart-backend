from rest_framework import serializers


class CreatedByReadMixin(serializers.Serializer):
    created_by_name = serializers.SerializerMethodField()

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_display_name()
        return None


class CreatedByWriteMixin:
    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)
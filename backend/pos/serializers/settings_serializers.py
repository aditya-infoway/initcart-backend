#pos/serializer/settings_serializers.py
from rest_framework import serializers
from pos.models.settings import setting

class SettingSerializers(serializers.ModelSerializer):
    class Meta:
        model = setting
        fields = "__all__"
        read_only_fields = ["branch"]

    def create(self, validated_data):
        branch = self.context.get("branch")
        if branch:
            validated_data["branch"] = branch
        return super().create(validated_data)
    
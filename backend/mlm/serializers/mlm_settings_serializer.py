#mlm/serializers/mlm_settings_serializer.py
from rest_framework import serializers
from mlm.models.mlm_settings import MLMSettings


class MLMSettingsSerializer(serializers.ModelSerializer):

    class Meta:
        model = MLMSettings
        fields = "__all__"
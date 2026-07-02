from rest_framework import serializers
from mlm.models.mlm_level_config import MLMLevelConfig

class MLMLevelConfigSerializer(serializers.ModelSerializer):

    class Meta:
        model = MLMLevelConfig
        fields = "__all__"

    def validate(self, data):

        if MLMLevelConfig.objects.exists():
            raise serializers.ValidationError(
                "MLM level configuration already exists."
            )

        return data
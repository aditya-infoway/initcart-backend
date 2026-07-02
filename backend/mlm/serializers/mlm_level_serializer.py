#mlm/serializers/mlm_level_serializer.py
from rest_framework import serializers
from django.db.models import Sum

from mlm.models.mlm_level import MLMLevel
from mlm.models.mlm_level_config import MLMLevelConfig
from mlm.models.profit_distribution import ProfitDistribution


class MLMLevelSerializer(serializers.ModelSerializer):

    class Meta:
        model = MLMLevel
        fields = "__all__"
        read_only_fields = ["config"]

    #  Automatically attach default config
    def create(self, validated_data):

        config = MLMLevelConfig.objects.first()

        if not config:
            raise serializers.ValidationError(
                "MLM configuration not found"
            )

        validated_data["config"] = config

        return super().create(validated_data)

    #  Validation for MLM percentage
    def validate(self, data):

        config = MLMLevelConfig.objects.first()

        profit_config = ProfitDistribution.objects.first()

        if not profit_config:
            raise serializers.ValidationError(
                "Profit distribution not configured"
            )

        mlm_percentage = profit_config.mlm_percentage

        current_total = MLMLevel.objects.filter(config=config).exclude(
            id=self.instance.id if self.instance else None
        ).aggregate(total=Sum("percentage"))["total"] or 0

        if current_total + data["percentage"] > mlm_percentage:
            raise serializers.ValidationError(
                f"Total MLM level percentage cannot exceed {mlm_percentage}%"
            )

        return data
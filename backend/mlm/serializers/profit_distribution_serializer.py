from rest_framework import serializers
from mlm.models.profit_distribution import ProfitDistribution

class ProfitDistributionSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProfitDistribution
        fields = "__all__"

    def validate(self, data):

        total = (
            data.get("pos_percentage", 0) +
            data.get("service_percentage", 0) +
            data.get("mlm_percentage", 0) +
            data.get("company_percentage", 0)
        )

        if total != 100:
            raise serializers.ValidationError(
                "Total percentage must equal 100%"
            )

        return data
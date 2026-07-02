from rest_framework import serializers
from pos.models.salesentry import SalesMaster

class SalesDeshboardSerializers(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = SalesMaster
        fields = ["bill_no", "customer_name", "grand_total"]

    def get_customer_name(self, obj):
            if obj.customer:
                return obj.customer.account_name  # ✅ correct
            return None  
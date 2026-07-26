# pos/serializers/sales_bill_display_serializers.py
from rest_framework import serializers
from pos.models.sales_bill_display_setting import SalesBillDisplaySetting
from pos.models.branch import Branch


class SalesBillDisplaySettingSerializer(serializers.ModelSerializer):
    selected_branches = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), many=True, required=False
    )
    selected_branches_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SalesBillDisplaySetting
        fields = ["id", "mode", "selected_branches", "selected_branches_detail"]

    def get_selected_branches_detail(self, obj):
        return [
            {"id": b.id, "branch_name": b.branch_name}
            for b in obj.selected_branches.all()
        ]
from rest_framework import serializers
from pos.models.cashreceipt import CashReceipt

class CashReceiptSerializer(serializers.ModelSerializer):
    cash_account_name = serializers.CharField(
        source="cash_account.account_name", read_only=True
    )
    party_name = serializers.CharField(
        source="op_account.account_name", read_only=True
    )

    #  Party (op_account) full details for receipt print — "Received With Thanks From"
    party_address = serializers.CharField(source="op_account.address", read_only=True, default=None)
    party_city = serializers.CharField(source="op_account.city", read_only=True, default=None)
    party_state = serializers.CharField(source="op_account.state", read_only=True, default=None)
    party_country = serializers.CharField(source="op_account.country", read_only=True, default=None)
    party_pincode = serializers.CharField(source="op_account.pincode", read_only=True, default=None)
    party_phone = serializers.CharField(source="op_account.phone", read_only=True, default=None)
    party_mobile = serializers.CharField(source="op_account.mobile", read_only=True, default=None)
    party_email = serializers.CharField(source="op_account.email", read_only=True, default=None)
    party_gst_no = serializers.CharField(source="op_account.gst_no", read_only=True, default=None)
    party_pan_card = serializers.CharField(source="op_account.pan_card", read_only=True, default=None)

    #  Branch details for receipt print header (multi-branch)
    branch_name = serializers.CharField(source="branch.branch_name", read_only=True)
    branch_owner_name = serializers.CharField(source="branch.owner_name", read_only=True)
    branch_address = serializers.CharField(source="branch.address", read_only=True, default=None)
    branch_city = serializers.CharField(source="branch.city", read_only=True, default=None)
    branch_state = serializers.CharField(source="branch.state", read_only=True, default=None)
    branch_country = serializers.CharField(source="branch.country", read_only=True, default=None)
    branch_pincode = serializers.CharField(source="branch.pincode", read_only=True, default=None)
    branch_phone = serializers.CharField(source="branch.phone", read_only=True, default=None)
    branch_email = serializers.CharField(source="branch.email", read_only=True, default=None)

    class Meta:
        model = CashReceipt
        fields = "__all__"
        read_only_fields = ["branch"]

    def create(self, validated_data):
        branch = self.context.get("branch")
        if branch:
            validated_data["branch"] = branch
        return super().create(validated_data)
    
    
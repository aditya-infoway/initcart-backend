from rest_framework import serializers
from pos.models.cashreceipt import CashReceipt
from pos.serializers.mixins_serializers import CreatedByReadMixin

class CashReceiptSerializer(CreatedByReadMixin, serializers.ModelSerializer):
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
        # ✅ CHANGE: fields = "__all__" → explicit fields
        fields = [
            'id', 'date', 'voucher_no', 'cash_account', 'op_account',
            'branch', 'amount', 'narration', 'type', 'created_at',
            'cash_account_name', 'party_name',
            'party_address', 'party_city', 'party_state', 'party_country',
            'party_pincode', 'party_phone', 'party_mobile', 'party_email',
            'party_gst_no', 'party_pan_card',
            'branch_name', 'branch_owner_name', 'branch_address',
            'branch_city', 'branch_state', 'branch_country',
            'branch_pincode', 'branch_phone', 'branch_email',
            'purchase_return', 'sales_entry', 'stock_transfer',
            'stock_return', 'b2b_sale',
            'created_by', 'created_by_name',   # ✅ ADD
        ]
        read_only_fields = ["branch"]

    def create(self, validated_data):
        branch = self.context.get("branch")
        if branch:
            validated_data["branch"] = branch
        
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        
        return super().create(validated_data)

    
    
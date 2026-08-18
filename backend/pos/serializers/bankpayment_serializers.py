from rest_framework import serializers
from pos.models.bankpayment import BankPayment
from pos.serializers.mixins_serializers import CreatedByReadMixin

class BankPaymentSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    # Add read-only fields for display
    bank_account_name = serializers.CharField(
        source="bank_account.account_name", read_only=True
    )
    party_name = serializers.CharField(
        source="op_account.account_name", read_only=True
    )

    class Meta:
        model = BankPayment
        fields = [
            'id', 
            'date', 
            'voucher_no', 
            'bank_account', 
            'op_account',
            'branch', 
            'amount', 
            'mode', 
            'cheque_no', 
            'cheque_date',
            'cheque_clear_date', 
            'narration', 
            'type', 
            'created_at',
            'bank_account_name', 
            'party_name', 
            'sales_return', 
            'purchase',
            'stock_transfer', 
            'created_by', 
            'created_by_name',  # ✅ ADDED - ONLY MISSING FIELD
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
#pos/serializer/bankpayment_serializers.py
from rest_framework import serializers
from pos.models.bankpayment import BankPayment

class BankPaymentSerializer(serializers.ModelSerializer):
    # Add read-only fields for display
    bank_account_name = serializers.CharField(
        source="bank_account.account_name", read_only=True
    )
    party_name = serializers.CharField(
        source="op_account.account_name", read_only=True
    )

    class Meta:
        model = BankPayment
        fields = "__all__"
        read_only_fields = ["branch"]  # client cannot send branch

    def create(self, validated_data):
        branch = self.context.get("branch")  # <-- use context instead of data
        if branch:
            validated_data["branch"] = branch
        return super().create(validated_data)
    
    
    
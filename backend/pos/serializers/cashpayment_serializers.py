# pos/serializers/cashpayment_serializers.py
from rest_framework import serializers
from pos.models.cashpayment import CashPayment

class CashPaymentSerializer(serializers.ModelSerializer):
    # Add read-only fields for display
    cash_account_name = serializers.CharField(
        source="cash_account.account_name", read_only=True
    )
    party_name = serializers.CharField(
        source="op_account.account_name", read_only=True
    )

    class Meta:
        model = CashPayment
        fields = "__all__"
        read_only_fields = ["branch"]  # client cannot send branch

    def create(self, validated_data):
        branch = self.context.get("branch")  # <-- use context instead of data
        if branch:
            validated_data["branch"] = branch
        
        # Log the type being created
        print(f"Creating CashPayment with type: {validated_data.get('type')}")
        
        return super().create(validated_data)
    
    
    
    
# pos/serializers/cashpayment_serializers.py
from rest_framework import serializers
from pos.models.cashpayment import CashPayment
from pos.serializers.mixins_serializers import CreatedByReadMixin 

class CashPaymentSerializer(CreatedByReadMixin, serializers.ModelSerializer):
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
        branch = self.context.get("branch")
        if branch:
            validated_data["branch"] = branch
        
        # ✅ ADD - Set created_by from request
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
            print(f"✅ CashPayment created_by set to: {request.user}")
        
        return super().create(validated_data)
    
    
    
    
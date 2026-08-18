from rest_framework import serializers
from pos.models.contra import Contra
from pos.serializers.mixins_serializers import CreatedByReadMixin

class ContraSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    cash_account_name = serializers.CharField(
        source="cash_account.account_name", read_only=True
    )
    party_name = serializers.CharField(
        source="op_account.account_name", read_only=True
    )

    class Meta:
        model = Contra
        # ✅ CHANGE: fields = "__all__" → explicit fields
        fields = [
            'id', 'date', 'voucher_no', 'cash_account', 'op_account',
            'branch', 'amount', 'narration', 'type', 'created_at',
            'cash_account_name', 'party_name',
            'created_by', 'created_by_name',   # ✅ ADD
        ]
        read_only_fields = ["branch"]

    def validate_voucher_no(self, value):
        """Validate that voucher_no is unique within the branch."""
        branch = self.context.get("branch")
        if not branch:
            raise serializers.ValidationError("Branch context is required.")
        
        if Contra.objects.filter(branch=branch, voucher_no=value).exists():
            raise serializers.ValidationError(
                f"Voucher number '{value}' already exists for this branch."
            )
        return value

    def create(self, validated_data):
        branch = self.context.get("branch")
        if branch:
            validated_data["branch"] = branch
        
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        
        return super().create(validated_data)
# pos/serializers/schemeoffer_serializers.py
from rest_framework import serializers

from pos.models.branch import Branch
from pos.models.schemeoffer import SchemeOffer


class SchemeOfferSerializer(serializers.ModelSerializer):
    branches = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), many=True, required=False
    )
    branch_names = serializers.SerializerMethodField(read_only=True)
    created_by_branch_name = serializers.CharField(
        source="created_by_branch.branch_name", read_only=True, default=None
    )

    class Meta:
        model = SchemeOffer
        fields = [
            "id",
            "offer_name",
            "start_date",
            "end_date",
            "availability",
            "branches",
            "branch_names",
            "amount",
            "scheme_type",
            "status",
            "created_by_branch",
            "created_by_branch_name",
            "created_at",
        ]
        read_only_fields = ["created_by_branch", "created_at"]

    def get_branch_names(self, obj):
        if obj.availability == "all":
            return "All Branches"
        return ", ".join(obj.branches.values_list("branch_name", flat=True))

    def validate(self, data):
        start = data.get("start_date", getattr(self.instance, "start_date", None))
        end = data.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError("End date must be on/after start date")

        availability = data.get(
            "availability", getattr(self.instance, "availability", "all")
        )
        branches = data.get("branches", None)
        existing_has_branches = bool(
            self.instance and self.instance.pk and self.instance.branches.exists()
        )
        if availability == "selected" and not branches and not existing_has_branches:
            raise serializers.ValidationError(
                "Select at least one branch for 'Selected Branch' availability"
            )

        amount = data.get("amount", getattr(self.instance, "amount", None))
        if amount is not None and amount <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")

        return data

    def create(self, validated_data):
        branches = validated_data.pop("branches", [])
        scheme = SchemeOffer.objects.create(**validated_data)
        if scheme.availability == "selected":
            scheme.branches.set(branches)
        return scheme

    def update(self, instance, validated_data):
        branches = validated_data.pop("branches", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        if instance.availability == "selected" and branches is not None:
            instance.branches.set(branches)
        elif instance.availability == "all":
            instance.branches.clear()
        return instance


class SchemeCustomerRowSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField()
    customer_phone = serializers.SerializerMethodField()
    total_sales = serializers.FloatField()
    
    def get_customer_phone(self, obj):
        # obj is the customer dict with customer_id
        from pos.models.account import Account
        try:
            customer = Account.objects.get(id=obj.get('customer_id'))
            return customer.mobile or ""
        except Account.DoesNotExist:
            return ""


class SchemeBranchReportSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField()
    branch_name = serializers.CharField()
    customers = SchemeCustomerRowSerializer(many=True)


class SchemeMonthReportSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    label = serializers.CharField()
    period_start = serializers.CharField()
    period_end = serializers.CharField()
    branches = SchemeBranchReportSerializer(many=True)
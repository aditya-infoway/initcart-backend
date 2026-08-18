# pos/serializers/account_serializer.py
from rest_framework import serializers
from pos.models.account import Account
from pos.serializers.mixins_serializers import CreatedByReadMixin
import re

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'
    
    def validate(self, attrs):
        group = attrs.get('group') or getattr(self.instance, 'group', None)
        branch = attrs.get('branch') or getattr(self.instance, 'branch', None)

        if group == 'Sundry Creditor(Main)' and branch:
            qs = Account.objects.filter(branch=branch, group='Sundry Creditor(Main)')
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "group": "This branch already has a Sundry Creditor(Main) account. Only one is allowed per branch."
                })
        return attrs    

    def validate_mobile(self, value):
        if value and not re.match(r'^[0-9]{10}$', value):
            raise serializers.ValidationError("Mobile number must be 10 digits")
        return value

    def validate_pincode(self, value):
        if value and not re.match(r'^[0-9]{6}$', value):
            raise serializers.ValidationError("Pincode must be 6 digits")
        return value

    def validate_gst_no(self, value):
        if value and not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', value):
            raise serializers.ValidationError("Invalid GST Number")
        return value

    def validate_pan_card(self, value):
        if value and not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', value):
            raise serializers.ValidationError("Invalid PAN Card Number")
        return value
    
    def create(self, validated_data):
        # set created_by                          # ADD these 4 lines
        request = self.context.get("request")      # ADD
        if request and request.user and request.user.is_authenticated:  # ADD
            validated_data["created_by"] = request.user  # ADD
        
        validated_data["current_balance"] = validated_data.get(
            "opening_balance", 0
        )
        return super().create(validated_data)
    

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "account_name", "group", "current_balance"]


class AccountviewSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "branch_name",
            "account_name",
            "group",
            "opening_balance",
            "drcr",
            "address",
            "country",
            "state",
            "city",
            "email",
            "pincode",
            "phone",
            "mobile",
            "gst_no",
            "pan_card",
            "current_balance",
            "current_drcr",
            "created_by",
            "created_by_name",
        ]


class AccountTermsSerializers(serializers.ModelSerializer):
    class Meta:
        model = Account 
        fields = ["id", "account_name", "group"]
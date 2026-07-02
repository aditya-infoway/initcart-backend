# pos/serializers/account_serializer.py
from rest_framework import serializers
from pos.models.account import Account
import re

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'

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
        validated_data["current_balance"] = validated_data.get(
            "opening_balance", 0
        )
        return super().create(validated_data)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "account_name", "group", "current_balance"]


class AccountviewSerializer(serializers.ModelSerializer):
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
            "pincode",
            "phone",
            "mobile",
            "gst_no",
            "pan_card",
            "current_balance",
            "current_drcr",
        ]


class AccountTermsSerializers(serializers.ModelSerializer):
    class Meta:
        model = Account 
        fields = ["id", "account_name", "group"]
from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from ecommerce.models.vendor import (
    Vendor, VendorApprovalRequest, VendorWallet,
    VendorWithdrawalRequest, Brand
)

User = get_user_model()


# ================================
#  VENDOR REGISTRATION (Frontend)
# ================================
class VendorRegistrationSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = Vendor
        fields = [
            "vendor_type", "vendor_subtype",
            "business_name", "owner_name",
            "email", "phone", "password", "confirm_password",
            "address", "city", "state", "pincode",
            "licence_file", "gst_certificate", "id_proof", "store_logo"  # ADDED: store_logo
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
        if Vendor.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Vendor with this email already exists."})

        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        raw_password = validated_data["password"]

        # Step 1: Create django User with vendor role
        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=raw_password,
            role="vendor",
            first_name=validated_data.get("owner_name", "").split()[0] or "",
            last_name=" ".join(validated_data.get("owner_name", "").split()[1:]) or ""
        )

        # Step 2: Hash vendor password
        validated_data["password"] = make_password(raw_password)

        # Step 3: Create Vendor with user link
        vendor = Vendor.objects.create(user=user, **validated_data)

        # Step 4: Auto approval + wallet create
        VendorApprovalRequest.objects.create(vendor=vendor)
        VendorWallet.objects.create(vendor=vendor)

        return vendor


# ================================
# LIST + DETAIL + GENERIC
# ================================
class VendorListSerializer(serializers.ModelSerializer):
    store_logo_url = serializers.SerializerMethodField()  # ADDED: For logo URL

    class Meta:
        model = Vendor
        fields = [
            "id", "business_name", "vendor_type",
            "vendor_subtype", "owner_name", "email",
            "phone", "status", "verification_label",
            "created_at", "created_by", "store_logo", "store_logo_url"  # ADDED: store_logo fields
        ]

    def get_store_logo_url(self, obj):
        if obj.store_logo:
            return obj.store_logo.url
        return None


class VendorDetailSerializer(serializers.ModelSerializer):
    store_logo_url = serializers.SerializerMethodField()  # ADDED: For logo URL

    class Meta:
        model = Vendor
        exclude = ("password",)
        read_only_fields = ("created_at", "updated_at", "is_approved")

    def get_store_logo_url(self, obj):
        if obj.store_logo:
            return obj.store_logo.url
        return None


class VendorSerializer(serializers.ModelSerializer):
    """Admin create/update vendor"""
    store_logo_url = serializers.SerializerMethodField()
    
    class Meta:     
        model = Vendor
        fields = "__all__"
        # ✅ ADD THIS FOR FILE FIELDS
        extra_kwargs = {
            'licence_file': {'required': False},
            'gst_certificate': {'required': False},
            'store_logo': {'required': False},
            'id_proof': {'required': False},
        }

    def get_store_logo_url(self, obj):
        if obj.store_logo:
            return obj.store_logo.url
        return None



# ================================
# APPROVAL SERIALIZERS
# ================================
class VendorApprovalSerializer(serializers.ModelSerializer):
    vendor_details = VendorDetailSerializer(source="vendor", read_only=True)

    class Meta:
        model = VendorApprovalRequest
        fields = "__all__"


class VendorApprovalActionSerializer(serializers.Serializer):
    bank_name = serializers.CharField(required=True)
    account_number = serializers.CharField(required=True)
    ifsc_code = serializers.CharField(required=True)
    upi_id = serializers.CharField(required=False, allow_blank=True)
    admin_notes = serializers.CharField(required=False, allow_blank=True)


# ================================
# WALLET / WITHDRAWAL / BRAND
# ================================
class VendorWalletSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.business_name", read_only=True)
    vendor_email = serializers.CharField(source="vendor.email", read_only=True)

    class Meta:
        model = VendorWallet
        fields = "__all__"


class VendorWithdrawalSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.business_name", read_only=True)
    vendor_email = serializers.CharField(source="vendor.email", read_only=True)

    class Meta:
        model = VendorWithdrawalRequest
        fields = "__all__"
        read_only_fields = ("request_id", "request_date")


class BrandSerializer(serializers.ModelSerializer):
    product_count = serializers.ReadOnlyField()
    total_products = serializers.ReadOnlyField()
    
    class Meta:
        model = Brand
        fields = [
            "id", 
            "brand_name", 
            "brand_logo", 
            "description", 
            "status", 
            "created_by", 
            "created_at", 
            "updated_at",
            "product_count",
            "total_products"
        ]
# pos/serializers/branch_serializers.py
from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.account import Account
from pos.serializers.mixins_serializers import CreatedByReadMixin,CreatedByWriteMixin

User = get_user_model()


DEBITOR_GROUPS = ['Customer - Sundry Debitor', 'Sundry Debitor(Internal)']
CREDITOR_GROUPS = ['Supplier - Sundry Creditor', 'Sundry Creditor(Internal)']


class BranchCreateSerializer(CreatedByWriteMixin,serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    sundry_debitor_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(group__in=DEBITOR_GROUPS),
        required=False, allow_null=True
    )
    sundry_creditor_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(group__in=CREDITOR_GROUPS),
        required=False, allow_null=True
    )

    class Meta:
        model = Branch
        fields = [
            "branch_type", "branch_name", "owner_name",
            "email", "phone", "password",
            "address", "city", "state", "country", "pincode",
            "bank_name", "account_number", "ifsc_code", "upi_id",
            "licence_file", "gst_certificate", "branch_logo", "id_proof",
            "status", "sundry_debitor_account", "sundry_creditor_account",
            "ownership_type",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, attrs):
            if Branch.objects.filter(email=attrs["email"]).exists():
                raise serializers.ValidationError({"email": "Branch with this email already exists."})

            debitor = attrs.get("sundry_debitor_account")
            creditor = attrs.get("sundry_creditor_account")
            if debitor and creditor:
                raise serializers.ValidationError({
                    "sundry_creditor_account": "only one linked account allowed —  Debitor or Creditor, not both ."
                })
            return attrs
    def create(self, validated_data):
        raw_password = validated_data.pop("password")

        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=raw_password,
            role="branch",
            first_name=validated_data.get("owner_name", "").split()[0] or "",
            last_name=" ".join(validated_data.get("owner_name", "").split()[1:]) or ""
        )

        validated_data["password"] = make_password(raw_password)

        # ✅ Yahan manually created_by set karo
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user

        branch = Branch.objects.create(user=user, **validated_data)
        return branch

#  BRANCH LIST SERIALIZER
class BranchListSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    branch_logo_url = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    sundry_debitor_account_name = serializers.CharField(
        source="sundry_debitor_account.account_name", read_only=True, default=None
    )
    sundry_creditor_account_name = serializers.CharField(
        source="sundry_creditor_account.account_name", read_only=True, default=None
    )

    class Meta:
        model = Branch
        fields = [
            "id", "branch_name", "branch_type", "owner_name",
            "email", "phone", "status", "city", "state",
            "branch_logo", "branch_logo_url", "created_at", "updated_at",
            "sundry_debitor_account_name","sundry_creditor_account_name",
            "ownership_type","created_by", "created_by_name"
        ]

    def get_branch_logo_url(self, obj):
        if obj.branch_logo:
            return obj.branch_logo.url
        return None

#  BRANCH DETAIL SERIALIZER
class BranchDetailSerializer(serializers.ModelSerializer):
    branch_logo_url = serializers.SerializerMethodField()
    licence_file_url = serializers.SerializerMethodField()
    gst_certificate_url = serializers.SerializerMethodField()
    sundry_debitor_account_name = serializers.CharField(
        source="sundry_debitor_account.account_name", read_only=True, default=None
    )
    sundry_creditor_account_name = serializers.CharField(
        source="sundry_creditor_account.account_name", read_only=True, default=None
    )
    id_proof_url = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Branch
        exclude = ("password",)
        read_only_fields = ("created_at", "updated_at")

    def get_branch_logo_url(self, obj):
        if obj.branch_logo:
            return obj.branch_logo.url
        return None

    def get_licence_file_url(self, obj):
        if obj.licence_file:
            return obj.licence_file.url
        return None

    def get_gst_certificate_url(self, obj):
        if obj.gst_certificate:
            return obj.gst_certificate.url
        return None

    def get_id_proof_url(self, obj):
        if obj.id_proof:
            return obj.id_proof.url
        return None

#  BRANCH UPDATE SERIALIZEr

class BranchUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.EmailField(required=False)
    branch_code = serializers.CharField(required=False, allow_blank=True, max_length=3)
    sundry_debitor_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(group__in=DEBITOR_GROUPS),
        required=False, allow_null=True
    )
    sundry_creditor_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(group__in=CREDITOR_GROUPS),
        required=False, allow_null=True
    )

    class Meta:
        model = Branch
        fields = [
            "branch_type", "branch_name", "owner_name", "phone",
            "address", "city", "state", "country", "pincode","email",
            "bank_name", "account_number", "ifsc_code", "upi_id",
            "licence_file", "gst_certificate", "branch_logo", "id_proof",
            "status", "password", "branch_code",
            "sundry_debitor_account", "sundry_creditor_account",
            "ownership_type",
        ]

    def validate_email(self, value):
        qs = Branch.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This email is already used by another branch.")
        return value
    
    def validate(self, attrs):
        debitor = attrs.get("sundry_debitor_account")
        creditor = attrs.get("sundry_creditor_account")
        if debitor and creditor and debitor.id == creditor.id:
            raise serializers.ValidationError({
                "sundry_creditor_account": "Same account cannot be used as both debitor and creditor."
            })
        return attrs

    def validate_branch_code(self, value):
        code = (value or "").strip().upper()
        if not code:
            return ""
        if len(code) != 3 or not code.isalpha():
            raise serializers.ValidationError("Branch code must be exactly 3 letters (A-Z).")
        qs = Branch.objects.filter(branch_code=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This branch code is already taken by another branch.")
        return code

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)

        if 'branch_code' in validated_data:
            code = validated_data.pop('branch_code')
            instance.branch_code = code if code else None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password and password.strip():
            if instance.user:
                instance.user.set_password(password)
                instance.user.save()
                instance.password = make_password(password)

        instance.save()
        return instance
    
    
    
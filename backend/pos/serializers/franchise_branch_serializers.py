# pos/serializers/franchise_branch_serializers.py
from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from pos.models.branch import Branch
from pos.models.account import Account
from users.models import ROLE_CHOICES

User = get_user_model()

DEBITOR_GROUPS = ['Customer - Sundry Debitor', 'Sundry Debitor(Internal)']
CREDITOR_GROUPS = ['Supplier - Sundry Creditor', 'Sundry Creditor(Internal)']


class FranchiseBranchCreateSerializer(serializers.ModelSerializer):
    """
    Franchise (ya uske permitted employee) is serializer se apna
    2nd-level Branch create karta hai. GST/PAN edit nahi hote — create()
    ke andar parent Franchise se auto-copy ho jaate hain.
    """
    password = serializers.CharField(write_only=True, required=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, required=True)
    ALLOWED_ROLES = ("branch", "branch_customer", "branch_agent", "branch_both", "vendor")

    role = serializers.ChoiceField(
        choices=[(r, r) for r in ALLOWED_ROLES],
        required=False,
        default="branch",
    )
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
            "branch_name",      # Business Name
            "owner_name",
            "phone",            # Owner Mobile Number
            "email",
            "password", "confirm_password",
            "address", "country", "state", "city",
            "sundry_debitor_account", "sundry_creditor_account",
            "role", 
        ]

    def validate(self, attrs):
        role = attrs.get("role", "branch")
        if role not in self.ALLOWED_ROLES:
            raise serializers.ValidationError({"role": "Invalid account type."})

        if attrs.get("password") != attrs.pop("confirm_password", None):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        if Branch.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "This email is already used by another branch."})

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        parent_franchise = self.context["parent_franchise"]
        raw_password = validated_data.pop("password")
        role = validated_data.pop("role", "branch")   # ✅ NEW — franchise ne jo type choose kiya

        name_parts = validated_data.get("owner_name", "").split()

        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=raw_password,
            role=role,                                  # ✅ hardcoded "branch" ki jagah dynamic
            first_name=name_parts[0] if name_parts else "",
            last_name=" ".join(name_parts[1:]) if len(name_parts) > 1 else "",
        )

        branch = Branch.objects.create(
            user=user,
            parent_franchise=parent_franchise,
            ownership_type="branch",   # ⚠️ ye Branch.ownership_type hai — hamesha "branch" rahega
                                        # (2-level hierarchy ke liye). role alag cheez hai (User.role).
            branch_type=parent_franchise.branch_type,
            status="active",
            created_by=request.user if request.user.is_authenticated else None,
            password=make_password(raw_password),
            **validated_data,
        )

        branch.copy_tax_details_from_franchise()
        return branch


class FranchiseBranchListSerializer(serializers.ModelSerializer):
    linked_account_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Branch
        fields = [
            "id", "branch_name", "owner_name", "phone", "email",
            "address", "country", "state", "city",
            "gst_number", "pan_number", "status",
            "linked_account_name", "created_at",
        ]

    def get_linked_account_name(self, obj):
        if obj.sundry_debitor_account:
            return obj.sundry_debitor_account.account_name
        if obj.sundry_creditor_account:
            return obj.sundry_creditor_account.account_name
        return None


class FranchiseBranchUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    confirm_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
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
            "branch_name", "owner_name", "phone", "email", "password", "confirm_password",
            "address", "country", "state", "city", "status",
            "sundry_debitor_account", "sundry_creditor_account",
        ]

    def validate(self, attrs):
        pwd = attrs.get("password")
        confirm = attrs.pop("confirm_password", None)
        if pwd and pwd != confirm:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def validate_email(self, value):
        qs = Branch.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This email is already used by another branch.")
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password and password.strip():
            if instance.user:
                instance.user.set_password(password)
                instance.user.save()
            instance.password = make_password(password)

        instance.save()
        return instance
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from users.models import User


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    referral_code = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = (
            'username',
            'email',
            'password',
            'role',
            'phone',
            'referral_code'
        )

    # ── Validation ───────────────────────────────────────────────────────────

    def validate_username(self, value):
        value = value.strip()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        # Superadmin email se koi aur register nahi kar sakta
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_role(self, value):
        # Koi bhi superadmin role se register nahi kar sakta
        if value in ("superadmin",):
            raise serializers.ValidationError("Invalid role.")
        return value

    def create(self, validated_data):
        referral_code = validated_data.pop("referral_code", None)
        referred_by = None

        if referral_code:
            try:
                referred_by = User.objects.get(referral_code=referral_code)
            except User.DoesNotExist:
                pass

        user = User.objects.create(
            username=validated_data['username'],
            email=validated_data['email'].lower(),
            role=validated_data['role'],
            phone=validated_data.get('phone', ''),
            referred_by=referred_by
        )
        user.set_password(validated_data['password'])
        user.save()

        return user
    
    
    
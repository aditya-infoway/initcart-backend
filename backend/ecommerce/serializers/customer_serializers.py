# ecommerce/serializers/customer_serializers.py  (Complete fixed version)
# Changes from original:
#   - CustomerLoginSerializer  → added phone login + better error messages
#   - ForgotPasswordSerializer → role__in uses CUSTOMER_ROLES (covers branch variants)
#   - ResetPasswordSerializer  → same
#   - VerifyResetTokenSerializer → same
#   - All other serializers → unchanged

from rest_framework import serializers
from django.contrib.auth import authenticate
from users.models import User
from ecommerce.models.customer import CustomerProfile
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings

# All roles that count as "customer" — single source of truth
CUSTOMER_ROLES = (
    "customer",
    "both",
    "branch_customer",
    "branch_agent",
    "branch_both",
)


# ─────────────────────────────────────────────────────────────────────────────
class CustomerRegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True, min_length=3, max_length=150, trim_whitespace=True
    )
    email           = serializers.EmailField(required=True, trim_whitespace=True)
    password        = serializers.CharField(
        required=True, write_only=True,
        style={'input_type': 'password'}, min_length=8, max_length=128
    )
    confirm_password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'}
    )
    full_name = serializers.CharField(required=True, max_length=255, trim_whitespace=True)
    phone     = serializers.CharField(required=True, max_length=15, trim_whitespace=True)
    address   = serializers.CharField(required=True, trim_whitespace=True)
    city      = serializers.CharField(required=True, max_length=100, trim_whitespace=True)
    state     = serializers.CharField(required=True, max_length=100, trim_whitespace=True)
    referral_code = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def validate_username(self, value):
        value = value.strip().lower()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists.")
        return value

    def validate_phone(self, value):
        phone_digits = ''.join(filter(str.isdigit, value))
        if len(phone_digits) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits.")
        return phone_digits

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})
        if len(data['password']) < 8:
            raise serializers.ValidationError({"password": ["Password must be at least 8 characters."]})
        return data

    def create(self, validated_data):
        referral_code = validated_data.get('referral_code', '')
        referred_by   = None
        if referral_code:
            try:
                referred_by = User.objects.get(referral_code=referral_code)
            except User.DoesNotExist:
                pass

        user = User.objects.create_user(
            username   = validated_data['username'],
            email      = validated_data['email'],
            password   = validated_data['password'],
            role       = User.ROLE_CUSTOMER,
            phone      = validated_data['phone'],
            referred_by= referred_by,
        )

        CustomerProfile.objects.create(
            user      = user,
            full_name = validated_data['full_name'],
            phone     = validated_data['phone'],
            email     = validated_data['email'],
            address   = validated_data['address'],
            city      = validated_data['city'],
            state     = validated_data['state'],
        )
        return user


# ─────────────────────────────────────────────────────────────────────────────
class CustomerLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True, trim_whitespace=True)
    password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'}
    )

    def validate(self, data):
        identifier = data.get('username', '').strip()
        password   = data.get('password', '')

        if not identifier or not password:
            raise serializers.ValidationError("Username/email/phone and password are required.")

        user = None

        # ── 1. Try direct username authenticate ──────────────────────────
        user = authenticate(username=identifier, password=password)

        # ── 2. Try email lookup ───────────────────────────────────────────
        if not user:
            try:
                user_obj = User.objects.get(email=identifier.lower())
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass

        # ── 3. Try phone lookup ───────────────────────────────────────────
        if not user:
            try:
                phone_digits = ''.join(filter(str.isdigit, identifier))
                if phone_digits:
                    user_obj = User.objects.get(phone=phone_digits)
                    user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
            except User.MultipleObjectsReturned:
                # Multiple users with same phone — fall back to first active one
                user_obj = User.objects.filter(phone=identifier).first()
                if user_obj:
                    user = authenticate(username=user_obj.username, password=password)

        # ── Auth failed ───────────────────────────────────────────────────
        if not user:
            raise serializers.ValidationError("Invalid username/email/phone or password.")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        # ── SUPERADMIN BLOCK — serializer level pe bhi rok do ──────────────
        if user.role == "superadmin" or user.user_type == "superadmin":
            raise serializers.ValidationError("Invalid username/email/phone or password.")

        # ── Role check ────────────────────────────────────────────────────
        if not user.is_customer():
            if user.is_branch():
                data['user'] = user
                data['branch_activation_required'] = True
                return data
            raise serializers.ValidationError("Only customers can login here.")

        data['user'] = user
        return data


# ─────────────────────────────────────────────────────────────────────────────
class CustomerProfileSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ['id', 'username', 'email', 'role', 'phone', 'profile']

    def get_profile(self, obj):
        try:
            profile = obj.customer_profile
            return {
                'full_name': profile.full_name,
                'address':   profile.address,
                'city':      profile.city,
                'state':     profile.state,
                'created_at': profile.created_at,
            }
        except CustomerProfile.DoesNotExist:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD RESET SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, trim_whitespace=True)

    def validate_email(self, value):
        value = value.strip().lower()
        # ✅ covers all customer-capable roles including branch variants
        if not User.objects.filter(email=value, role__in=CUSTOMER_ROLES).exists():
            raise serializers.ValidationError("No customer account found with this email.")
        return value

    def save(self):
        email = self.validated_data['email']
        user  = User.objects.get(email=email, role__in=CUSTOMER_ROLES)

        token     = default_token_generator.make_token(user)
        uid       = urlsafe_base64_encode(force_bytes(user.pk))
        reset_link= f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"

        subject = "Password Reset Request - Ecommerce Store"
        message = f"""Hello {user.username},

You have requested to reset your password for your Ecommerce Store account.

Click the link below to reset your password:
{reset_link}

This link will expire in 24 hours.

If you didn't request this password reset, please ignore this email.

Best regards,
Ecommerce Store Team
"""
        html_message = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .button {{ display: inline-block; background: #2563eb; color: white;
                   padding: 12px 24px; text-decoration: none; border-radius: 4px;
                   font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Password Reset Request</h2>
        <p>Hello {user.username},</p>
        <p>Click the button below to reset your password:</p>
        <p><a href="{reset_link}" class="button">Reset Password</a></p>
        <p>Or copy this link: <code>{reset_link}</code></p>
        <p><strong>This link expires in 24 hours.</strong></p>
        <p>If you didn't request this, please ignore this email.</p>
    </div>
</body>
</html>"""

        try:
            send_mail(
                subject      = subject,
                message      = message,
                from_email   = settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message = html_message,
                fail_silently= False,
            )
        except Exception as e:
            print(f"Email error: {e}")

        return {'user': user, 'uid': uid, 'token': token}


# ─────────────────────────────────────────────────────────────────────────────
class ResetPasswordSerializer(serializers.Serializer):
    uid              = serializers.CharField(required=True)
    token            = serializers.CharField(required=True)
    new_password     = serializers.CharField(
        required=True, write_only=True,
        style={'input_type': 'password'}, min_length=8, max_length=128
    )
    confirm_password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'}
    )

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})

        try:
            uid  = force_str(urlsafe_base64_decode(data['uid']))
            # ✅ covers all customer-capable roles
            user = User.objects.get(pk=uid, role__in=CUSTOMER_ROLES)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": ["Invalid reset link."]})

        if not default_token_generator.check_token(user, data['token']):
            raise serializers.ValidationError({"token": ["Reset link has expired or is invalid."]})

        data['user'] = user
        return data

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()

        try:
            from rest_framework.authtoken.models import Token
            Token.objects.filter(user=user).delete()
        except Exception:
            pass

        try:
            send_mail(
                subject        = "Password Changed Successfully",
                message        = f"Hello {user.username},\n\nYour password has been changed successfully.",
                from_email     = settings.DEFAULT_FROM_EMAIL,
                recipient_list = [user.email],
                fail_silently  = True,
            )
        except Exception:
            pass

        return user


# ─────────────────────────────────────────────────────────────────────────────
class VerifyResetTokenSerializer(serializers.Serializer):
    uid   = serializers.CharField(required=True)
    token = serializers.CharField(required=True)

    def validate(self, data):
        try:
            uid  = force_str(urlsafe_base64_decode(data['uid']))
            # ✅ covers all customer-capable roles
            user = User.objects.get(pk=uid, role__in=CUSTOMER_ROLES)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": ["Invalid reset link."]})

        if not default_token_generator.check_token(user, data['token']):
            raise serializers.ValidationError({"token": ["Reset link has expired or is invalid."]})

        data['user'] = user
        return data


# ─────────────────────────────────────────────────────────────────────────────
class ChangePasswordSerializer(serializers.Serializer):
    old_password     = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'}
    )
    new_password     = serializers.CharField(
        required=True, write_only=True,
        style={'input_type': 'password'}, min_length=8, max_length=128
    )
    confirm_password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'}
    )

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, data):
        if data['new_password'] == data['old_password']:
            raise serializers.ValidationError({"new_password": ["New password must be different from current password."]})
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": ["Passwords do not match."]})
        return data

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()

        try:
            from rest_framework.authtoken.models import Token
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
            return token.key
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
class CompleteCustomerProfileSerializer(serializers.ModelSerializer):
    """Complete profile serializer with orders and agent status"""
    username   = serializers.CharField(source='user.username', read_only=True)
    user_id    = serializers.IntegerField(source='user.id',   read_only=True)
    recent_orders      = serializers.SerializerMethodField()
    orders_count       = serializers.IntegerField(source='total_orders', read_only=True)
    points_value       = serializers.SerializerMethodField()
    agent_profile      = serializers.SerializerMethodField()
    can_apply_for_agent= serializers.SerializerMethodField()

    class Meta:
        model  = CustomerProfile
        fields = [
            'user_id', 'username', 'full_name', 'email', 'phone',
            'address', 'city', 'state',
            'total_orders', 'total_spent', 'loyalty_points',
            'created_at', 'updated_at',
            'is_eligible_for_agent', 'eligible_for_agent_since',
            'recent_orders', 'orders_count', 'points_value',
            'agent_profile', 'can_apply_for_agent',
        ]

    def get_points_value(self, obj):
        return obj.available_points_value

    def get_recent_orders(self, obj):
        from ecommerce.models.order import Order
        try:
            orders = Order.objects.filter(customer=obj.user).order_by('-created_at')[:5]
            return [
                {
                    'id':           order.id,
                    'order_number': getattr(order, 'order_number', f"ORD-{order.id}"),
                    'total_amount': float(order.total_amount) if hasattr(order, 'total_amount') else 0,
                    'status':       getattr(order, 'status', 'pending'),
                    'created_at':   order.created_at.isoformat(),
                    'items_count':  order.items.count() if hasattr(order, 'items') else 0,
                }
                for order in orders
            ]
        except Exception as e:
            print(f"Error fetching recent orders: {e}")
            return []

    def get_agent_profile(self, obj):
        try:
            from mlm.models.agent import Agent
            agent = Agent.objects.get(user=obj.user)
            return {
                'id':                agent.id,
                'agent_type':        agent.agent_type,
                'status':            agent.status,
                'full_name':         agent.full_name,
                'contact_number':    agent.contact_number,
                'total_sales':       float(agent.total_sales) if agent.total_sales else 0,
                'is_active':         agent.is_active_agent,
                'created_at':        agent.created_at.isoformat(),
                'has_passport_photo': bool(agent.passport_photo),
                'has_id_proof':       bool(agent.id_proof),
            }
        except Exception:
            return None

    def get_can_apply_for_agent(self, obj):
        try:
            from mlm.models.agent import Agent
            if Agent.objects.filter(user=obj.user).exists():
                return False
            return obj.is_eligible_for_agent
        except Exception:
            return obj.is_eligible_for_agent
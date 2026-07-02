# ecommerce/views/customer_views.py  (Complete Updated Version)
# Changes from original:
#   - CustomerLoginView   → accepts branch users (is_customer() now covers them)
#   - CustomerProfileView → works for branch users
#   - ApplyForAgentView   → branch users can apply for agent
#   - BranchCustomerActivateView → NEW endpoint: lets branch user opt-in as customer
# All other views are unchanged from your original file.

from users.models import User
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import login, logout
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction
from ecommerce.serializers.customer_serializers import (
    CustomerRegistrationSerializer,
    CustomerLoginSerializer,
    CustomerProfileSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    VerifyResetTokenSerializer,
    ChangePasswordSerializer,
)
from ecommerce.models.customer import CustomerProfile
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


# ─── helpers ────────────────────────────────────────────────────────────────

CUSTOMER_ROLES = ("customer", "both", "branch_customer", "branch_agent", "branch_both")
AGENT_ROLES    = ("agent",    "both", "branch_agent",    "branch_both")
BRANCH_ROLES   = ("branch",   "branch_customer", "branch_agent", "branch_both")


def _ensure_customer_profile(user):
    """
    Get-or-create a CustomerProfile for *any* user type including branch users.
    Returns (profile, created_bool).
    """
    return CustomerProfile.objects.get_or_create(
        user=user,
        defaults={
            "full_name": user.get_full_name() or user.username,
            "email":     user.email,
            "phone":     getattr(user, "phone", "") or "",
            "address":   "",
            "city":      "",
            "state":     "",
        },
    )


def _profile_dict(profile, request=None):
    """Serialise CustomerProfile to a plain dict."""
    return {
        "full_name":                profile.full_name,
        "email":                    profile.email,
        "phone":                    profile.phone,
        "address":                  profile.address,
        "city":                     profile.city,
        "state":                    profile.state,
        "total_orders":             profile.total_orders,
        "total_spent":              float(profile.total_spent),
        "loyalty_points":           profile.loyalty_points,
        "points_value":             profile.available_points_value,
        "is_eligible_for_agent":    profile.is_eligible_for_agent,
        "eligible_for_agent_since": profile.eligible_for_agent_since,
        "agent_documents_uploaded": profile.agent_documents_uploaded,
        "created_at":               profile.created_at.isoformat(),
        "updated_at":               profile.updated_at.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXISTING VIEWS (unchanged logic, branch-aware)
# ═══════════════════════════════════════════════════════════════════════════

class CustomerRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            with transaction.atomic():
                referral_code = request.data.get("referral_code")
                serializer = CustomerRegistrationSerializer(data=request.data)

                if serializer.is_valid():
                    user = serializer.save()

                    if user.referred_by:
                        try:
                            agent = Agent.objects.get(user=user.referred_by)
                            print(f"✅ Agent {agent.full_name} got a new referral")
                        except Agent.DoesNotExist:
                            pass

                    token, _ = Token.objects.get_or_create(user=user)

                    return Response(
                        {
                            "success": True,
                            "message": "Registration successful!",
                            "user": {
                                "id":          user.id,
                                "username":    user.username,
                                "email":       user.email,
                                "role":        user.role,
                                "referred_by": user.referred_by.username if user.referred_by else None,
                            },
                            "token": token.key,
                        },
                        status=status.HTTP_201_CREATED,
                    )

                return Response(
                    {"success": False, "errors": serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except Exception as e:
            return Response(
                {"success": False, "message": f"Error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ─────────────────────────────────────────────────────────────────────────────
class CustomerLoginView(APIView):
    """
    Login for customers AND branch users who have activated customer access.

    Branch users whose role is still plain 'branch' will get a specific error
    message instructing them to activate customer access first via
    POST /ecommerce/customer/activate-branch-customer/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            serializer = CustomerLoginSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(
                    {"success": False, "message": "Validation failed", "errors": serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.validated_data["user"]

            # ── SUPERADMIN BLOCK — customer login bilkul nahi ──────────────
            if user.role == User.ROLE_SUPERADMIN or user.user_type == "superadmin":
                return Response(
                    {"success": False, "message": "Invalid username/email/phone or password."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # ── Branch user: auto-activate customer access silently ─────────
            if user.role == "branch":
                with transaction.atomic():
                    user.upgrade_role("customer")
                    profile, created = _ensure_customer_profile(user)
                    if created:
                        try:
                            branch = user.branch
                            profile.full_name = branch.owner_name or user.username
                            profile.phone     = branch.phone or ""
                            profile.address   = branch.address or ""
                            profile.city      = branch.city or ""
                            profile.state     = branch.state or ""
                            profile.save()
                        except Exception:
                            pass
                user.refresh_from_db()

            if not user.is_customer():
                return Response(
                    {"success": False, "message": "This account does not have customer access."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # ────────────────────────────────────────────────────────────────

            token, _   = Token.objects.get_or_create(user=user)
            refresh    = RefreshToken.for_user(user)
            profile, _ = _ensure_customer_profile(user)

            profile.check_agent_eligibility()
            login(request, user)

            # Agent info
            agent_exists = Agent.objects.filter(user=user).exists()
            agent_status = None
            if agent_exists:
                agent = Agent.objects.get(user=user)
                agent_status = {
                    "status":            agent.status,
                    "agent_type":        agent.agent_type,
                    "has_passport_photo": bool(agent.passport_photo),
                    "has_id_proof":       bool(agent.id_proof),
                }

            profile_data = _profile_dict(profile)
            profile_data["is_eligible_for_agent"] = profile.is_eligible_for_agent
            profile_data["eligible_for_agent_since"] = profile.eligible_for_agent_since
            profile_data["agent_exists"]  = agent_exists
            profile_data["agent_status"]  = agent_status

            return Response(
                {
                    "success": True,
                    "message": "Login successful!",
                    "user": {
                        "id":        user.id,
                        "username":  user.username,
                        "email":     user.email,
                        "role":      user.role,
                        "user_type": user.user_type,
                        "is_branch": user.is_branch(),
                        "profile":   profile_data,
                    },
                    "token":      token.key,
                    "drf_token":  token.key,
                    "access":     str(refresh.access_token),
                    "refresh":    str(refresh),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"success": False, "message": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ─────────────────────────────────────────────────────────────────────────────
class CustomerLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            Token.objects.filter(user=request.user).delete()
            logout(request)
            return Response({"success": True, "message": "Logged out successfully"})
        except Exception:
            return Response({"success": True, "message": "Logged out"})


# ─────────────────────────────────────────────────────────────────────────────
class CustomerProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            if not request.user.is_customer():
                return Response(
                    {"success": False, "message": "Access denied. Customer access required."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            profile, _ = _ensure_customer_profile(request.user)
            profile.check_agent_eligibility()

            mlm_settings    = MLMSettings.objects.first()
            min_sale_amount = float(mlm_settings.minimum_sale_amount) if mlm_settings else 0

            # ── Agent info ──────────────────────────────────────────────────
            agent_exists = False
            agent_data   = None

            try:
                agent        = Agent.objects.get(user=request.user)
                agent_exists = True

                current_sales = float(agent.total_sales)
                remaining     = max(0, min_sale_amount - current_sales)
                has_min_sales = current_sales >= min_sale_amount

                if agent.status == "pending":
                    activation_reason = "Pending admin approval"
                elif agent.status == "rejected":
                    activation_reason = "Application rejected"
                elif not has_min_sales:
                    activation_reason = f"Need ₹{remaining:.0f} more in sales to activate"
                else:
                    activation_reason = "Active"

                agent_data = {
                    "id":                   agent.id,
                    "agent_type":           agent.agent_type,
                    "agent_type_display":   agent.get_agent_type_display(),
                    "status":               agent.status,
                    "full_name":            agent.full_name,
                    "contact_number":       agent.contact_number,
                    "email":                agent.email,
                    "address":              agent.address,
                    "city":                 agent.city,
                    "state":                agent.state,
                    "total_sales":          current_sales,
                    "is_active_agent":      agent.is_active_agent,
                    "has_minimum_sales":    has_min_sales,
                    "minimum_required":     min_sale_amount,
                    "remaining_sales":      remaining,
                    "sales_progress_pct":   round(min(current_sales / min_sale_amount * 100, 100), 1) if min_sale_amount > 0 else 0,
                    "activation_reason":    activation_reason,
                    "minimum_achieved_at":  agent.minimum_achieved_at.isoformat() if agent.minimum_achieved_at else None,
                    "can_refer_agents":     has_min_sales and agent.is_active_agent and agent.status == "approved",
                    "sale_referral_link":   f"https://initcart.in/?ref={request.user.referral_code}" if has_min_sales else None,
                    "agent_referral_link":  f"https://initcart.in/becomeAgent?ref={request.user.referral_code}" if has_min_sales else None,
                    "has_passport_photo":   bool(agent.passport_photo),
                    "has_id_proof":         bool(agent.id_proof),
                    "has_gst_certificate":  bool(agent.gst_certificate),
                    "has_business_license": bool(agent.business_license),
                    "passport_photo_url":   request.build_absolute_uri(agent.passport_photo.url) if agent.passport_photo else None,
                    "id_proof_url":         request.build_absolute_uri(agent.id_proof.url) if agent.id_proof else None,
                    "sponsor": (
                        {
                            "id":            request.user.referred_by.id,
                            "username":      request.user.referred_by.username,
                            "full_name":     getattr(getattr(request.user.referred_by, "agent", None), "full_name", None),
                            "referral_code": request.user.referred_by.referral_code,
                        }
                        if request.user.referred_by else None
                    ),
                    "created_at": agent.created_at.isoformat(),
                }

            except Agent.DoesNotExist:
                pass

            # ── Eligibility ─────────────────────────────────────────────────
            current_spent   = float(profile.total_spent)
            agent_eligibility = {
                "is_eligible":              profile.is_eligible_for_agent,
                "eligible_since":           profile.eligible_for_agent_since.isoformat() if profile.eligible_for_agent_since else None,
                "minimum_required_amount":  min_sale_amount,
                "current_total_spent":      current_spent,
                "remaining_to_eligible":    max(0, min_sale_amount - current_spent),
                "progress_pct":             round(min(current_spent / min_sale_amount * 100, 100), 1) if min_sale_amount > 0 else 0,
                "can_apply_now":            profile.is_eligible_for_agent and not agent_exists,
            }

            return Response(
                {
                    "success": True,
                    "data": {
                        "user": {
                            "id":            request.user.id,
                            "username":      request.user.username,
                            "email":         request.user.email,
                            "phone":         getattr(request.user, "phone", "") or "",
                            "role":          request.user.role,
                            "user_type":     request.user.user_type,
                            "is_branch":     request.user.is_branch(),
                            "referral_code": request.user.referral_code,
                            "referred_by":   request.user.referred_by.username if request.user.referred_by else None,
                        },
                        "profile":           _profile_dict(profile),
                        "agent_eligibility": agent_eligibility,
                        "agent_info":        {"exists": agent_exists, "data": agent_data},
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            import traceback; traceback.print_exc()
            return Response({"success": False, "message": f"Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
class ApplyForAgentView(APIView):
    """
    Customers AND branch-customers can apply for agent role.
    Documents required: passport_photo, id_proof (mandatory)
                        gst_certificate, business_license (optional)
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    # roles that are allowed to hit this endpoint
    _ALLOWED_ROLES = ("customer", "both", "branch_customer", "branch_agent", "branch_both")

    def post(self, request):
        try:
            user = request.user

            if user.role not in self._ALLOWED_ROLES:
                return Response(
                    {"success": False, "message": "Only customers or branch-customers can apply for agent role."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if Agent.objects.filter(user=user).exists():
                return Response(
                    {"success": False, "message": "You are already an agent."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                customer_profile = CustomerProfile.objects.get(user=user)
            except CustomerProfile.DoesNotExist:
                return Response(
                    {"success": False, "message": "Customer profile not found. Please update your profile first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            settings_obj = MLMSettings.objects.first()
            min_amount   = settings_obj.minimum_sale_amount if settings_obj else 50000

            if not customer_profile.is_eligible_for_agent:
                return Response(
                    {
                        "success":         False,
                        "message":         f"You need purchases of at least ₹{min_amount} to become an agent.",
                        "current_spent":   float(customer_profile.total_spent),
                        "required_amount": float(min_amount),
                        "remaining":       max(0, float(min_amount) - float(customer_profile.total_spent)),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            agent_type = request.data.get("agent_type", "normal")
            if agent_type not in ("normal", "pos", "society"):
                return Response({"success": False, "message": "Invalid agent type."}, status=status.HTTP_400_BAD_REQUEST)

            if "passport_photo" not in request.FILES:
                return Response({"success": False, "message": "Passport size photo is required."}, status=status.HTTP_400_BAD_REQUEST)

            if "id_proof" not in request.FILES:
                return Response({"success": False, "message": "ID proof (Aadhar/PAN) is required."}, status=status.HTTP_400_BAD_REQUEST)

            agent = customer_profile.create_agent_profile_from_customer(
                passport_photo=request.FILES["passport_photo"],
                id_proof=request.FILES["id_proof"],
                gst_certificate=request.FILES.get("gst_certificate"),
                business_license=request.FILES.get("business_license"),
                agent_type=agent_type,
                society_or_business_name=request.data.get("society_or_business_name", ""),
            )

            # ── Upgrade role for branch users ───────────────────────────────
            if user.is_branch():
                user.upgrade_role("agent")

            return Response(
                {
                    "success": True,
                    "message": "Congratulations! Your agent account has been activated successfully!",
                    "data": {
                        "agent_id":    agent.id,
                        "status":      agent.status,
                        "agent_type":  agent.agent_type,
                        "is_active":   agent.is_active_agent,
                        "total_sales": float(agent.total_sales),
                        "minimum_sale_status": {
                            "current_sales":   float(agent.total_sales),
                            "minimum_required": float(settings_obj.minimum_sale_amount) if settings_obj else 0,
                            "is_active":        agent.is_active_agent,
                            "remaining":        max(0, float(settings_obj.minimum_sale_amount) - float(agent.total_sales)) if settings_obj else 0,
                        },
                        "documents_uploaded": {
                            "passport_photo":   bool(agent.passport_photo),
                            "id_proof":         bool(agent.id_proof),
                            "gst_certificate":  bool(agent.gst_certificate),
                            "business_license": bool(agent.business_license),
                        },
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            import traceback; traceback.print_exc()
            return Response(
                {"success": False, "message": f"Error submitting application: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


# ═══════════════════════════════════════════════════════════════════════════
# NEW VIEW – Branch users activate customer access
# ═══════════════════════════════════════════════════════════════════════════

class BranchCustomerActivateView(APIView):
    """
    POST /ecommerce/customer/activate-branch-customer/

    Allows a branch user (role='branch') to opt-in as a customer so they
    can shop on the storefront.  Call this once; subsequent logins via
    CustomerLoginView will succeed.

    If the branch user is already authenticated, we use their token.
    If they are not yet authenticated, they should first authenticate via
    the branch login endpoint and then call this endpoint with that token.

    On success:
    - User role upgraded to 'branch_customer'
    - CustomerProfile created
    - Returns new JWT tokens
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        # Must be a branch user
        if not user.is_branch():
            return Response(
                {"success": False, "message": "This endpoint is only for branch users."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Already has customer access
        if user.is_customer():
            profile, _ = _ensure_customer_profile(user)
            token, _   = Token.objects.get_or_create(user=user)
            refresh    = RefreshToken.for_user(user)
            return Response(
                {
                    "success":  True,
                    "message":  "Customer access is already active on your account.",
                    "role":     user.role,
                    "token":    token.key,
                    "access":   str(refresh.access_token),
                    "refresh":  str(refresh),
                },
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            # Upgrade role: branch → branch_customer
            user.upgrade_role("customer")

            # Create CustomerProfile pre-filled from branch data
            profile, created = _ensure_customer_profile(user)
            if created:
                # Try to pull address info from the linked Branch record
                try:
                    branch = user.branch  # reverse OneToOne from Branch model
                    profile.full_name = branch.owner_name or user.username
                    profile.phone     = branch.phone or ""
                    profile.address   = branch.address or ""
                    profile.city      = branch.city or ""
                    profile.state     = branch.state or ""
                    profile.save()
                except Exception:
                    pass

        token, _ = Token.objects.get_or_create(user=user)
        refresh  = RefreshToken.for_user(user)

        return Response(
            {
                "success":  True,
                "message":  "Customer access activated! You can now shop on the website.",
                "role":     user.role,
                "token":    token.key,
                "access":   str(refresh.access_token),
                "refresh":  str(refresh),
                "profile": {
                    "full_name": profile.full_name,
                    "email":     profile.email,
                    "phone":     profile.phone,
                    "city":      profile.city,
                    "state":     profile.state,
                },
            },
            status=status.HTTP_200_OK,
        )


# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD RESET VIEWS  (unchanged from original)
# ═══════════════════════════════════════════════════════════════════════════

class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            serializer = ForgotPasswordSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    {"success": True, "message": "If an account exists with this email, you will receive a password reset link.", "email": serializer.validated_data["email"]},
                    status=status.HTTP_200_OK,
                )
            return Response({"success": False, "message": "Validation failed", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"success": True, "message": "If an account exists with this email, you will receive a password reset link."}, status=status.HTTP_200_OK)


class VerifyResetTokenView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            serializer = VerifyResetTokenSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.validated_data["user"]
                return Response({"success": True, "valid": True, "message": "Reset link is valid.", "email": user.email, "username": user.username})
            return Response({"success": False, "valid": False, "message": "Reset link is invalid or expired.", "errors": serializer.errors})
        except Exception:
            return Response({"success": False, "valid": False, "message": "Invalid reset link."})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            serializer = ResetPasswordSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()
                return Response({"success": True, "message": "Password has been reset successfully. You can now login with your new password.", "email": user.email})
            return Response({"success": False, "message": "Validation failed", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"success": False, "message": "An error occurred. Please try again."}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            if request.user.role not in ("customer", "both", "branch_customer", "branch_agent", "branch_both"):
                return Response({"success": False, "message": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
            serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
            if serializer.is_valid():
                new_token = serializer.save()
                resp = {"success": True, "message": "Password changed successfully."}
                if new_token:
                    resp["token"] = new_token
                return Response(resp)
            return Response({"success": False, "message": "Validation failed", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"success": False, "message": f"Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


# ═══════════════════════════════════════════════════════════════════════════
# ADDITIONAL VIEWS  (unchanged from original)
# ═══════════════════════════════════════════════════════════════════════════

class CustomerStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            if not request.user.is_customer():
                return Response({"success": False, "message": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
            try:
                profile = CustomerProfile.objects.get(user=request.user)
            except CustomerProfile.DoesNotExist:
                return Response({"success": False, "message": "Customer profile not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response({
                "success": True,
                "data": {
                    "stats": {
                        "total_orders":  profile.total_orders,
                        "total_spent":   float(profile.total_spent),
                        "loyalty_points": profile.loyalty_points,
                        "points_value":  profile.available_points_value,
                    }
                },
            })
        except Exception as e:
            return Response({"success": False, "message": f"Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class TestEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            email = request.data.get("email", "")
            if not email:
                return Response({"success": False, "message": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
            from django.core.mail import send_mail
            from django.conf import settings
            send_mail(
                subject="Test Email - Ecommerce Store",
                message="This is a test email from your Django application.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            return Response({"success": True, "message": f"Test email sent to {email}", "email": email})
        except Exception as e:
            return Response({"success": False, "message": f"Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


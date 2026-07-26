from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from django.core.cache import cache
from .models import User
from django.contrib.auth.hashers import make_password  # already check_password hai, make_password add karo
from django.db.models import Q


def handler429(request, exception):
    return JsonResponse(
        {"error": "Too many login attempts. Please wait 5 minutes."},
        status=429
    )


class LoginView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Duplicate email case handle karo — superadmin wala skip karo
        try:
            user_obj = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except User.MultipleObjectsReturned:
            # Agar duplicate hain — superadmin ko skip karke pehla lo
            user_obj = User.objects.filter(
                email=email
            ).exclude(role="superadmin").first()
            if not user_obj:
                return Response(
                    {"error": "Invalid email or password"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        user = authenticate(username=user_obj.username, password=password)

        if not user:
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access":   str(refresh.access_token),
                "refresh":  str(refresh),
                "email":    user.email,
                "role":     user.role,
                "username": user.username,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(
            {"message": "Logged out successfully"},
            status=status.HTTP_200_OK,
        )


class SuperAdminLoginView(APIView):
    permission_classes = []

    def post(self, request):
        email    = request.data.get("email", "").strip().lower()
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Rate limit check ─────────────────────────────────────────────
        cache_key = f"sa_login_attempts_{email}"
        attempts  = cache.get(cache_key, 0)

        if attempts >= 5:
            return Response(
                {"error": "Too many failed attempts. Please wait 5 minutes."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # ── Superadmin user fetch — duplicate safe ───────────────────────
        # get() ki jagah filter().first() — duplicate hone pe bhi crash nahi karega
        user_obj = User.objects.filter(
            email=email,
            role=User.ROLE_SUPERADMIN,
            user_type="superadmin"
        ).first()

        if not user_obj:
            cache.set(cache_key, attempts + 1, timeout=300)
            return Response(
                {"error": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ── Password check ───────────────────────────────────────────────
        user = authenticate(username=user_obj.username, password=password)
        if not user:
            cache.set(cache_key, attempts + 1, timeout=300)
            remaining = max(0, 4 - attempts)
            return Response(
                {"error": f"Invalid email or password. {remaining} attempts remaining."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ── Success — attempts reset ──────────────────────────────────────
        cache.delete(cache_key)

        refresh = RefreshToken.for_user(user)
        return Response({
            "message": "Super Admin login successful",
            "access":   str(refresh.access_token),
            "refresh":  str(refresh),
            "email":    user.email,
            "role":     user.role,
            "username": user.username,
        })


class AgentReferralLinkAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != "agent":
            return Response({"error": "Only agents have referral links"})

        referral_link = f"https://initcart.in/register?ref={user.referral_code}"

        return Response({
            "referral_code": user.referral_code,
            "referral_link": referral_link
        })
        
        
class SuperAdminChangeCredentialsView(APIView):
    """
    Superadmin panel ka email/password badalne ke liye.
    Sirf User model (superadmin panel login) affect hota hai —
    Branch.password (branch panel login) is se bilkul untouched rehta hai.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        user = request.user

        if getattr(user, "role", None) != "superadmin":
            return Response(
                {"success": False, "message": "Only Super Admin can perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        current_password = (request.data.get("current_password") or "").strip()
        new_password = (request.data.get("new_password") or "").strip()
        new_email = (request.data.get("new_email") or "").strip().lower()

        if not current_password:
            return Response(
                {"success": False, "message": "Current password is required."},
                status=400,
            )

        if not user.check_password(current_password):
            return Response(
                {"success": False, "message": "Current password is incorrect."},
                status=400,
            )

        updated = False

        if new_email and new_email != user.email:
            if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                return Response(
                    {"success": False, "message": "This email is already in use."},
                    status=400,
                )
            user.email = new_email
            user.username = new_email  # login username bhi sync rakho
            updated = True

        if new_password:
            if len(new_password) < 6:
                return Response(
                    {"success": False, "message": "New password must be at least 6 characters."},
                    status=400,
                )
            user.set_password(new_password)
            updated = True

        if not updated:
            return Response({"success": False, "message": "Nothing to update."}, status=400)

        user.save()

        return Response({
            "success": True,
            "message": "Super Admin login credentials updated successfully.",
            "email": user.email,
        })        
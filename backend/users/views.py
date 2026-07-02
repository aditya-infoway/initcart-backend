from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from django.core.cache import cache
from .models import User


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
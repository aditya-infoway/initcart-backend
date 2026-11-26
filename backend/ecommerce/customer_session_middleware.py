from django.http import JsonResponse
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings


class CustomerSessionMiddleware:
    """
    Sirf CUSTOMER login se bane JWT (claim client="customer") par check:
      - account deleted                          -> 401 code=account_deleted
      - session_version mismatch (logout/delete) -> 401 code=session_expired
    Baaki sab tokens -> seedha aage.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        parts = request.META.get("HTTP_AUTHORIZATION", "").split()

        if len(parts) == 2 and parts[0].lower() == "bearer":
            try:
                token = AccessToken(parts[1])
            except TokenError:
                token = None

            if token is not None and token.get("client") == "customer":
                from ecommerce.models.customer import CustomerProfile

                p = CustomerProfile.objects.filter(
                    user_id=token.get(api_settings.USER_ID_CLAIM)
                ).values("is_deleted", "session_version").first()

                if p:
                    if p["is_deleted"]:
                        return JsonResponse(
                            {"success": False, "message": "This account has been deleted.",
                             "code": "account_deleted"}, status=401)
                    if token.get("cv") != p["session_version"]:
                        return JsonResponse(
                            {"success": False, "message": "Session expired. Please login again.",
                             "code": "session_expired"}, status=401)

        return self.get_response(request)
from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
from rest_framework.authtoken.models import Token
from ecommerce.models.token_model import CustomerToken


class DualTokenAuthentication(BaseAuthentication):
    """
    Accept both Django Token and CustomerToken
    """
    
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return None
        
        try:
            # Format: "Token <token_key>" or "Bearer <token_key>"
            parts = auth_header.split()
            
            if len(parts) != 2:
                return None
            
            auth_type, token_key = parts
            
            if auth_type.lower() not in ['token', 'bearer']:
                return None
            
            # Try Django Token first
            try:
                django_token = Token.objects.get(key=token_key)
                if django_token.user.is_active:
                    return (django_token.user, django_token)
            except Token.DoesNotExist:
                pass
            
            # Try CustomerToken
            try:
                customer_token = CustomerToken.objects.get(key=token_key)
                if customer_token.is_valid():
                    return (customer_token.user, customer_token)
            except CustomerToken.DoesNotExist:
                pass
            
            # No valid token found
            return None
            
        except (IndexError, ValueError):
            return None
    
    def authenticate_header(self, request):
        """
        Required method for DRF authentication classes
        """
        return 'Token'
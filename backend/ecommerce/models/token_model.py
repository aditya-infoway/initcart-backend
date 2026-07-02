import secrets
from django.db import models
from users.models import User

class CustomerToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_auth_token')
    key = models.CharField(max_length=64, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)
    
    def generate_key(self):
        return secrets.token_hex(32)
    
    def __str__(self):
        return f"Token for {self.user.username}"
    
    @classmethod
    def get_or_create(cls, user):
        token, created = cls.objects.get_or_create(user=user)
        return token, created
    
    @classmethod
    def delete_token(cls, user):
        cls.objects.filter(user=user).delete()
from django.db import models
from django.conf import settings
from datetime import timedelta
from django.utils import timezone

class SubscriptionPlan(models.Model):
    SERVICE_CHOICES = [
        ('salon', 'Salon & Beauty'),
        ('gym', 'Gym & Fitness'),
        ('real_estate', 'Real Estate'),
        ('travel_agency', 'Travel Agency'),
        ('finance', 'Finance & Banking'),
        ('tech', 'Technology Services'),
        ('hospitality', 'Hospitality'),
        ('healthcare', 'Healthcare'),
        ('education', 'Education'),
        ('professional', 'Professional Services'),
        ('work_place', 'Work Place Services'),
        ('all', 'All Services'),
    ]
    
    SUBSCRIPTION_TYPE_CHOICES = [
        ('1 Month', '1 Month'),
        ('3 Months', '3 Months'),
        ('6 Months', '6 Months'),
        ('1 year', '1 Year'),
        ('Free Trial', 'Free Trial'),
    ]
    
    service_type = models.CharField(max_length=50, choices=SERVICE_CHOICES, default='all')
    subscription_type = models.CharField(max_length=50, choices=SUBSCRIPTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['service_type', 'subscription_type']
    
    def __str__(self):
        return f"{self.get_service_type_display()} - {self.get_subscription_type_display()} (₹{self.amount})"



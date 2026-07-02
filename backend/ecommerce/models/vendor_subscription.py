# vendor_subscription.py में save method update करें
from django.db import models
from django.utils import timezone
from datetime import timedelta
from ecommerce.models.subscription import SubscriptionPlan

class VendorSubscription(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE, related_name='subscriptions')
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    start_date = models.DateTimeField(default=timezone.now)  # Default value set
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.vendor.business_name} - {self.subscription_plan.subscription_type}"
    
    def save(self, *args, **kwargs):
        # Calculate end date if not set
        if not self.end_date and self.subscription_plan:
            # Calculate end date based on subscription type
            duration_map = {
                '1 Month': 30,
                '3 Months': 90,
                '6 Months': 180,
                '1 year': 365,
                'Free Trial': 7
            }
            
            days = duration_map.get(self.subscription_plan.subscription_type, 30)
            
            # Ensure start_date is set
            if not self.start_date:
                self.start_date = timezone.now()
            
            self.end_date = self.start_date + timedelta(days=days)
        
        # Check if subscription is still valid
        if self.end_date and self.end_date < timezone.now():
            self.is_active = False
        
        super().save(*args, **kwargs)
# ecommerce/models/loyalty.py - SIMPLIFIED VERSION

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings

class LoyaltyPointsConfig(models.Model):
    POINTS_TYPE = [
        ('percentage', 'Percentage of Purchase'),
        ('fixed', 'Fixed Points per Purchase'),
        ('tiered', 'Tiered (Price Range based)'),
    ]
    
    EARNED_ON = [
        ('all_orders', 'All Orders'),
        ('above_amount', 'Orders Above Amount'),
        ('specific_products', 'Specific Products'),
        ('specific_categories', 'Specific Categories'),
    ]
    
    name = models.CharField(max_length=100, help_text="Rule name e.g., 'Standard Points', 'Festival Bonus'")
    points_type = models.CharField(max_length=20, choices=POINTS_TYPE, default='percentage')
    earned_on = models.CharField(max_length=30, choices=EARNED_ON, default='all_orders')
    
    percentage_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=1.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of order amount to convert to points"
    )
    
    fixed_points = models.IntegerField(
        default=0,
        help_text="Fixed points per purchase"
    )
    
    min_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Minimum order amount for this tier"
    )
    max_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Maximum order amount for this tier (leave blank for unlimited)"
    )
    tier_points = models.IntegerField(
        default=0,
        help_text="Points for this tier"
    )
    
    min_order_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Minimum order amount to earn points"
    )
    max_points_per_order = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Maximum points that can be earned per order"
    )
    
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=1,
        help_text="Higher priority rules will be applied first"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', '-created_at']
        verbose_name = 'Loyalty Points Configuration'
        verbose_name_plural = 'Loyalty Points Configurations'
    
    def __str__(self):
        return f"{self.name} ({self.get_points_type_display()})"
    
    @property
    def is_valid(self):
        from django.utils import timezone
        now = timezone.now()
        
        if not self.is_active:
            return False
        
        if now < self.valid_from:
            return False
        
        if self.valid_to and now > self.valid_to:
            return False
        
        return True
    
    def calculate_points(self, order_amount):
        if not self.is_valid:
            return 0
        
        if order_amount < float(self.min_order_amount):
            return 0
        
        points = 0
        
        if self.points_type == 'percentage':
            points = int((order_amount * float(self.percentage_rate)) / 100)
        
        elif self.points_type == 'fixed':
            points = self.fixed_points
        
        elif self.points_type == 'tiered':
            if order_amount >= float(self.min_amount):
                if self.max_amount is None or order_amount <= float(self.max_amount):
                    points = self.tier_points
        
        if self.max_points_per_order and points > self.max_points_per_order:
            points = self.max_points_per_order
        
        return points


class LoyaltyPointsTransaction(models.Model):
    TRANSACTION_TYPE = [
        ('earned', 'Earned'),
        ('used', 'Used'),
        ('bonus', 'Bonus'),
        ('expired', 'Expired'),
        ('adjusted', 'Adjusted'),
    ]
    
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='loyalty_transactions'
    )
    
    points = models.IntegerField()
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE)
    config = models.ForeignKey(
        'LoyaltyPointsConfig',
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # TEMPORARY: Use integer field instead of foreign key
    order_id = models.PositiveIntegerField(null=True, blank=True)
    order_number = models.CharField(max_length=100, blank=True, null=True)
    
    description = models.TextField()
    balance_after = models.IntegerField(help_text="Points balance after this transaction")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer.username}: {self.points} points ({self.get_transaction_type_display()})"
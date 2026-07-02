# ecommerce/serializers/loyalty_serializers.py
from rest_framework import serializers
from ecommerce.models.loyalty import LoyaltyPointsConfig, LoyaltyPointsTransaction
from ecommerce.models.order import Order
from users.models import User

class LoyaltyPointsConfigSerializer(serializers.ModelSerializer):
    is_valid = serializers.SerializerMethodField()
    remaining_days = serializers.SerializerMethodField()
    
    class Meta:
        model = LoyaltyPointsConfig
        fields = [
            'id', 'name', 'points_type', 'earned_on', 
            'percentage_rate', 'fixed_points',
            'min_amount', 'max_amount', 'tier_points',
            'min_order_amount', 'max_points_per_order',
            'valid_from', 'valid_to', 'is_active', 'priority',
            'is_valid', 'remaining_days', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_is_valid(self, obj):
        return obj.is_valid
    
    def get_remaining_days(self, obj):
        from django.utils import timezone
        if obj.valid_to:
            remaining = obj.valid_to - timezone.now()
            return max(0, remaining.days)
        return None
    
    def validate(self, data):
        # Validate based on points_type
        points_type = data.get('points_type', self.instance.points_type if self.instance else None)
        
        if points_type == 'percentage':
            if data.get('percentage_rate', 0) <= 0:
                raise serializers.ValidationError({
                    'percentage_rate': 'Percentage rate must be greater than 0'
                })
        
        elif points_type == 'fixed':
            if data.get('fixed_points', 0) <= 0:
                raise serializers.ValidationError({
                    'fixed_points': 'Fixed points must be greater than 0'
                })
        
        elif points_type == 'tiered':
            if data.get('tier_points', 0) <= 0:
                raise serializers.ValidationError({
                    'tier_points': 'Tier points must be greater than 0'
                })
            
            min_amount = data.get('min_amount', 0)
            max_amount = data.get('max_amount', None)
            
            if max_amount is not None and max_amount <= min_amount:
                raise serializers.ValidationError({
                    'max_amount': 'Maximum amount must be greater than minimum amount'
                })
        
        # Validate dates
        valid_from = data.get('valid_from')
        valid_to = data.get('valid_to')
        
        if valid_to and valid_from and valid_to < valid_from:
            raise serializers.ValidationError({
                'valid_to': 'Valid to date must be after valid from date'
            })
        
        return data


class LoyaltyPointsTransactionSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.username', read_only=True)
    customer_email = serializers.EmailField(source='customer.email', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True, allow_null=True)
    config_name = serializers.CharField(source='config.name', read_only=True, allow_null=True)
    
    class Meta:
        model = LoyaltyPointsTransaction
        fields = [
            'id', 'customer', 'customer_name', 'customer_email',
            'points', 'transaction_type', 'config', 'config_name',
            'order', 'order_number', 'description', 'balance_after',
            'created_at'
        ]
        read_only_fields = ['balance_after', 'created_at']


class LoyaltyPointsCalculatorSerializer(serializers.Serializer):
    """Serializer for calculating points"""
    order_amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    customer_id = serializers.IntegerField(required=False)
    
    def calculate_points(self):
        """Calculate points based on active rules"""
        from ecommerce.models.loyalty import LoyaltyPointsConfig
        from django.utils import timezone
        
        order_amount = float(self.validated_data['order_amount'])
        customer_id = self.validated_data.get('customer_id')
        
        # Get all active and valid rules
        active_rules = LoyaltyPointsConfig.objects.filter(
            is_active=True,
            valid_from__lte=timezone.now()
        ).exclude(
            valid_to__lt=timezone.now()
        ).order_by('-priority')
        
        total_points = 0
        applicable_rules = []
        
        for rule in active_rules:
            points = rule.calculate_points(order_amount)
            if points > 0:
                total_points += points
                applicable_rules.append({
                    'rule_id': rule.id,
                    'rule_name': rule.name,
                    'points_type': rule.points_type,
                    'points': points
                })
        
        return {
            'order_amount': order_amount,
            'total_points': total_points,
            'applicable_rules': applicable_rules,
            'point_value': round(total_points * 0.1, 2)  # 100 points = ₹10
        }


class LoyaltyPointsReportSerializer(serializers.Serializer):
    """Serializer for loyalty points reports"""
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    customer_id = serializers.IntegerField(required=False)
    transaction_type = serializers.ChoiceField(
        choices=LoyaltyPointsTransaction.TRANSACTION_TYPE,
        required=False
    )
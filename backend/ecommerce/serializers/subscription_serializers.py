from rest_framework import serializers
from decimal import Decimal
from ecommerce.models.subscription import SubscriptionPlan
from ecommerce.models.vendor_subscription import VendorSubscription

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    service_type_display = serializers.CharField(
        source='get_service_type_display',
        read_only=True
    )
    subscription_type_display = serializers.CharField(
        source='get_subscription_type_display',
        read_only=True
    )

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id',
            'service_type',
            'service_type_display',
            'subscription_type',
            'subscription_type_display',
            'amount',
            'description',
            'is_active',
            'created_at',
            'updated_at'
        ]
    
    def to_representation(self, instance):
        """Convert Decimal to float for JSON serialization"""
        representation = super().to_representation(instance)
        
        # Convert Decimal amount to float with 2 decimal precision
        if 'amount' in representation and representation['amount'] is not None:
            if isinstance(representation['amount'], Decimal):
                # Round to 2 decimal places and convert to float
                representation['amount'] = float(Decimal(representation['amount']).quantize(Decimal('0.00')))
            elif isinstance(representation['amount'], str):
                try:
                    # Convert string to Decimal, then to float with rounding
                    dec_amount = Decimal(representation['amount'])
                    representation['amount'] = float(dec_amount.quantize(Decimal('0.00')))
                except (ValueError, TypeError):
                    representation['amount'] = 0.0
        
        return representation
    
    def to_internal_value(self, data):
        """Convert incoming data to proper Decimal"""
        data = data.copy()
        
        # Handle amount conversion
        if 'amount' in data and data['amount'] is not None:
            try:
                # Convert string/float to Decimal with 2 decimal places
                if isinstance(data['amount'], str):
                    data['amount'] = Decimal(data['amount']).quantize(Decimal('0.00'))
                elif isinstance(data['amount'], (int, float)):
                    data['amount'] = Decimal(str(data['amount'])).quantize(Decimal('0.00'))
            except (ValueError, TypeError):
                raise serializers.ValidationError({
                    'amount': 'Enter a valid number.'
                })
        
        return super().to_internal_value(data)
    
    def validate_amount(self, value):
        """Validate amount field"""
        if value < 0:
            raise serializers.ValidationError("Amount cannot be negative.")
        
        # Ensure it has exactly 2 decimal places
        return value.quantize(Decimal('0.00'))


class VendorSubscriptionSerializer(serializers.ModelSerializer):
    subscription_plan = SubscriptionPlanSerializer(read_only=True)
    
    class Meta:
        model = VendorSubscription
        fields = [
            'id',
            'subscription_plan',
            'start_date',
            'end_date',
            'is_active',
            'payment_status',
            'created_at',
            'updated_at'
        ]
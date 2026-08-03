#ecommerce/models/order.py
from django.db import models
from users.models import User
from ecommerce.models.vendor import Vendor
from ecommerce.models.product import Product, ProductStock
from ecommerce.models.customer import CustomerProfile
from django.utils import timezone
from datetime import timedelta
from mlm.models.agent import Agent

class Order(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHODS = [
        ('razorpay', 'Razorpay'),
        ('cod', 'Cash on Delivery'),
    ]
    
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=100, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loyalty_points_used = models.IntegerField(default=0)
    loyalty_points_earned = models.IntegerField(default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    billing_name = models.CharField(max_length=255)
    billing_email = models.EmailField()
    billing_phone = models.CharField(max_length=15)
    billing_address = models.TextField()
    billing_city = models.CharField(max_length=100)
    billing_state = models.CharField(max_length=100)
    billing_pincode = models.CharField(max_length=10)
    
    shipping_name = models.CharField(max_length=255, blank=True, null=True)
    shipping_phone = models.CharField(max_length=15, blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_state = models.CharField(max_length=100, blank=True, null=True)
    shipping_pincode = models.CharField(max_length=10, blank=True, null=True)
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    
    order_status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    commission_distributed_at_checkout = models.BooleanField(default=False)
    commission_distributed_at_delivery = models.BooleanField(default=False)
    mlm_commission_processed = models.BooleanField(default=False)
    commission_distributed = models.BooleanField(default=False)
    checkout_commission_processed = models.BooleanField(default=False)
    delivery_commission_processed = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    referral_agent = models.ForeignKey(
    Agent,
    on_delete=models.SET_NULL,
    null=True,  
    blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["order_status"]),  
            models.Index(fields=["payment_status"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["delivered_at"]), 
        ]
    
    def __str__(self):
        return f"{self.order_number} - {self.customer.email}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            import uuid
            self.order_number = f"ORD{str(uuid.uuid4())[:8].upper()}"
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='order_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    product_stock = models.ForeignKey(ProductStock, on_delete=models.CASCADE, null=True, blank=True)
    final_price = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    default=0
    )
    
    vendor_receivable = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    platform_profit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120)
    color = models.CharField(max_length=120, blank=True, null=True)
    size = models.CharField(max_length=120, blank=True, null=True)
    
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    item_status = models.CharField(max_length=20, choices=Order.ORDER_STATUS, default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.product_name} x {self.quantity} - {self.order.order_number}"


class CustomerAddress(models.Model):
    ADDRESS_TYPE = [
        ('billing', 'Billing'),
        ('shipping', 'Shipping'),
        ('both', 'Both'),
    ]
    
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPE, default='both')
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    address_line1 = models.TextField()
    address_line2 = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default='India')
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Customer Addresses'
        ordering = ['-is_default', '-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.city} ({self.address_type})"
    
    def save(self, *args, **kwargs):
        # If setting as default, unset default for other addresses
        if self.is_default:
            CustomerAddress.objects.filter(
                customer=self.customer, 
                address_type=self.address_type
            ).update(is_default=False)
        super().save(*args, **kwargs)


class Cart(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart')
    product_stock = models.ForeignKey(ProductStock, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['customer', 'product_stock']
    
    def __str__(self):
        return f"{self.customer.email} - {self.product_stock.product.product_name} x {self.quantity}"
    
    @property
    def item_total(self):
        try:
            price = float(self.product_stock.final_price)
            return round(price * self.quantity, 2)
        except:
            return 0


class VendorDeliveryInfo(models.Model):
    """Delivery information for vendor-specific items in an order"""
    
    DELIVERY_SERVICES = [
        ('shipmojo', 'ShipMojo (Recommended)'),
        ('self', 'Self Delivery'),
        ('courier', 'Courier Service'),
    ]
    
    DELIVERY_STATUS = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed to Deliver'),
        ('returned', 'Returned'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='vendor_deliveries')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='delivery_infos')
    
    # Delivery service selection
    delivery_service = models.CharField(max_length=20, choices=DELIVERY_SERVICES, default='self')
    
    # Self delivery fields
    delivery_man_name = models.CharField(max_length=255, blank=True, null=True)
    delivery_man_phone = models.CharField(max_length=15, blank=True, null=True)
    delivery_incentive = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Courier service fields
    courier_name = models.CharField(max_length=255, blank=True, null=True)
    courier_website = models.URLField(blank=True, null=True)
    tracking_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Common fields
    expected_delivery_date = models.DateField(blank=True, null=True)
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS, default='pending')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['order', 'vendor']
        verbose_name = 'Vendor Delivery Information'
        verbose_name_plural = 'Vendor Delivery Information'
    
    def __str__(self):
        return f"{self.vendor.business_name} - {self.order.order_number} - {self.delivery_service}"


class PendingCheckout(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    razorpay_order_id = models.CharField(max_length=255, unique=True)
    referral_code = models.CharField(max_length=50, null=True, blank=True)
    billing_address_id = models.IntegerField(null=True, blank=True)
    shipping_address_id = models.IntegerField(null=True, blank=True)
    use_same_address = models.BooleanField(default=True)
    coupon_code = models.CharField(max_length=50, null=True, blank=True)
    loyalty_points_to_use = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    payment_completed = models.BooleanField(default=False)
    razorpay_payment_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=15)
        super().save(*args, **kwargs)

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

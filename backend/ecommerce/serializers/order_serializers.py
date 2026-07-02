from rest_framework import serializers
from ecommerce.models.order import (
    Order, OrderItem, Cart, CustomerAddress, VendorDeliveryInfo, 
)
from ecommerce.models.coupon import Coupon 
from ecommerce.models.product import Product, ProductStock
from ecommerce.models.vendor import Vendor
from ecommerce.serializers.product_serializers import ProductSerializer, ProductStockSerializer
from ecommerce.serializers.vendor_serializers import VendorDetailSerializer
import razorpay
from django.conf import settings
from ecommerce.models.loyalty import LoyaltyPointsTransaction


# Initialize Razorpay client
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


class CustomerAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = [
            'id', 'address_type', 'full_name', 'phone', 'email',
            'address_line1', 'address_line2', 'city', 'state', 
            'pincode', 'country', 'is_default', 'created_at'
        ]
    
    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['customer'] = request.user
        return super().create(validated_data)


class AdminRecentOrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.username")

    class Meta:
        model = Order
        fields = [
            "order_number",
            "customer_name",
            "order_status",
            "payment_status",
            "final_amount",
            "created_at"
        ]


class CartSerializer(serializers.ModelSerializer):
    product_details = serializers.SerializerMethodField()
    item_total = serializers.SerializerMethodField()
    
    class Meta:
        model = Cart
        fields = ['id', 'product_stock', 'quantity', 'product_details', 'item_total', 'created_at']
    
    def get_product_details(self, obj):
        stock = obj.product_stock
        product = stock.product
        
        return {
            'product_id': product.id,
            'product_name': product.product_name,
            'sku': product.sku,
            'main_image': product.main_image.url if product.main_image else None,
            'thumbnail': product.thumbnail_image.url if product.thumbnail_image else None,
            'vendor_name': product.vendor.business_name,
            'color': stock.color,
            'size': stock.size,
            'unit_price': stock.final_price,
            'max_quantity': stock.maximum_order_quantity,
            'stock_quantity': stock.stock_quantity
        }
    
    def get_item_total(self, obj):
        return obj.item_total
    
    def validate(self, data):
        stock = data.get('product_stock')
        quantity = data.get('quantity', 1)
        
        if stock.stock_quantity < quantity:
            raise serializers.ValidationError(
                f"Only {stock.stock_quantity} items available in stock"
            )
        
        if quantity > stock.maximum_order_quantity:
            raise serializers.ValidationError(
                f"Maximum order quantity is {stock.maximum_order_quantity}"
            )
        
        return data


class CouponSerializer(serializers.ModelSerializer):
    is_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'coupon_type', 'discount_value',
            'min_order_amount', 'max_discount_amount',
            'valid_from', 'valid_to', 'max_usage', 'used_count',
            'is_active', 'is_valid'
        ]
    
    def get_is_valid(self, obj):
        is_valid, message = obj.is_valid()
        return {
            'valid': is_valid,
            'message': message
        }


class LoyaltyPointsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyPointsTransaction
        fields = [
            'id', 'points', 'transaction_type', 'description',
            'order_id', 'order_number', 'config', 'balance_after', 'created_at'
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    product_details = serializers.SerializerMethodField()
    vendor_details = serializers.SerializerMethodField()
    variant_image = serializers.SerializerMethodField() 
    tax = serializers.SerializerMethodField() 
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_stock', 'vendor', 'vendor_details',
            'product_name', 'sku', 'color', 'size', 'quantity',
            'unit_price', 'tax_rate', 'tax_amount', 'discount_amount',
            'total_price', 'item_status', 'product_details', 'created_at',
            'variant_image', 'tax' ,
        ]
    
    def get_tax(self, obj):
        if obj.product_stock:
            return obj.product_stock.tax
        return 0 
    
    def get_variant_image(self, obj):
        if obj.product_stock and obj.product_stock.variant_image:
            return obj.product_stock.variant_image.url
        return None
    
    def get_product_details(self, obj):
        variant_image = None

        # Agar variant product hai to stock se image lo
        if obj.product_stock and obj.product_stock.variant_image:
            variant_image = obj.product_stock.variant_image.url

        main_image = None
        if obj.product.main_image:
            main_image = obj.product.main_image.url

        return {
            'product_name': obj.product_name,
            'main_image': main_image,
            'variant_image': variant_image
        }
    
    def get_vendor_details(self, obj):
        return {
            'business_name': obj.vendor.business_name,
            'vendor_type': obj.vendor.vendor_type
        }


class OrderSerializer(serializers.ModelSerializer):
    items                = OrderItemSerializer(many=True, read_only=True)
    customer_details     = serializers.SerializerMethodField()
    payment_details      = serializers.SerializerMethodField()
    referral_agent_info  = serializers.SerializerMethodField()   # ← NEW
 
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'customer', 'customer_details',
            'total_amount', 'shipping_charge', 'tax_amount',
            'discount_amount', 'loyalty_points_used', 'loyalty_points_earned',
            'final_amount', 'billing_name', 'billing_email', 'billing_phone',
            'billing_address', 'billing_city', 'billing_state', 'billing_pincode',
            'shipping_name', 'shipping_phone', 'shipping_address',
            'shipping_city', 'shipping_state', 'shipping_pincode',
            'payment_method', 'payment_status', 'razorpay_order_id',
            'razorpay_payment_id', 'razorpay_signature', 'order_status',
            'notes', 'items', 'payment_details', 'created_at', 'updated_at',
            'referral_agent_info',       # ← NEW
            'mlm_commission_processed',  # ← NEW
        ]
        read_only_fields = [
            'order_number', 'customer', 'total_amount', 'shipping_charge',
            'tax_amount', 'discount_amount', 'final_amount', 'payment_status',
            'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature',
            'order_status', 'created_at', 'updated_at',
            'referral_agent_info', 'mlm_commission_processed',  # ← NEW
        ]
 
    def get_customer_details(self, obj):
        return {
            'username': obj.customer.username,
            'email':    obj.customer.email,
            'phone':    obj.customer.phone,
        }
 
    def get_payment_details(self, obj):
        if obj.payment_method == 'razorpay' and obj.razorpay_order_id:
            try:
                payment = client.payment.fetch(obj.razorpay_payment_id)
                return {
                    'status': payment['status'],
                    'method': payment['method'],
                    'bank':   payment.get('bank'),
                    'wallet': payment.get('wallet'),
                    'vpa':    payment.get('vpa'),
                    'card_id':payment.get('card_id'),
                }
            except:
                return None
        return None
 
    def get_referral_agent_info(self, obj):   # ← NEW METHOD
        if not obj.referral_agent:
            return None
        agent = obj.referral_agent
        return {
            "id":         agent.id,
            "full_name":  agent.full_name,
            "agent_type": agent.agent_type,
            "username":   agent.user.username,
            "is_active":  agent.is_active_agent,
        }
 
 

class CheckoutSerializer(serializers.Serializer):
    billing_address_id = serializers.IntegerField(required=False, allow_null=True)
    shipping_address_id = serializers.IntegerField(required=False, allow_null=True)
    use_same_address = serializers.BooleanField(default=True)
    
    # Shipping address fields (if not using saved address)
    shipping_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    shipping_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    shipping_address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    shipping_city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    shipping_state = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    shipping_pincode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    payment_method = serializers.ChoiceField(choices=Order.PAYMENT_METHODS)
    coupon_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    loyalty_points_to_use = serializers.IntegerField(min_value=0, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    referral_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate(self, data):
        request = self.context.get('request')
        
        # Validate loyalty points
        loyalty_points_to_use = data.get('loyalty_points_to_use', 0)
        if loyalty_points_to_use > 0:
            try:
                profile = request.user.customer_profile
                if not profile.can_use_points(loyalty_points_to_use):
                    raise serializers.ValidationError(
                        f"You only have {profile.loyalty_points} loyalty points available"
                    )
            except:
                raise serializers.ValidationError("Customer profile not found")
        
        # Validate coupon if provided
        coupon_code = data.get('coupon_code')
        if coupon_code:
            try:
                from ecommerce.models.coupon import Coupon
                coupon = Coupon.objects.get(code=coupon_code.upper(), status='active')
                
                # Check if coupon is valid
                if not coupon.is_valid():
                    raise serializers.ValidationError("Coupon is expired or inactive")
                    
            except Coupon.DoesNotExist:
                raise serializers.ValidationError("Invalid coupon code")
        
        return data


class RazorpayOrderSerializer(serializers.Serializer):
    order_id = serializers.CharField()
    amount = serializers.IntegerField()
    currency = serializers.CharField(default="INR")
    
    def create_razorpay_order(self):
        data = self.validated_data
        try:
            order_data = {
                'amount': data['amount'],
                'currency': data['currency'],
                'payment_capture': 1,  # Auto capture payment
                'notes': {
                    'order_id': data['order_id']
                }
            }
            
            razorpay_order = client.order.create(order_data)
            return razorpay_order
        except Exception as e:
            raise serializers.ValidationError(f"Razorpay error: {str(e)}")
        
        
class CreateRazorpayOrderSerializer(serializers.Serializer):
    billing_address_id = serializers.IntegerField(required=False, allow_null=True)
    shipping_address_id = serializers.IntegerField(required=False, allow_null=True)
    use_same_address = serializers.BooleanField(default=True)

    coupon_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    loyalty_points_to_use = serializers.IntegerField(min_value=0, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    referral_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        request = self.context.get('request')

        loyalty_points_to_use = data.get('loyalty_points_to_use', 0)

        if loyalty_points_to_use > 0:
            profile = request.user.customer_profile
            if profile.loyalty_points_balance < loyalty_points_to_use:
                raise serializers.ValidationError(
                    f"You only have {profile.loyalty_points_balance} loyalty points available"
                )

        return data
class VendorOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for vendor-specific order items"""
    product_details = serializers.SerializerMethodField()
    order_info = serializers.SerializerMethodField()
    customer_info = serializers.SerializerMethodField()
    tax_percentage = serializers.FloatField(source="product_stock.tax", read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'order', 'product', 'product_name', 'sku', 
            'color', 'size', 'quantity', 'unit_price', 'tax_amount',
            'discount_amount', 'total_price', 'item_status',
            'product_details', 'order_info', 'customer_info', 'created_at',
            'tax_percentage'
        ]


    def get_product_details(self, obj):
        """Return product details with variant image support"""
        
        # 👇 IMPORTANT: Check if product_stock exists and has variant_image
        variant_image = None
        if obj.product_stock and obj.product_stock.variant_image:
            # Get the full URL
            if hasattr(obj.product_stock.variant_image, 'url'):
                variant_image = obj.product_stock.variant_image.url
            else:
                variant_image = obj.product_stock.variant_image
        
        # Get main image and thumbnail
        main_image = None
        thumbnail = None
        if obj.product:
            if obj.product.main_image and hasattr(obj.product.main_image, 'url'):
                main_image = obj.product.main_image.url
            if obj.product.thumbnail_image and hasattr(obj.product.thumbnail_image, 'url'):
                thumbnail = obj.product.thumbnail_image.url
        
        # Log for debugging
        print(f"🔍 Product: {obj.product_name}")
        print(f"  - Variant Image: {variant_image}")
        print(f"  - Thumbnail: {thumbnail}")
        print(f"  - Main Image: {main_image}")
        
        return {
            'product_name': obj.product_name,
            'main_image': main_image,
            'thumbnail': thumbnail,
            'variant_image': variant_image,  # Make sure this is included
            'sku': obj.sku,
            'color': obj.color,
            'size': obj.size
        }
    def get_order_info(self, obj):
        return {
            'order_id': obj.order.id,
            'order_number': obj.order.order_number,
            'order_date': obj.order.created_at,
            'payment_method': obj.order.payment_method,
            'payment_status': obj.order.payment_status,
            'total_amount': obj.order.total_amount,
            'shipping_charge': obj.order.shipping_charge,
            'discount_amount': obj.order.discount_amount,
            'final_amount': obj.order.final_amount
        }
    
    def get_customer_info(self, obj):
        return {
            'customer_name': obj.order.billing_name,
            'customer_phone': obj.order.billing_phone,
            'customer_email': obj.order.billing_email,
            'shipping_address': {
                'name': obj.order.shipping_name,
                'phone': obj.order.shipping_phone,
                'address': obj.order.shipping_address,
                'city': obj.order.shipping_city,
                'state': obj.order.shipping_state,
                'pincode': obj.order.shipping_pincode
            },
            'billing_address': {
                'name': obj.order.billing_name,
                'phone': obj.order.billing_phone,
                'address': obj.order.billing_address,
                'city': obj.order.billing_city,
                'state': obj.order.billing_state,
                'pincode': obj.order.billing_pincode
            }
        }
class VendorOrderDetailSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_id",
            "created_at",
            "total_amount",
            "items",
            "billing_address",
            "shipping_address"
        ]

    def get_items(self, obj):
        request = self.context.get("request")

        if not request.user.is_authenticated:
            return []

        vendor = getattr(request.user, "vendor", None)

        if not vendor:
            return []

        items = obj.items.filter(vendor=vendor).select_related(
            "product_stock",
            "product_stock__product"
        )

        return VendorOrderItemSerializer(items, many=True).data

class VendorOrderListSerializer(serializers.ModelSerializer):
    """Simplified serializer for order list view"""
    vendor_items_count = serializers.SerializerMethodField()
    vendor_total = serializers.SerializerMethodField()
    vendor_item_status = serializers.SerializerMethodField()
    store = serializers.SerializerMethodField()
    totalAmount = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'created_at',
            'billing_name', 'billing_phone',
            'payment_method', 'payment_status',
            'order_status', 'vendor_items_count',
            'vendor_total', 'vendor_item_status',
            'store', 'totalAmount'
        ]
    
    def get_store(self, obj):
        """Get store/vendor name for this order"""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            try:
                # ✅ Get the vendor's business name
                vendor = Vendor.objects.get(user=request.user)
                print(f"Store name for vendor: {vendor.business_name}")  # Debug
                return vendor.business_name  # Return actual business name
            except Vendor.DoesNotExist:
                print("Vendor not found for user")  # Debug
                return None
            except Exception as e:
                print(f"Error in get_store: {e}")  # Debug
                return None
        return None
    
    def get_totalAmount(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            try:
                vendor = Vendor.objects.get(user=request.user)
                vendor_items = obj.items.filter(vendor=vendor)
                return sum(float(item.total_price) for item in vendor_items)
            except Vendor.DoesNotExist:
                return 0
        return 0
    
    def get_vendor_items_count(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            try:
                vendor = Vendor.objects.get(user=request.user)
                return obj.items.filter(vendor=vendor).count()
            except Vendor.DoesNotExist:
                return 0
        return 0
    
    def get_vendor_total(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            try:
                vendor = Vendor.objects.get(user=request.user)
                vendor_items = obj.items.filter(vendor=vendor)
                return sum(float(item.total_price) for item in vendor_items)
            except Vendor.DoesNotExist:
                return 0
        return 0
    
    def get_vendor_item_status(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            try:
                vendor = Vendor.objects.get(user=request.user)
                vendor_items = obj.items.filter(vendor=vendor)
                if vendor_items.exists():
                    # Return the status of the first item
                    return vendor_items.first().item_status
            except Vendor.DoesNotExist:
                return None
        return None

class VendorOrderSerializer(serializers.ModelSerializer):
    """Serializer for vendor orders"""

    items = serializers.SerializerMethodField()
    customer_details = serializers.SerializerMethodField()
    order_summary = serializers.SerializerMethodField()
    delivery_info = serializers.SerializerMethodField()
    tax_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'created_at', 'updated_at',
            'customer_details', 'payment_method', 'payment_status',
            'order_status', 'items', 'order_summary', 'delivery_info',
            'notes', 'tax_percentage'
        ]

    # 🔹 vendor ek hi baar nikalega
    def get_vendor(self):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            try:
                return Vendor.objects.get(user=request.user)
            except Vendor.DoesNotExist:
                return None
        return None

    # 🔹 TAX PERCENTAGE
    def get_tax_percentage(self, obj):
        vendor = self.get_vendor()
        if not vendor:
            return 0

        item = obj.items.filter(vendor=vendor).first()

        if item and item.product_stock:
            return float(item.product_stock.tax)

        return 0

    # 🔹 ITEMS
    def get_items(self, obj):
        vendor = self.get_vendor()
        if not vendor:
            return []

        items = obj.items.filter(vendor=vendor)

        return VendorOrderItemSerializer(
            items,
            many=True,
            context=self.context
        ).data

    # 🔹 CUSTOMER DETAILS
    def get_customer_details(self, obj):
        return {
            'name': obj.billing_name,
            'phone': obj.billing_phone,
            'email': obj.billing_email,
            'shipping_address': {
                'name': obj.shipping_name,
                'phone': obj.shipping_phone,
                'address': obj.shipping_address,
                'city': obj.shipping_city,
                'state': obj.shipping_state,
                'pincode': obj.shipping_pincode
            }
        }

    # 🔹 ORDER SUMMARY
    def get_order_summary(self, obj):
        vendor = self.get_vendor()
        if not vendor:
            return {}

        vendor_items = obj.items.filter(vendor=vendor)

        subtotal = sum(float(item.total_price) for item in vendor_items)
        discount = sum(float(item.discount_amount) for item in vendor_items)
        tax = sum(float(item.tax_amount) for item in vendor_items)

        return {
            'vendor_subtotal': round(subtotal, 2),
            'vendor_discount': round(discount, 2),
            'vendor_tax': round(tax, 2),
            'vendor_total': round(subtotal - discount + tax, 2),
            'total_items': vendor_items.count(),
            'total_quantity': sum(item.quantity for item in vendor_items)
        }

    # 🔹 DELIVERY INFO
    def get_delivery_info(self, obj):
        vendor = self.get_vendor()
        if not vendor:
            return None

        try:
            delivery_info = VendorDeliveryInfo.objects.get(
                order=obj,
                vendor=vendor
            )

            return {
                'delivery_service': delivery_info.delivery_service,
                'delivery_man_name': delivery_info.delivery_man_name,
                'delivery_man_phone': delivery_info.delivery_man_phone,
                'delivery_incentive': float(delivery_info.delivery_incentive) if delivery_info.delivery_incentive else None,
                'expected_delivery_date': delivery_info.expected_delivery_date,
                'tracking_id': delivery_info.tracking_id,
                'courier_name': delivery_info.courier_name,
                'courier_website': delivery_info.courier_website,
                'delivery_status': delivery_info.delivery_status,
                'updated_at': delivery_info.updated_at
            }

        except VendorDeliveryInfo.DoesNotExist:
            return None

class VendorOrderStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating item status"""
    order_item_id = serializers.IntegerField(required=False)
    order_id = serializers.IntegerField(required=False)
    item_status = serializers.ChoiceField(choices=Order.ORDER_STATUS)
    
    def validate(self, data):
        if not data.get('order_item_id') and not data.get('order_id'):
            raise serializers.ValidationError("Either order_item_id or order_id is required")
        return data


class VendorDeliveryInfoSerializer(serializers.ModelSerializer):
    """Serializer for vendor delivery information"""
    
    class Meta:
        model = VendorDeliveryInfo
        fields = [
            'id', 'order', 'vendor', 'delivery_service',
            'delivery_man_name', 'delivery_man_phone',
            'delivery_incentive', 'expected_delivery_date',
            'tracking_id', 'courier_name', 'courier_website',
            'delivery_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class VendorOrderStatsSerializer(serializers.Serializer):
    """Serializer for vendor order statistics"""
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    packaging = serializers.IntegerField()
    out_for_delivery = serializers.IntegerField()
    delivered = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    returned = serializers.IntegerField()
    failed_to_deliver = serializers.IntegerField()           
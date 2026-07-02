# ecommerce/views/cart_views.py
from datetime import timedelta

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import F
from django.db import transaction
from rest_framework.authentication import TokenAuthentication 
from rest_framework_simplejwt.authentication import JWTAuthentication
from decimal import Decimal

from ecommerce.models.order import Cart, CustomerAddress
from ecommerce.models.product import ProductStock
from ecommerce.serializers.order_serializers import (
    CartSerializer, CustomerAddressSerializer
)
from ecommerce.models.customer import CustomerProfile
from ecommerce.utils.campaign_utils import get_campaign_price_for_product  # 👈 ADD THIS IMPORT


class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    authentication_classes = [JWTAuthentication,TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # ✅ Allow both customer and both user types to access cart
        if not self.request.user.is_customer():
            return Cart.objects.none()
        
        return Cart.objects.filter(customer=self.request.user).select_related(
            'product_stock', 
            'product_stock__product', 
            'product_stock__product__vendor'
        )
    
    def create(self, request, *args, **kwargs):  
        product_stock_id = request.data.get('product_stock')
        quantity = int(request.data.get('quantity', 1))
        
        try:
            product_stock = ProductStock.objects.get(id=product_stock_id)
            
            # Check stock availability
            if product_stock.stock_quantity < quantity:
                return Response({
                    'success': False,
                    'message': f'Only {product_stock.stock_quantity} items available in stock'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check max order quantity
            if quantity > product_stock.maximum_order_quantity:
                return Response({
                    'success': False,
                    'message': f'Maximum order quantity is {product_stock.maximum_order_quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if item already in cart
            cart_item, created = Cart.objects.get_or_create(
                customer=request.user,
                product_stock=product_stock,
                defaults={'quantity': quantity}
            )
            
            if not created:
                new_quantity = cart_item.quantity + quantity
                
                if new_quantity > product_stock.maximum_order_quantity:
                    return Response({
                        'success': False,
                        'message': f'Maximum order quantity is {product_stock.maximum_order_quantity}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                cart_item.quantity = new_quantity
                cart_item.save()
            
            serializer = self.get_serializer(cart_item)
            
            # 👇 Get campaign price for response
            campaign_data = get_campaign_price_for_product(product_stock.product, request)
            
            response_data = serializer.data
            if campaign_data:
                response_data['campaign_price'] = campaign_data['campaign_price']
                response_data['original_price'] = campaign_data['original_price']
                response_data['is_in_campaign'] = True
                response_data['campaign_details'] = campaign_data
            else:
                response_data['campaign_price'] = None
                response_data['is_in_campaign'] = False
            
            return Response({
                'success': True,
                'message': 'Item added to cart',
                'data': response_data
            }, status=status.HTTP_201_CREATED)
            
        except ProductStock.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
# In ecommerce/views/cart_views.py - Update the list method

    def list(self, request, *args, **kwargs):
        """Override list to add campaign prices and countdown to cart items"""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        # 👇 Add campaign prices and countdown to each cart item
        cart_data = []
        for item, item_data in zip(queryset, serializer.data):
            campaign_data = get_campaign_price_for_product(item.product_stock.product, request)
            
            if campaign_data:
                item_data['campaign_price'] = campaign_data['campaign_price']
                item_data['original_price'] = campaign_data['original_price']
                item_data['is_in_campaign'] = True
                item_data['campaign_details'] = campaign_data
                
                # 👇 Add countdown if end_datetime exists
                if campaign_data.get('end_datetime'):
                    from django.utils import timezone
                    now = timezone.now()
                    end_time = campaign_data['end_datetime']
                    
                    # Check if end_time is timezone-aware
                    if timezone.is_aware(end_time) and timezone.is_naive(now):
                        now = timezone.make_aware(now)
                    elif timezone.is_naive(end_time) and timezone.is_aware(now):
                        end_time = timezone.make_aware(end_time)
                    
                    if end_time > now:
                        time_diff = end_time - now
                        total_seconds = int(time_diff.total_seconds())
                        
                        days = total_seconds // (24 * 3600)
                        hours = (total_seconds % (24 * 3600)) // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        
                        item_data['campaign_countdown'] = {
                            'days': days,
                            'hours': hours,
                            'minutes': minutes,
                            'seconds': seconds,
                            'total_seconds': total_seconds,
                            'campaign_type': campaign_data.get('campaign_type'),
                            'campaign_name': campaign_data.get('campaign_name')
                        }
                
                # Override item_total with campaign price
                price = Decimal(str(campaign_data['campaign_price']))
                item_data['item_total'] = float(
                    (price * Decimal(str(item.quantity))).quantize(Decimal("0.01"))
                )
            else:
                item_data['campaign_price'] = None
                item_data['is_in_campaign'] = False
                item_data['campaign_countdown'] = None
            
            cart_data.append(item_data)
        
        return Response({
            'success': True,
            'data': cart_data
        })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        cart_items = self.get_queryset()

        subtotal = Decimal("0.00")

        for item in cart_items:
            campaign_data = get_campaign_price_for_product(
                item.product_stock.product,
                request
            )

            if campaign_data:
                price = Decimal(str(campaign_data['campaign_price']))
                subtotal += price * Decimal(str(item.quantity))
            else:
                subtotal += Decimal(str(item.item_total))

        item_count = len(cart_items)

        free_shipping_threshold = Decimal("1000")
        shipping_charge = Decimal("0.00") if subtotal >= free_shipping_threshold else Decimal("50.00")

        total = subtotal + shipping_charge

        return Response({
            'success': True,
            'data': {
                'item_count': item_count,
                'subtotal': str(subtotal.quantize(Decimal("0.01"))),
                'shipping_charge': str(shipping_charge),
                'total': str(total.quantize(Decimal("0.01"))),
                'free_shipping_threshold': str(free_shipping_threshold),
                'eligible_for_free_shipping': subtotal >= free_shipping_threshold
            }
        })
    
    @action(detail=True, methods=['post'])
    def update_quantity(self, request, pk=None):
        try:
            cart_item = Cart.objects.get(id=pk, customer=request.user)
            quantity = int(request.data.get('quantity', 1))
            
            if quantity < 1:
                cart_item.delete()
                return Response({
                    'success': True,
                    'message': 'Item removed from cart'
                })
            
            # Check stock availability
            if cart_item.product_stock.stock_quantity < quantity:
                return Response({
                    'success': False,
                    'message': f'Only {cart_item.product_stock.stock_quantity} items available in stock'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check max order quantity
            if quantity > cart_item.product_stock.maximum_order_quantity:
                return Response({
                    'success': False,
                    'message': f'Maximum order quantity is {cart_item.product_stock.maximum_order_quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            cart_item.quantity = quantity
            cart_item.save()
            
            serializer = self.get_serializer(cart_item)
            
            # 👇 Add campaign price to response
            campaign_data = get_campaign_price_for_product(cart_item.product_stock.product, request)
            
            response_data = serializer.data
            if campaign_data:
                response_data['campaign_price'] = campaign_data['campaign_price']
                response_data['original_price'] = campaign_data['original_price']
                response_data['is_in_campaign'] = True
                price = Decimal(str(campaign_data['campaign_price']))
                response_data['item_total'] = float(
                    (price * Decimal(str(quantity))).quantize(Decimal("0.01"))
                )
            else:
                response_data['campaign_price'] = None
                response_data['is_in_campaign'] = False
            
            return Response({
                'success': True,
                'message': 'Quantity updated',
                'data': response_data
            })
            
        except Cart.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'])
    def clear(self, request):
        cart_items = self.get_queryset()
        count = cart_items.count()
        cart_items.delete()
        
        return Response({
            'success': True,
            'message': f'Cleared {count} items from cart'
        })


class CustomerAddressViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerAddressSerializer
    authentication_classes = [TokenAuthentication, JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return CustomerAddress.objects.filter(customer=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        try:
            address = CustomerAddress.objects.get(id=pk, customer=request.user)
            address.is_default = True
            address.save()
            
            return Response({
                'success': True,
                'message': 'Address set as default'
            })
        except CustomerAddress.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Address not found'
            }, status=status.HTTP_404_NOT_FOUND)


class CheckoutAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Step 2: Verify payment and create order
        """
        from ecommerce.serializers.order_serializers import CheckoutSerializer 
        from ecommerce.models.order import Order, OrderItem, Cart, CustomerAddress
        from ecommerce.models.coupon import Coupon, CouponUsage 
        from django.db import transaction
        import razorpay
        from mlm.models.agent import Agent
        from users.models import User
        from django.conf import settings
        from django.utils import timezone
        from ecommerce.models.loyalty import LoyaltyPointsConfig, LoyaltyPointsTransaction
        from ecommerce.models.customer import CustomerProfile
        from ecommerce.utils.campaign_utils import get_campaign_price_for_product
        from decimal import Decimal
        
        print(f"Key ID raw: '{settings.RAZORPAY_KEY_ID}'")
        print(f"Key Secret first/last chars: '{settings.RAZORPAY_KEY_SECRET[:1]}...{settings.RAZORPAY_KEY_SECRET[-1:]}'")

        # Strip whitespace
        key_id = settings.RAZORPAY_KEY_ID.strip()
        key_secret = settings.RAZORPAY_KEY_SECRET.strip()
        print(f"After strip - Key ID: '{key_id}'")
        print(f"After strip - Key Secret: '{key_secret[:5]}...'")
        
        # For Razorpay - Get payment details
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_signature = request.data.get('razorpay_signature')
        
        # ========== RAZORPAY PAYMENT VERIFICATION ==========
        if razorpay_payment_id and razorpay_order_id and razorpay_signature:

            try:
                import hmac
                import hashlib
                from ecommerce.models.order import PendingCheckout

                # 🔐 Verify Signature
                body = f"{razorpay_order_id}|{razorpay_payment_id}"
                expected_signature = hmac.new(
                    settings.RAZORPAY_KEY_SECRET.strip().encode(),
                    body.encode(),
                    hashlib.sha256
                ).hexdigest()

                if not hmac.compare_digest(expected_signature, razorpay_signature):
                    return Response({
                        'success': False,
                        'message': 'Invalid payment signature'
                    }, status=400)

                # 💳 Fetch payment from Razorpay
                client = razorpay.Client(
                    auth=(settings.RAZORPAY_KEY_ID.strip(), settings.RAZORPAY_KEY_SECRET.strip())
                )

                payment = client.payment.fetch(razorpay_payment_id)

                if payment['status'] != 'captured':
                    return Response({
                        'success': False,
                        'message': 'Payment not completed'
                    }, status=400)
                if Order.objects.filter(razorpay_order_id=razorpay_order_id).exists():
                    return Response({
                        "success": True,
                        "message": "Order already processed"
                    })
                # 📦 Get Pending Checkout
                try:
                    pending = PendingCheckout.objects.get(
                        user=request.user,
                        razorpay_order_id=razorpay_order_id
                    )
                except PendingCheckout.DoesNotExist:
                    return Response({
                        "success": False,
                        "message": "Invalid or expired checkout"
                    }, status=400)
                expires_at = timezone.now() + timedelta(minutes=15)
                if pending.is_expired():
                    pending.delete()
                    return Response({
                        "success": False,
                        "message": "Checkout expired."
                    }, status=400)

                coupon_code = pending.coupon_code
                loyalty_points_to_use = pending.loyalty_points_to_use or 0
                billing_address_id = pending.billing_address_id
                shipping_address_id = pending.shipping_address_id
                use_same_address = pending.use_same_address
                notes = pending.notes or ""

                # 🛒 Get Cart
                cart_items = Cart.objects.filter(customer=request.user).select_related(
                    'product_stock', 'product_stock__product', 'product_stock__product__vendor'
                )

                if not cart_items.exists():
                    return Response({
                        'success': False,
                        'message': 'Cart is empty'
                    }, status=400)

                with transaction.atomic():

                    #  Validate quantity & stock
                    for cart_item in cart_items:
                        if cart_item.quantity > cart_item.product_stock.maximum_order_quantity:
                            return Response({
                                'success': False,
                                'message': f"Maximum allowed for {cart_item.product_stock.product.product_name} is {cart_item.product_stock.maximum_order_quantity}"
                            }, status=400)

                        if cart_item.product_stock.stock_quantity < cart_item.quantity:
                            return Response({
                                'success': False,
                                'message': f"Only {cart_item.product_stock.stock_quantity} units available"
                            }, status=400)

                    # 💰 Calculate subtotal (campaign safe)
                    subtotal = Decimal("0.00")
                    campaign_items_info = []

                    for cart_item in cart_items:
                        campaign_data = get_campaign_price_for_product(
                            cart_item.product_stock.product, request
                        )

                        if campaign_data:
                            item_price = Decimal(str(campaign_data['campaign_price']))
                        else:
                            item_price = Decimal(str(cart_item.product_stock.final_price))

                        campaign_items_info.append({
                            'cart_item': cart_item,
                            'campaign_data': campaign_data,
                            'item_price': item_price
                        })

                        subtotal += item_price * cart_item.quantity

                    shipping_charge = Decimal("0") if subtotal >= Decimal("1000") else Decimal("50")

                    # 🎟 Coupon validation (FULLY SAFE)
                    discount_amount = Decimal("0.00")
                    coupon = None

                    if coupon_code:
                        try:
                            coupon = Coupon.objects.get(code=coupon_code.upper(), status='active')

                            if not coupon.is_valid():
                                return Response({
                                    'success': False,
                                    'message': 'Coupon expired or inactive'
                                }, status=400)

                            usage_count = CouponUsage.objects.filter(
                                coupon=coupon,
                                user=request.user
                            ).count()

                            if usage_count >= coupon.limit_per_user:
                                return Response({
                                    'success': False,
                                    'message': f'Coupon already used {usage_count} times'
                                }, status=400)

                            applicable_amount = Decimal("0.00")
                            for item in campaign_items_info:
                                product = item['cart_item'].product_stock.product
                                if coupon.can_be_applied_to_product(product):
                                    applicable_amount += item['item_price'] * item['cart_item'].quantity

                            if applicable_amount >= Decimal(str(coupon.min_order_value)):
                                discount_amount = coupon.calculate_discount(applicable_amount)
                                coupon.used_count = F('used_count') + 1
                                coupon.save()
                                coupon.refresh_from_db()

                        except Coupon.DoesNotExist:
                            pass

                    # 👤 Customer Profile
                    profile, _ = CustomerProfile.objects.get_or_create(
                        user=request.user,
                        defaults={
                            'full_name': request.user.get_full_name() or request.user.username,
                            'email': request.user.email
                        }
                    )

                    # ⭐ Loyalty usage
                    loyalty_points_used = 0
                    if loyalty_points_to_use > 0 and profile.loyalty_points_balance >= loyalty_points_to_use:
                        loyalty_points_used = loyalty_points_to_use
                        loyalty_discount = Decimal(str(loyalty_points_used)) * Decimal("0.10")
                        discount_amount += loyalty_discount

                    final_amount = subtotal + shipping_charge - discount_amount

                    # 🔒 Amount Tampering Protection
                    razorpay_amount = Decimal(str(payment['amount'])) / Decimal("100")
                    if razorpay_amount != final_amount:
                        return Response({
                            'success': False,
                            'message': 'Payment amount mismatch'
                        }, status=400)

                    # 📍 Address Handling
                    billing_address = CustomerAddress.objects.get(
                        id=billing_address_id,
                        customer=request.user
                    )

                    if use_same_address:
                        shipping_address = billing_address
                    else:
                        shipping_address = CustomerAddress.objects.get(
                            id=shipping_address_id,
                            customer=request.user
                        )
                    from ecommerce.utils.agent_order_utils import resolve_referral_agent

                    referral_code = request.data.get("referral_code")
                    referral_agent = resolve_referral_agent(request.user, referral_code)

                    # if referral_agent:
                    # #     from utils.upline_engine import get_upline_agents
                    # #     update_agent_sales(referral_agent.user, final_amount)
                        
                    #     # Upline chain update for activation check
                    #     uplines = get_upline_agents(referral_agent.user)
                    #     for upline in uplines:
                    #         # update_agent_sales(upline["user"], Decimal("0"))
                    
                    # 🧾 Create Order
                    order = Order.objects.create(
                        customer=request.user,
                        referral_agent=referral_agent,
                        total_amount=subtotal,
                        shipping_charge=shipping_charge,
                        discount_amount=discount_amount,
                        loyalty_points_used=loyalty_points_used,
                        final_amount=final_amount,

                        billing_name=billing_address.full_name,
                        billing_email=billing_address.email,
                        billing_phone=billing_address.phone,
                        billing_address=billing_address.address_line1,
                        billing_city=billing_address.city,
                        billing_state=billing_address.state,
                        billing_pincode=billing_address.pincode,

                        shipping_name=shipping_address.full_name,
                        shipping_phone=shipping_address.phone,
                        shipping_address=shipping_address.address_line1,
                        shipping_city=shipping_address.city,
                        shipping_state=shipping_address.state,
                        shipping_pincode=shipping_address.pincode,

                        payment_method='razorpay',
                        payment_status='completed',
                        order_status='confirmed',

                        razorpay_order_id=razorpay_order_id,
                        razorpay_payment_id=razorpay_payment_id,
                        razorpay_signature=razorpay_signature,

                        notes=notes
                    )
                    #Update customer stats (Already exists but ensure it's there)
                    profile.total_orders += 1
                    profile.total_spent += final_amount
                    profile.save()
                    profile.check_agent_eligibility()
                    # if referral_agent:
                    #     from ecommerce.utils.order_service import update_agent_sales
                    #     update_agent_sales(referral_agent.user, final_amount)
                        
                    #     # Upline agents की sales भी update करो (0 amount से)
                    #     from utils.upline_engine import get_upline_agents
                    #     uplines = get_upline_agents(referral_agent.user)
                    #     for upline in uplines:
                    #         update_agent_sales(upline["user"], Decimal("0"))

                    # 📦 Create Order Items + Reduce Stock
                    for item in campaign_items_info:

                        cart_item = item['cart_item']
                        product_stock = cart_item.product_stock

                        product_stock.stock_quantity -= cart_item.quantity
                        product_stock.save()

                        vendor_receivable = product_stock.vendor_receivable
                        platform_profit = Decimal(str(product_stock.final_price)) - Decimal(str(vendor_receivable))

                        OrderItem.objects.create(

                            order=order,
                            vendor=product_stock.product.vendor,
                            product=product_stock.product,
                            product_stock=product_stock,

                            product_name=product_stock.product.product_name,
                            sku=product_stock.product.sku,
                            color=product_stock.color,
                            size=product_stock.size,

                            quantity=cart_item.quantity,

                            unit_price=item['item_price'],
                            total_price=item['item_price'] * cart_item.quantity,

                            vendor_receivable=vendor_receivable,
                            platform_profit=platform_profit * cart_item.quantity,
                        )
                        from django.db.models import Sum

                    total_platform_profit = order.items.aggregate(
                        total=Sum("platform_profit")
                    )["total"] or 0

                    # # In CheckoutAPIView (around line where you distribute commission)
                    # if order.referral_agent and not order.commission_distributed_at_checkout:
                    #     from utils.profit_engine import calculate_profit_distribution
                    #     from utils.commision_engine import distribute_commission
                        
                    #     # Sum up platform_profit
                    #     total_platform_profit = order.items.aggregate(
                    #         total=Sum('platform_profit')
                    #     )['total'] or 0

                    #     result = calculate_profit_distribution(
                    #         total_profit=total_platform_profit,
                    #         seller_user=order.referral_agent.user,
                    #         root_user=order.referral_agent.user
                    #     )

                    #     distribute_commission(order, result)

                    #     # Set flags
                    #     order.commission_distributed_at_checkout = True
                    #     order.commission_distributed = True
                    #     order.save()
                        
                    cart_items.delete()
                    pending.delete()

                    return Response({
                            'success': True,
                            'message': 'Order created successfully',
                            'order_number': order.order_number
                        })

            except Exception as e:
                print("❌ Razorpay Checkout Error:", str(e))
                return Response({
                    'success': False,
                    'message': f'Failed to create order: {str(e)}'
                }, status=500)
        
        # ========== COD OR DIRECT CHECKOUT ==========
        else:
            # ✅ COD Checkout - Use serializer with full data
            serializer = CheckoutSerializer(data=request.data, context={'request': request})
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                with transaction.atomic():
                    # Get cart items
                    cart_items = Cart.objects.filter(customer=request.user).select_related(
                        'product_stock', 'product_stock__product', 'product_stock__product__vendor'
                    )
                    
                    if not cart_items.exists():
                        return Response({
                            'success': False,
                            'message': 'Cart is empty'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # ========== VALIDATE MAX ORDER QUANTITY AND STOCK ==========
                    for cart_item in cart_items:
                        if cart_item.quantity > cart_item.product_stock.maximum_order_quantity:
                            return Response({
                                'success': False,
                                'message': f"Cannot order {cart_item.quantity} units of '{cart_item.product_stock.product.product_name}'. Maximum allowed is {cart_item.product_stock.maximum_order_quantity}."
                            }, status=status.HTTP_400_BAD_REQUEST)
                        
                        if cart_item.product_stock.stock_quantity < cart_item.quantity:
                            return Response({
                                'success': False,
                                'message': f"Only {cart_item.product_stock.stock_quantity} units of '{cart_item.product_stock.product.product_name}' available in stock."
                            }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Calculate subtotal with campaign prices
                    subtotal = Decimal("0.00")
                    campaign_items_info = []
                    
                    for cart_item in cart_items:
                        campaign_data = get_campaign_price_for_product(cart_item.product_stock.product, request)
                        
                        if campaign_data:
                            item_price = Decimal(str(campaign_data['campaign_price']))
                            campaign_items_info.append({
                                'cart_item': cart_item,
                                'campaign_data': campaign_data,
                                'item_price': item_price
                            })
                        else:
                            item_price = Decimal(str(cart_item.product_stock.final_price))
                            campaign_items_info.append({
                                'cart_item': cart_item,
                                'campaign_data': None,
                                'item_price': item_price
                            })
                        
                        subtotal += item_price * cart_item.quantity
                    
                    shipping_charge = Decimal("0") if subtotal >= Decimal("1000") else Decimal("50")
                    
                    # Apply coupon if valid
                    discount_amount = Decimal("0.00")
                    coupon = None
                    coupon_code = serializer.validated_data.get('coupon_code')
                    
                    if coupon_code:
                        try:
                            coupon = Coupon.objects.get(code=coupon_code.upper(), status='active')
                            
                            if not coupon.is_valid():
                                return Response({
                                    'success': False,
                                    'message': 'Coupon is expired or inactive'
                                }, status=status.HTTP_400_BAD_REQUEST)
                            
                            usage_count = CouponUsage.objects.filter(
                                coupon=coupon,
                                user=request.user
                            ).count()
                            
                            if usage_count >= coupon.limit_per_user:
                                return Response({
                                    'success': False,
                                    'message': f'You have already used this coupon {usage_count} times'
                                }, status=status.HTTP_400_BAD_REQUEST)
                            
                            applicable_amount = Decimal("0.00")
                            applicable_items = []
                            
                            for item_info in campaign_items_info:
                                product = item_info['cart_item'].product_stock.product
                                if coupon.can_be_applied_to_product(product):
                                    applicable_amount += item_info['item_price'] * item_info['cart_item'].quantity
                                    applicable_items.append({
                                        'product_id': product.id,
                                        'product_name': product.product_name,
                                        'quantity': item_info['cart_item'].quantity,
                                        'price': item_info['item_price']
                                    })
                            
                            if applicable_amount == 0:
                                return Response({
                                    'success': False,
                                    'message': 'This coupon cannot be applied to any item in your cart'
                                }, status=status.HTTP_400_BAD_REQUEST)
                            
                            if applicable_amount < Decimal(str(coupon.min_order_value)):
                                return Response({
                                    'success': False,
                                    'message': f'Minimum order value for this coupon is ₹{coupon.min_order_value}'
                                }, status=status.HTTP_400_BAD_REQUEST)
                            
                            discount_amount = coupon.calculate_discount(applicable_amount)
                            coupon_applied_items = applicable_items
                            coupon.used_count = F('used_count') + 1
                            coupon.save()
                            coupon.refresh_from_db()
                            
                        except Coupon.DoesNotExist:
                            return Response({
                                'success': False,
                                'message': 'Invalid coupon code'
                            }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Get or create customer profile
                    profile, created = CustomerProfile.objects.get_or_create(
                        user=request.user,
                        defaults={
                            'full_name': request.user.get_full_name() or request.user.username,
                            'email': request.user.email,
                            'phone': '',
                            'address': '',
                            'city': '',
                            'state': ''
                        }
                    )
                    
                    # Apply loyalty points if requested
                    loyalty_points_used = 0
                    loyalty_discount = 0
                    loyalty_points_to_use = serializer.validated_data.get('loyalty_points_to_use', 0)
                    
                    if loyalty_points_to_use > 0:
                        if profile.can_use_points(loyalty_points_to_use):
                            loyalty_points_used = loyalty_points_to_use
                            loyalty_discount = Decimal(str(loyalty_points_used)) * Decimal("0.10")
                            discount_amount += loyalty_discount
                        else:
                            return Response({
                                'success': False,
                                'message': f'Not enough loyalty points. You have {profile.loyalty_points} points'
                            }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Calculate final amount
                    final_amount = subtotal + shipping_charge - discount_amount
                    
                    # Calculate loyalty points to be earned
                    loyalty_points_earned = 0
                    applied_loyalty_rules = []
                    
                    active_rules = LoyaltyPointsConfig.objects.filter(
                        is_active=True,
                        valid_from__lte=timezone.now()
                    ).exclude(
                        valid_to__lt=timezone.now()
                    ).order_by('-priority')
                    
                    for rule in active_rules:
                        points = rule.calculate_points(final_amount)
                        if points > 0:
                            loyalty_points_earned += points
                            applied_loyalty_rules.append({
                                'rule_id': rule.id,
                                'rule_name': rule.name,
                                'points_type': rule.points_type,
                                'points_earned': points
                            })
                    
                    # Get addresses
                    use_same_address = serializer.validated_data.get('use_same_address', True)
                    billing_address_id = serializer.validated_data.get('billing_address_id')
                    
                    if billing_address_id:
                        try:
                            billing_address = CustomerAddress.objects.get(
                                id=billing_address_id, customer=request.user
                            )
                            billing_data = {
                                'name': billing_address.full_name,
                                'phone': billing_address.phone,
                                'email': billing_address.email or request.user.email,
                                'address': billing_address.address_line1,
                                'city': billing_address.city,
                                'state': billing_address.state,
                                'pincode': billing_address.pincode
                            }
                        except CustomerAddress.DoesNotExist:
                            return Response({
                                'success': False,
                                'message': 'Billing address not found'
                            }, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        billing_data = {
                            'name': profile.full_name or request.user.get_full_name() or request.user.username,
                            'phone': profile.phone or '',
                            'email': profile.email or request.user.email,
                            'address': profile.address or '',
                            'city': profile.city or '',
                            'state': profile.state or '',
                            'pincode': profile.pincode if hasattr(profile, 'pincode') else '000000'
                        }
                    
                    # Get shipping address
                    if use_same_address:
                        shipping_data = billing_data
                    else:
                        shipping_address_id = serializer.validated_data.get('shipping_address_id')
                        if shipping_address_id:
                            try:
                                shipping_address = CustomerAddress.objects.get(
                                    id=shipping_address_id, customer=request.user
                                )
                                shipping_data = {
                                    'name': shipping_address.full_name,
                                    'phone': shipping_address.phone,
                                    'email': shipping_address.email or request.user.email,
                                    'address': shipping_address.address_line1,
                                    'city': shipping_address.city,
                                    'state': shipping_address.state,
                                    'pincode': shipping_address.pincode
                                }
                            except CustomerAddress.DoesNotExist:
                                return Response({
                                    'success': False,
                                    'message': 'Shipping address not found'
                                }, status=status.HTTP_400_BAD_REQUEST)
                        else:
                            shipping_data = {
                                'name': serializer.validated_data.get('shipping_name') or billing_data['name'],
                                'phone': serializer.validated_data.get('shipping_phone') or billing_data['phone'],
                                'email': request.user.email,
                                'address': serializer.validated_data.get('shipping_address') or billing_data['address'],
                                'city': serializer.validated_data.get('shipping_city') or billing_data['city'],
                                'state': serializer.validated_data.get('shipping_state') or billing_data['state'],
                                'pincode': serializer.validated_data.get('shipping_pincode') or billing_data['pincode']
                            }
                    
                    # Prepare order notes
                    order_notes = serializer.validated_data.get('notes', '')
                    if coupon and 'coupon_applied_items' in locals():
                        coupon_info = f"\n\nCoupon Applied: {coupon.code}\n"
                        coupon_info += f"Discount: ₹{discount_amount}\n"
                        if len(coupon_applied_items) > 0:
                            coupon_info += "Applied on items:\n"
                            for item in coupon_applied_items[:3]:
                                coupon_info += f"- {item['product_name']} (Qty: {item['quantity']})\n"
                        order_notes = coupon_info + order_notes
                    
                    # Add campaign info to notes
                    campaign_info = "\n\nCampaign Items:\n"
                    campaign_count = 0
                    for item_info in campaign_items_info:
                        if item_info['campaign_data']:
                            campaign_count += 1
                            campaign_info += f"- {item_info['cart_item'].product_stock.product.product_name}: Campaign Price ₹{item_info['item_price']} (Original ₹{item_info['campaign_data']['original_price']})\n"
                    
                    if campaign_count > 0:
                        order_notes = campaign_info + order_notes
                    # 🔥 FIX: Get referral_code from request.data
                    from ecommerce.utils.agent_order_utils import resolve_referral_agent

                    referral_code = request.data.get('referral_code')
                    if referral_code == "":
                        referral_code = None

                    referral_agent = resolve_referral_agent(request.user, referral_code)
                    
                    # Order create करते समय referral_agent सेट करें
                    order = Order.objects.create(
                        customer=request.user,
                        total_amount=subtotal,
                        shipping_charge=shipping_charge,
                        discount_amount=discount_amount,
                        loyalty_points_used=loyalty_points_used,
                        loyalty_points_earned=loyalty_points_earned,
                        final_amount=final_amount,
                        referral_agent=referral_agent,  
                        
                        billing_name=billing_data['name'],
                        billing_email=billing_data['email'],
                        billing_phone=billing_data['phone'],
                        billing_address=billing_data['address'],
                        billing_city=billing_data['city'],
                        billing_state=billing_data['state'],
                        billing_pincode=billing_data['pincode'],
                        
                        shipping_name=shipping_data['name'],
                        shipping_phone=shipping_data['phone'],
                        shipping_address=shipping_data['address'],
                        shipping_city=shipping_data['city'],
                        shipping_state=shipping_data['state'],
                        shipping_pincode=shipping_data['pincode'],
                        
                        payment_method=serializer.validated_data['payment_method'],
                        notes=order_notes
                    )
                    # if referral_agent:
                    #     from ecommerce.utils.order_service import update_agent_sales
                    #     update_agent_sales(referral_agent.user, final_amount)
                        
                    #     # Upline agents की sales भी update करो (0 amount से)
                    #     from utils.upline_engine import get_upline_agents
                    #     uplines = get_upline_agents(referral_agent.user)
                    #     for upline in uplines:
                    #         update_agent_sales(upline["user"], Decimal("0"))
                    
                    # Create order items and reduce stock
                    order_items = []
                    for item_info in campaign_items_info:
                        cart_item = item_info['cart_item']
                        product_stock = cart_item.product_stock
                        item_price = item_info['item_price']
                        campaign_data = item_info['campaign_data']
                        
                        if product_stock.stock_quantity < cart_item.quantity:
                            raise Exception(f"Insufficient stock for {product_stock.product.product_name}")
                        
                        product_stock.stock_quantity -= cart_item.quantity
                        product_stock.save()
                        
                        item_subtotal = item_price * cart_item.quantity
                        
                        vendor_receivable = product_stock.vendor_receivable
                        platform_profit = Decimal(str(product_stock.final_price)) - Decimal(str(vendor_receivable))
                        
                        order_item = OrderItem(

                            order=order,
                            vendor=product_stock.product.vendor,
                            product=product_stock.product,
                            product_stock=product_stock,

                            product_name=product_stock.product.product_name,
                            sku=product_stock.product.sku,
                            color=product_stock.color,
                            size=product_stock.size,

                            quantity=cart_item.quantity,

                            unit_price=item_price,
                            total_price=item_subtotal,

                            vendor_receivable=vendor_receivable,
                            platform_profit=platform_profit * cart_item.quantity
                        )
                        
                        if campaign_data and hasattr(order_item, 'original_price'):
                            order_item.original_price = campaign_data['original_price']
                        
                        order_items.append(order_item)
                    
                    OrderItem.objects.bulk_create(order_items)
                    
                from django.db.models import Sum

                total_platform_profit = order.items.aggregate(
                    total=Sum("platform_profit")
                )["total"] or 0

                # # In CheckoutAPIView (around line where you distribute commission)
                # if order.referral_agent and not order.commission_distributed_at_checkout:
                #     from utils.profit_engine import calculate_profit_distribution
                #     from utils.commision_engine import distribute_commission
                    
                #     # Sum up platform_profit
                #     total_platform_profit = order.items.aggregate(
                #         total=Sum('platform_profit')
                #     )['total'] or 0

                #     result = calculate_profit_distribution(
                #         total_profit=total_platform_profit,
                #         seller_user=order.referral_agent.user,
                #         root_user=order.referral_agent.user
                #     )

                #     distribute_commission(order, result)

                #     # Set flags
                #     order.commission_distributed_at_checkout = True
                #     order.commission_distributed = True
                #     order.save()
                cart_items.delete()

                # Handle loyalty points transactions
                if loyalty_points_used > 0:
                    LoyaltyPointsTransaction.objects.create(
                        customer=request.user,
                        points=loyalty_points_used,
                        transaction_type='used',
                        order_id=order.id,
                        order_number=order.order_number,
                        description=f"Used {loyalty_points_used} points for order {order.order_number}",
                        balance_after=profile.loyalty_points - loyalty_points_used
                    )

                    profile.loyalty_points_balance = profile.loyalty_points - loyalty_points_used
                    profile.save()

                if loyalty_points_earned > 0:
                    current_balance = profile.loyalty_points - loyalty_points_used
                    new_balance = current_balance + loyalty_points_earned

                    for rule_info in applied_loyalty_rules:
                        rule = LoyaltyPointsConfig.objects.get(id=rule_info['rule_id'])

                        LoyaltyPointsTransaction.objects.create(
                            customer=request.user,
                            points=rule_info['points_earned'],
                            transaction_type='earned',
                            config=rule,
                            order_id=order.id,
                            order_number=order.order_number,
                            description=f"Earned {rule_info['points_earned']} points from rule: {rule.name}",
                            balance_after=new_balance
                        )

                    profile.loyalty_points_balance = new_balance
                    profile.save()
                # Create coupon usage record
                if coupon:
                    CouponUsage.objects.create(
                        coupon=coupon,
                        user=request.user,
                        order=order,
                        discount_amount=discount_amount
                    )

                # Update customer stats
                profile.total_orders += 1
                final_amount_decimal = Decimal(str(final_amount))
                profile.total_spent += final_amount_decimal
                profile.save()

                # Prepare campaign items response
                campaign_items_response = []
                for item_info in campaign_items_info:
                    if item_info['campaign_data']:
                        campaign_items_response.append({
                            'product_name': item_info['cart_item'].product_stock.product.product_name,
                            'campaign_name': item_info['campaign_data']['campaign_name'],
                            'campaign_type': item_info['campaign_data']['campaign_type'],
                            'original_price': item_info['campaign_data']['original_price'],
                            'campaign_price': item_info['campaign_data']['campaign_price'],
                            'discount_percentage': item_info['campaign_data']['discount_percentage'],
                            'quantity': item_info['cart_item'].quantity
                        })

                return Response({
                    'success': True,
                    'message': 'Order created successfully',
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'payment_method': 'cod',
                    'final_amount': final_amount,
                    'subtotal': subtotal,
                    'shipping_charge': shipping_charge,
                    'discount_amount': discount_amount,
                    'coupon_applied': {
                        'code': coupon.code if coupon else None,
                        'discount': discount_amount if coupon else 0
                    },
                    'loyalty_points': {
                        'used': loyalty_points_used,
                        'earned': loyalty_points_earned,
                        'new_balance': profile.loyalty_points_balance,
                        'applied_rules': applied_loyalty_rules
                    },
                    'campaign_info': {
                        'items_count': campaign_count,
                        'items': campaign_items_response
                    }
                })
                    
            except Exception as e:
                return Response({
                    'success': False,
                    'message': f'Checkout failed: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoyaltyPointsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            # Get or create customer profile
            from ecommerce.models.customer import CustomerProfile
            profile, created = CustomerProfile.objects.get_or_create(
                user=request.user,
                defaults={
                    'full_name': request.user.get_full_name() or request.user.username,
                    'email': request.user.email
                }
            )
            
            from ecommerce.models.loyalty import LoyaltyPointsTransaction
            from ecommerce.serializers.loyalty_serializers import LoyaltyPointsTransactionSerializer
            from ecommerce.models.loyalty import LoyaltyPointsConfig
            from django.utils import timezone
            
            # Get recent transactions
            transactions = LoyaltyPointsTransaction.objects.filter(
                customer=request.user
            ).order_by('-created_at')[:20]
            
            # Get active loyalty rules that customer can benefit from
            active_rules = LoyaltyPointsConfig.objects.filter(
                is_active=True,
                valid_from__lte=timezone.now()
            ).exclude(
                valid_to__lt=timezone.now()
            ).order_by('-priority')[:5]
            
            # Calculate points value
            points_value = round(profile.loyalty_points * 0.1, 2)
            
            # Calculate how much more to spend for next reward tier
            next_reward_info = None
            if active_rules.exists():
                # Find the next applicable rule based on average order
                avg_order_value = profile.total_orders > 0 and profile.total_spent / profile.total_orders or 0
                
                for rule in active_rules:
                    if rule.min_order_amount > avg_order_value:
                        next_reward_info = {
                            'rule_name': rule.name,
                            'min_amount': float(rule.min_order_amount),
                            'remaining': round(float(rule.min_order_amount) - avg_order_value, 2),
                            'points_expected': rule.calculate_points(float(rule.min_order_amount))
                        }
                        break
            
            transaction_serializer = LoyaltyPointsTransactionSerializer(transactions, many=True)
            
            return Response({
                'success': True,
                'data': {
                    'available_points': profile.loyalty_points,
                    'points_value': points_value,
                    'total_spent': profile.total_spent,
                    'total_orders': profile.total_orders,
                    'next_reward': next_reward_info,
                    'transactions': transaction_serializer.data,
                    'active_rules_preview': [
                        {
                            'name': rule.name,
                            'points_type': rule.get_points_type_display(),
                            'min_order': float(rule.min_order_amount)
                        } for rule in active_rules
                    ]
                }
            })
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error fetching loyalty points: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
class CreateRazorpayOrderAPIView(APIView):
    """
    Step 1: Secure Razorpay Order Creation
    - Amount calculated on server
    - Campaign supported
    - Coupon validated
    - Loyalty validated
    - Tampering protected
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from ecommerce.serializers.order_serializers import CreateRazorpayOrderSerializer
        from ecommerce.models.order import Cart
        from ecommerce.models.order import PendingCheckout
        from ecommerce.models.coupon import Coupon, CouponUsage
        from ecommerce.models.customer import CustomerProfile
        from ecommerce.utils.campaign_utils import get_campaign_price_for_product
        from decimal import Decimal
        from django.conf import settings
        from rest_framework import status
        import razorpay

        serializer = CreateRazorpayOrderSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 🛒 Get Cart
            cart_items = Cart.objects.filter(customer=request.user).select_related(
                'product_stock', 'product_stock__product'
            )

            if not cart_items.exists():
                return Response({
                    'success': False,
                    'message': 'Cart is empty'
                }, status=status.HTTP_400_BAD_REQUEST)

            # 🔎 Validate stock & max quantity
            for cart_item in cart_items:
                if cart_item.quantity > cart_item.product_stock.maximum_order_quantity:
                    return Response({
                        'success': False,
                        'message': f"Maximum allowed for {cart_item.product_stock.product.product_name} is {cart_item.product_stock.maximum_order_quantity}"
                    }, status=400)

                if cart_item.product_stock.stock_quantity < cart_item.quantity:
                    return Response({
                        'success': False,
                        'message': f"Only {cart_item.product_stock.stock_quantity} units available"
                    }, status=400)

            # 💰 Calculate subtotal (Decimal safe)
            subtotal = Decimal("0.00")
            campaign_items_info = []

            for cart_item in cart_items:
                campaign_data = get_campaign_price_for_product(
                    cart_item.product_stock.product,
                    request
                )

                if campaign_data:
                    item_price = Decimal(str(campaign_data['campaign_price']))
                else:
                    item_price = Decimal(str(cart_item.product_stock.final_price))

                campaign_items_info.append({
                    'cart_item': cart_item,
                    'item_price': item_price,
                    'campaign_data': campaign_data
                })

                subtotal += item_price * cart_item.quantity

            shipping_charge = Decimal("0") if subtotal >= Decimal("1000") else Decimal("50")

            # 🎟 Coupon validation
            discount_amount = Decimal("0.00")
            coupon = None
            coupon_code = serializer.validated_data.get('coupon_code')

            if coupon_code:
                try:
                    coupon = Coupon.objects.get(code=coupon_code.upper(), status='active')

                    if not coupon.is_valid():
                        return Response({
                            'success': False,
                            'message': 'Coupon expired or inactive'
                        }, status=400)

                    usage_count = CouponUsage.objects.filter(
                        coupon=coupon,
                        user=request.user
                    ).count()

                    if usage_count >= coupon.limit_per_user:
                        return Response({
                            'success': False,
                            'message': f'Coupon already used {usage_count} times'
                        }, status=400)

                    applicable_amount = Decimal("0.00")
                    for item in campaign_items_info:
                        product = item['cart_item'].product_stock.product
                        if coupon.can_be_applied_to_product(product):
                            applicable_amount += item['item_price'] * item['cart_item'].quantity

                    if applicable_amount < Decimal(str(coupon.min_order_value)):
                        return Response({
                            'success': False,
                            'message': f'Minimum order value is ₹{coupon.min_order_value}'
                        }, status=400)

                    discount_amount = coupon.calculate_discount(applicable_amount)

                except Coupon.DoesNotExist:
                    return Response({
                        'success': False,
                        'message': 'Invalid coupon'
                    }, status=400)

            # ⭐ Loyalty validation
            profile, _ = CustomerProfile.objects.get_or_create(user=request.user)

            loyalty_points_to_use = serializer.validated_data.get('loyalty_points_to_use', 0)

            if loyalty_points_to_use > 0:
                if profile.loyalty_points_balance < loyalty_points_to_use:
                    return Response({
                        'success': False,
                        'message': f'Not enough loyalty points. You have {profile.loyalty_points_balance}'
                    }, status=400)

                loyalty_discount = Decimal(str(loyalty_points_to_use)) * Decimal("0.10")
                discount_amount += loyalty_discount

            #  Final calculation
            discount_amount = Decimal(str(discount_amount))
            final_amount = subtotal + shipping_charge - discount_amount

            if final_amount <= 0:
                return Response({
                    'success': False,
                    'message': 'Invalid final amount'
                }, status=400)

            #  Convert to paise
            razorpay_amount = int(Decimal(str(final_amount)) * 100)

            #  Create Razorpay Order
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID.strip(), settings.RAZORPAY_KEY_SECRET.strip())
            )

            razorpay_order = client.order.create({
                'amount': razorpay_amount,
                'currency': 'INR',
                'payment_capture': 1,
                'notes': {
                    'user_id': request.user.id,
                    'email': request.user.email
                }
            })

            #  Save PendingCheckout
            PendingCheckout.objects.filter(user=request.user).delete()

            # 🔥 FIX: Get referral_code from request.data, not from serializer
            referral_code = request.data.get('referral_code') or None
            
            PendingCheckout.objects.create(
                user=request.user,
                razorpay_order_id=razorpay_order['id'],
                referral_code=referral_code,  # 👈 This was missing!
                billing_address_id=serializer.validated_data.get('billing_address_id'),
                shipping_address_id=serializer.validated_data.get('shipping_address_id'),
                use_same_address=serializer.validated_data.get('use_same_address', True),
                coupon_code=coupon_code,
                loyalty_points_to_use=loyalty_points_to_use,
                notes=serializer.validated_data.get('notes', '')
            )

            return Response({
                'success': True,
                'razorpay_order_id': razorpay_order['id'],
                'amount': razorpay_order['amount'],
                'currency': razorpay_order['currency'],
                'key': settings.RAZORPAY_KEY_ID.strip()
            })

        except Exception as e:
            print("❌ Razorpay Order Creation Error:", str(e))
            return Response({
                'success': False,
                'message': f'Failed to create payment order: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            
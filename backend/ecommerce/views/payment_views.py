import hmac
import hashlib
import json
import uuid
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from ecommerce.models.subscription import SubscriptionPlan
from ecommerce.models.vendor import Vendor
from ecommerce.models.vendor_subscription import VendorSubscription

# Test mode setup - Always True for now
TEST_MODE = True

# Initialize Razorpay client for test mode
if not TEST_MODE:
    import razorpay
    try:
        RAZORPAY_KEY_ID = getattr(settings, 'RAZORPAY_KEY_ID', '')
        RAZORPAY_KEY_SECRET = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
        if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
            client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
            RAZORPAY_ENABLED = True
        else:
            RAZORPAY_ENABLED = False
            client = None
    except Exception as e:
        print(f"Razorpay initialization error: {e}")
        RAZORPAY_ENABLED = False
        client = None
else:
    RAZORPAY_ENABLED = False
    client = None
    print("Running in TEST MODE - Razorpay disabled")

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_razorpay_order(request):
    """
    Create Razorpay order (Test mode compatible)
    """
    try:
        data = request.data
        subscription_plan_id = data.get('subscription_plan_id')
        
        if not subscription_plan_id:
            return Response({
                'success': False,
                'error': 'Subscription plan ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get subscription plan
        try:
            plan = SubscriptionPlan.objects.get(id=subscription_plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Subscription plan not found or inactive'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get vendor
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Vendor profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate expiry date
        expiry_date = calculate_expiry_date(plan.subscription_type)
        
        # Generate test order ID
        order_id = f"order_test_{uuid.uuid4().hex[:16]}"
        
        # Create VendorSubscription record
        vendor_subscription = VendorSubscription.objects.create(
            vendor=vendor,
            subscription_plan=plan,
            expiry_date=expiry_date,
            status='pending',
            razorpay_order_id=order_id,
            amount=plan.amount,
            start_date=timezone.now()  # Set start date now
        )
        
        # Return response for test mode
        response_data = {
            'success': True,
            'order_id': order_id,
            'amount': str(plan.amount * 100),  # In paise for Razorpay
            'currency': 'INR',
            'subscription': {
                'id': vendor_subscription.id,
                'plan_name': f"{plan.get_service_type_display()} - {plan.get_subscription_type_display()}",
                'amount': str(plan.amount),
                'expiry_date': expiry_date.isoformat() if expiry_date else None
            },
            'test_mode': True,
            'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_fakekey12345'),
            'instructions': 'Test Mode: Use test card 4111 1111 1111 1111 with any future expiry and any CVV'
        }
        
        # If real Razorpay is enabled, create actual order
        if RAZORPAY_ENABLED and client:
            try:
                amount_paise = int(plan.amount * 100)
                order_data = {
                    'amount': amount_paise,
                    'currency': 'INR',
                    'receipt': f'sub_{plan.id}_{vendor.id}',
                    'payment_capture': 1,
                    'notes': {
                        'subscription_id': vendor_subscription.id,
                        'vendor_id': vendor.id
                    }
                }
                
                real_order = client.order.create(data=order_data)
                response_data['order_id'] = real_order['id']
                response_data['test_mode'] = False
                response_data['razorpay_key_id'] = getattr(settings, 'RAZORPAY_KEY_ID', '')
                
                # Update with real order ID
                vendor_subscription.razorpay_order_id = real_order['id']
                vendor_subscription.save()
                
            except Exception as e:
                print(f"Real Razorpay order failed: {e}")
                # Continue with test mode
        
        return Response(response_data)
        
    except Exception as e:
        print(f"Error creating order: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """
    Verify payment (Test mode compatible)
    """
    try:
        data = request.data
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_payment_id = data.get('razorpay_payment_id', f"pay_test_{uuid.uuid4().hex[:16]}")
        razorpay_signature = data.get('razorpay_signature', f"sig_test_{uuid.uuid4().hex[:32]}")
        subscription_id = data.get('subscription_id')
        
        if not razorpay_order_id or not subscription_id:
            return Response({
                'success': False,
                'error': 'Missing required parameters'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get vendor subscription
        try:
            vendor_subscription = VendorSubscription.objects.get(
                id=subscription_id,
                vendor__user=request.user
            )
        except VendorSubscription.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Subscription not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # In test mode, always succeed
        # In real mode, verify signature
        is_valid = True
        if RAZORPAY_ENABLED and not TEST_MODE:
            # Verify Razorpay signature
            try:
                body = f"{razorpay_order_id}|{razorpay_payment_id}"
                generated_signature = hmac.new(
                    getattr(settings, 'RAZORPAY_KEY_SECRET', '').encode(),
                    body.encode(),
                    hashlib.sha256
                ).hexdigest()
                
                is_valid = generated_signature == razorpay_signature
            except:
                is_valid = False
        
        if not is_valid:
            vendor_subscription.status = 'failed'
            vendor_subscription.save()
            return Response({
                'success': False,
                'error': 'Invalid payment signature',
                'test_mode': TEST_MODE
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update vendor subscription
        vendor_subscription.razorpay_payment_id = razorpay_payment_id
        vendor_subscription.razorpay_signature = razorpay_signature
        vendor_subscription.status = 'active'
        vendor_subscription.start_date = timezone.now()
        vendor_subscription.save()
        
        # Update vendor
        vendor = vendor_subscription.vendor
        vendor.subscription_status = 'active'
        vendor.subscription_expiry = vendor_subscription.expiry_date
        vendor.current_subscription = vendor_subscription.subscription_plan
        vendor.save()
        
        return Response({
            'success': True,
            'message': 'Payment verified and subscription activated successfully',
            'test_mode': TEST_MODE,
            'subscription': {
                'id': vendor_subscription.id,
                'status': vendor_subscription.status,
                'start_date': vendor_subscription.start_date,
                'expiry_date': vendor_subscription.expiry_date,
                'days_remaining': vendor_subscription.days_remaining,
                'plan': {
                    'id': vendor_subscription.subscription_plan.id,
                    'service_type': vendor_subscription.subscription_plan.get_service_type_display(),
                    'subscription_type': vendor_subscription.subscription_plan.get_subscription_type_display(),
                    'amount': str(vendor_subscription.subscription_plan.amount)
                }
            },
            'vendor': {
                'subscription_status': vendor.subscription_status,
                'subscription_expiry': vendor.subscription_expiry,
                'business_name': vendor.business_name
            }
        })
        
    except Exception as e:
        print(f"Error verifying payment: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_free_trial(request):
    """
    Start 14-day free trial for vendor
    """
    try:
        # Get vendor
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Vendor profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if already on trial or has active subscription
        if vendor.subscription_status == 'active' and vendor.subscription_expiry and vendor.subscription_expiry > timezone.now():
            return Response({
                'success': False,
                'error': 'You already have an active subscription'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if vendor.subscription_status == 'trial' and vendor.trial_end_date and vendor.trial_end_date > timezone.now():
            return Response({
                'success': False,
                'error': 'You are already on a free trial'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Start 14-day free trial
        vendor.subscription_status = 'trial'
        vendor.trial_start_date = timezone.now()
        vendor.trial_end_date = timezone.now() + timedelta(days=14)
        vendor.save()
        
        return Response({
            'success': True,
            'message': '14-day free trial started successfully',
            'trial': {
                'start_date': vendor.trial_start_date,
                'end_date': vendor.trial_end_date,
                'days_remaining': max(0, (vendor.trial_end_date - timezone.now()).days) if vendor.trial_end_date else 0
            }
        })
        
    except Exception as e:
        print(f"Error starting free trial: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subscription_status(request):
    """
    Get current subscription status of vendor
    """
    try:
        # Get vendor
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Vendor profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get active subscription if exists
        active_subscription = None
        if vendor.subscription_status == 'active' and vendor.subscription_expiry and vendor.subscription_expiry > timezone.now():
            active_subscription = VendorSubscription.objects.filter(
                vendor=vendor,
                status='active'
            ).order_by('-created_at').first()
        
        # Get subscription history
        subscription_history = VendorSubscription.objects.filter(
            vendor=vendor
        ).order_by('-created_at')[:10]
        
        history = []
        for sub in subscription_history:
            history.append({
                'id': sub.id,
                'plan_name': f"{sub.subscription_plan.get_service_type_display()} - {sub.subscription_plan.get_subscription_type_display()}",
                'amount': str(sub.amount),
                'status': sub.status,
                'start_date': sub.start_date,
                'expiry_date': sub.expiry_date,
                'created_at': sub.created_at
            })
        
        # Check trial status
        is_on_trial = False
        trial_days_remaining = 0
        if vendor.subscription_status == 'trial' and vendor.trial_end_date:
            is_on_trial = vendor.trial_end_date > timezone.now()
            if is_on_trial:
                trial_days_remaining = max(0, (vendor.trial_end_date - timezone.now()).days)
        
        response_data = {
            'success': True,
            'vendor': {
                'business_name': vendor.business_name,
                'email': vendor.email,
                'service_type': vendor.service_type,
                'subscription_status': vendor.subscription_status,
                'subscription_expiry': vendor.subscription_expiry,
                'has_active_subscription': vendor.subscription_status == 'active' and vendor.subscription_expiry and vendor.subscription_expiry > timezone.now(),
                'is_on_trial': is_on_trial,
                'trial_days_remaining': trial_days_remaining,
                'trial_end_date': vendor.trial_end_date
            }
        }
        
        if active_subscription:
            response_data['active_subscription'] = {
                'id': active_subscription.id,
                'plan': {
                    'id': active_subscription.subscription_plan.id,
                    'service_type': active_subscription.subscription_plan.get_service_type_display(),
                    'subscription_type': active_subscription.subscription_plan.get_subscription_type_display(),
                    'amount': str(active_subscription.subscription_plan.amount)
                },
                'start_date': active_subscription.start_date,
                'expiry_date': active_subscription.expiry_date,
                'days_remaining': max(0, (active_subscription.expiry_date - timezone.now()).days) if active_subscription.expiry_date else 0
            }
        
        response_data['subscription_history'] = history
        
        return Response(response_data)
        
    except Exception as e:
        print(f"Error getting subscription status: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_available_plans(request):
    """
    Get all available subscription plans for vendor's service type
    """
    try:
        # Get vendor
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Vendor profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get subscription plans for vendor's service type
        plans = SubscriptionPlan.objects.filter(
            is_active=True
        ).order_by('amount')
        
        # If vendor has specific service type, filter by it
        if vendor.service_type:
            plans = plans.filter(service_type=vendor.service_type)
        
        plans_data = []
        for plan in plans:
            plans_data.append({
                'id': plan.id,
                'service_type': plan.get_service_type_display(),
                'subscription_type': plan.get_subscription_type_display(),
                'amount': str(plan.amount),
                'description': plan.description,
                'duration_days': get_duration_days(plan.subscription_type),
                'monthly_cost': calculate_monthly_cost(plan.amount, plan.subscription_type),
                'features': get_plan_features(plan.amount)
            })
        
        return Response({
            'success': True,
            'vendor_service_type': vendor.service_type,
            'plans': plans_data,
            'total_plans': len(plans_data)
        })
        
    except Exception as e:
        print(f"Error getting available plans: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def simulate_test_payment(request):
    """
    Simulate test payment without Razorpay popup
    """
    try:
        data = request.data
        subscription_plan_id = data.get('subscription_plan_id')
        
        if not subscription_plan_id:
            return Response({
                'success': False,
                'error': 'Subscription plan ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get subscription plan
        try:
            plan = SubscriptionPlan.objects.get(id=subscription_plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Subscription plan not found or inactive'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get vendor
        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Vendor profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate expiry date
        expiry_date = calculate_expiry_date(plan.subscription_type)
        
        # Create subscription directly (simulating payment)
        vendor_subscription = VendorSubscription.objects.create(
            vendor=vendor,
            subscription_plan=plan,
            expiry_date=expiry_date,
            status='active',
            razorpay_order_id=f"test_order_{uuid.uuid4().hex[:16]}",
            razorpay_payment_id=f"test_payment_{uuid.uuid4().hex[:16]}",
            razorpay_signature=f"test_sig_{uuid.uuid4().hex[:32]}",
            amount=plan.amount,
            start_date=timezone.now()
        )
        
        # Update vendor
        vendor.subscription_status = 'active'
        vendor.subscription_expiry = expiry_date
        vendor.current_subscription = plan
        vendor.save()
        
        return Response({
            'success': True,
            'message': 'Test subscription activated successfully',
            'subscription': {
                'id': vendor_subscription.id,
                'status': vendor_subscription.status,
                'start_date': vendor_subscription.start_date,
                'expiry_date': vendor_subscription.expiry_date,
                'days_remaining': max(0, (vendor_subscription.expiry_date - timezone.now()).days) if vendor_subscription.expiry_date else 0,
                'plan': {
                    'service_type': plan.get_service_type_display(),
                    'subscription_type': plan.get_subscription_type_display(),
                    'amount': str(plan.amount)
                }
            }
        })
        
    except Exception as e:
        print(f"Error in test payment: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['POST'])
def razorpay_webhook(request):
    """
    Handle Razorpay webhook events
    """
    if not RAZORPAY_ENABLED:
        return Response({'status': 'razorpay_not_configured'}, status=status.HTTP_200_OK)
    
    try:
        webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
        received_signature = request.headers.get('X-Razorpay-Signature', '')
        
        # Verify webhook signature
        body = request.body.decode('utf-8')
        expected_signature = hmac.new(
            webhook_secret.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if received_signature != expected_signature:
            return Response({'status': 'invalid_signature'}, status=status.HTTP_400_BAD_REQUEST)
        
        event = json.loads(body)
        event_type = event.get('event')
        
        # Handle different webhook events
        if event_type == 'payment.captured':
            payment = event.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = payment.get('order_id')
            payment_id = payment.get('id')
            
            # Update subscription status
            try:
                vendor_subscription = VendorSubscription.objects.get(
                    razorpay_order_id=order_id,
                    razorpay_payment_id__isnull=True
                )
                vendor_subscription.razorpay_payment_id = payment_id
                vendor_subscription.status = 'active'
                vendor_subscription.start_date = timezone.now()
                vendor_subscription.save()
                
                # Update vendor
                vendor = vendor_subscription.vendor
                vendor.subscription_status = 'active'
                vendor.subscription_expiry = vendor_subscription.expiry_date
                vendor.current_subscription = vendor_subscription.subscription_plan
                vendor.save()
                
                print(f"Webhook: Subscription {vendor_subscription.id} activated via webhook")
                
            except VendorSubscription.DoesNotExist:
                pass
            
        elif event_type == 'payment.failed':
            payment = event.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = payment.get('order_id')
            
            # Mark subscription as failed
            try:
                vendor_subscription = VendorSubscription.objects.get(
                    razorpay_order_id=order_id,
                    status='pending'
                )
                vendor_subscription.status = 'failed'
                vendor_subscription.save()
                print(f"Webhook: Subscription {vendor_subscription.id} marked as failed")
            except VendorSubscription.DoesNotExist:
                pass
        
        return Response({'status': 'success'})
        
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Helper functions
def calculate_expiry_date(subscription_type):
    """Calculate expiry date based on subscription type"""
    today = timezone.now()
    
    duration_map = {
        '1 Month': 30,
        '3 Months': 90,
        '6 Months': 180,
        '1 year': 365
    }
    
    days = duration_map.get(subscription_type, 30)
    return today + timedelta(days=days)

def get_duration_days(subscription_type):
    """Get duration in days"""
    duration_map = {
        '1 Month': 30,
        '3 Months': 90,
        '6 Months': 180,
        '1 year': 365
    }
    return duration_map.get(subscription_type, 30)

def calculate_monthly_cost(amount, subscription_type):
    """Calculate monthly cost"""
    duration_days = get_duration_days(subscription_type)
    monthly_days = 30
    monthly_cost = (amount / duration_days) * monthly_days
    return round(monthly_cost, 2)

def get_plan_features(amount):
    """Get features based on plan amount"""
    if amount <= 500:
        return [
            "Basic Dashboard",
            "Up to 50 Products",
            "Email Support",
            "Order Management",
            "Sales Reports"
        ]
    elif amount <= 2000:
        return [
            "Advanced Dashboard",
            "Up to 500 Products",
            "Priority Support",
            "Bulk Upload",
            "Advanced Analytics",
            "Marketing Tools"
        ]
    else:
        return [
            "Enterprise Dashboard",
            "Unlimited Products",
            "24/7 Phone Support",
            "API Access",
            "Custom Reports",
            "Dedicated Account Manager",
            "Training Sessions"
        ]
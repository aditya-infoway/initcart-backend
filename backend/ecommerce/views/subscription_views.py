from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Q  # ADD THIS IMPORT
from datetime import timedelta
import razorpay
import hmac
import hashlib
from django.conf import settings
from ecommerce.models.subscription import SubscriptionPlan
from ecommerce.models.vendor_subscription import VendorSubscription
from ecommerce.serializers.subscription_serializers import (
    SubscriptionPlanSerializer, 
    VendorSubscriptionSerializer
)
from ecommerce.models.vendor import Vendor  # ADD THIS IMPORT

# Initialize Razorpay client
try:
    razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
except:
    razorpay_client = None

class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_superuser

# Admin Views
class SubscriptionPlanListCreateAPI(generics.ListCreateAPIView):
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    
    def get_queryset(self):
        return SubscriptionPlan.objects.all()
    
    def perform_create(self, serializer):
        serializer.save()

class SubscriptionPlanRetrieveUpdateDestroyAPI(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    queryset = SubscriptionPlan.objects.all()
    lookup_field = 'id'

# Vendor Views
class VendorSubscriptionCheckAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            try:
                vendor = request.user.vendor
            except:
                return Response({
                    'has_active_subscription': False,
                    'message': 'Vendor profile not found'
                })
            
            active_subscription = VendorSubscription.objects.filter(
                vendor=vendor,
                is_active=True,
                payment_status='completed',
                end_date__gte=timezone.now()
            ).first()
            
            has_active_subscription = bool(active_subscription)
            
            return Response({
                'has_active_subscription': has_active_subscription,
                # ✅ end_date direct bhi return karo
                'end_date': active_subscription.end_date.isoformat() if active_subscription else None,
                'current_subscription': VendorSubscriptionSerializer(active_subscription).data if active_subscription else None
            })
        except Exception as e:
            return Response({
                'has_active_subscription': False,
                'error': str(e)
            }, status=200)

class CurrentSubscriptionAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            vendor = request.user.vendor
            subscription = VendorSubscription.objects.filter(
                vendor=vendor,
                is_active=True,
                end_date__gte=timezone.now()
            ).first()
            
            if subscription:
                return Response(VendorSubscriptionSerializer(subscription).data)
            return Response({})
        except:
            return Response({})

class ActiveSubscriptionPlansAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            # Get vendor
            try:
                vendor = request.user.vendor
            except Vendor.DoesNotExist:
                # If vendor profile doesn't exist, show all plans
                plans = SubscriptionPlan.objects.filter(is_active=True)
                serializer = SubscriptionPlanSerializer(plans, many=True)
                return Response(serializer.data)
            
            # Get vendor's service type
            vendor_service_type = vendor.service_type
            
            # Filter plans based on vendor's service type
            if vendor_service_type:
                # Show plans matching vendor's service type OR 'all' type
                plans = SubscriptionPlan.objects.filter(
                    is_active=True
                ).filter(
                    Q(service_type=vendor_service_type) | 
                    Q(service_type='all')
                ).order_by('amount')
            else:
                # If vendor doesn't have service type, show all active plans
                plans = SubscriptionPlan.objects.filter(is_active=True)
            
            serializer = SubscriptionPlanSerializer(plans, many=True)
            return Response(serializer.data)
        except Exception as e:
            print(f"Error fetching plans: {e}")
            return Response([], status=200)

# class CreateRazorpayOrderAPI(APIView):
#     permission_classes = [permissions.IsAuthenticated]
    
#     def post(self, request):
#         # For now, return dummy response for testing
#         try:
#             data = request.data
#             amount = data.get('amount', 0)
#             subscription_plan_id = data.get('subscription_plan_id')
            
#             # For testing, create a dummy order ID
#             order_id = f"order_test_{int(timezone.now().timestamp())}"
            
#             return Response({
#                 'id': order_id,
#                 'amount': amount,
#                 'currency': 'INR'
#             })
#         except Exception as e:
#             return Response({'error': str(e)}, status=400)
import logging

logger = logging.getLogger(__name__)
class CreateRazorpayOrderAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            subscription_plan_id = request.data.get("subscription_plan_id")
            if not subscription_plan_id:
                return Response({"error": "subscription_plan_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Fetch subscription plan
            try:
                plan = SubscriptionPlan.objects.get(id=subscription_plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response({"error": "Subscription plan not found"}, status=status.HTTP_404_NOT_FOUND)

            amount = int(plan.amount) * 100  # Convert to paisa

            # Create Razorpay client
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

            # Try creating Razorpay order
            try:
                razorpay_order = client.order.create({
                    "amount": amount,
                    "currency": "INR",
                    "payment_capture": 1
                })

                return Response({
                    "order_id": razorpay_order.get("id"),
                    "amount": razorpay_order.get("amount"),
                    "currency": razorpay_order.get("currency"),
                    "key": settings.RAZORPAY_KEY_ID
                })

            except Exception as re:  # catch all Razorpay exceptions
                logger.error(f"Razorpay API error: {str(re)}")
                return Response({
                    "error": "Razorpay service is currently unavailable. Please try again later."
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        except Exception as e:
            logger.exception("Unexpected error in CreateRazorpayOrderAPI")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyPaymentAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(csrf_exempt)
    def post(self, request):
        try:
            data = request.data
            subscription_plan_id = data.get('subscription_plan_id')
            
            if not subscription_plan_id:
                return Response({
                    'success': False,
                    'error': 'Subscription plan ID is required'
                }, status=400)
            
            # Get vendor
            try:
                vendor = request.user.vendor
            except:
                return Response({
                    'success': False,
                    'error': 'Vendor profile not found'
                }, status=400)
            
            # Get subscription plan
            try:
                subscription_plan = SubscriptionPlan.objects.get(id=subscription_plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Subscription plan not found'
                }, status=404)
            
            # Check if vendor already has active subscription
            existing_active_subscription = VendorSubscription.objects.filter(
                vendor=vendor,
                is_active=True,
                payment_status='completed',
                end_date__gte=timezone.now()
            ).exists()
            
            if existing_active_subscription:
                return Response({
                    'success': False,
                    'error': 'You already have an active subscription'
                }, status=400)
            
            # Calculate end date based on subscription type
            start_date = timezone.now()
            
            # Map subscription type to days
            duration_map = {
                '1 Month': 30,
                '3 Months': 90,
                '6 Months': 180,
                '1 year': 365,
                'Free Trial': 7
            }
            
            days = duration_map.get(subscription_plan.subscription_type, 30)
            end_date = start_date + timedelta(days=days)
            
            # Create vendor subscription
            vendor_subscription = VendorSubscription.objects.create(
                vendor=vendor,
                subscription_plan=subscription_plan,
                payment_status='completed',
                is_active=True,
                start_date=start_date,  # Explicitly set
                end_date=end_date  # Explicitly set
            )
            
            return Response({
                'success': True,
                'message': 'Payment verified successfully',
                'subscription': VendorSubscriptionSerializer(vendor_subscription).data
            })
            
        except Exception as e:
            print(f"Verify payment error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=400)

class FreeTrialAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            vendor = request.user.vendor
            
            # Check if vendor already has an active subscription
            existing_subscription = VendorSubscription.objects.filter(
                vendor=vendor,
                is_active=True,
                end_date__gte=timezone.now()
            ).exists()
            
            if existing_subscription:
                return Response({'error': 'You already have an active subscription'}, status=400)
            
            # Create or get free trial plan
            free_plan, created = SubscriptionPlan.objects.get_or_create(
                service_type='all',
                subscription_type='Free Trial',
                defaults={
                    'amount': 0,
                    'description': '7-day free trial',
                    'is_active': True
                }
            )
            
            # Create vendor subscription
            vendor_subscription = VendorSubscription.objects.create(
                vendor=vendor,
                subscription_plan=free_plan,
                payment_status='completed',
                is_active=True
            )
            
            return Response({
                'success': True,
                'subscription': VendorSubscriptionSerializer(vendor_subscription).data
            })
        except Exception as e:
            print(f"Free trial error: {e}")
            return Response({'error': str(e)}, status=400)
        
class ServiceSpecificPlansAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            vendor = request.user.vendor
            
            # Get vendor's service type
            vendor_service_type = None
            if vendor.vendor_type == 'service' and vendor.vendor_subtype:
                vendor_service_type = vendor.vendor_subtype
            
            # Query plans
            if vendor_service_type:
                # Get plans specific to vendor's service type plus 'all' plans
                plans = SubscriptionPlan.objects.filter(
                    is_active=True
                ).filter(
                    Q(service_type=vendor_service_type) | 
                    Q(service_type='all')
                ).order_by('amount')
            else:
                # Show all active plans if vendor has no specific service type
                plans = SubscriptionPlan.objects.filter(is_active=True)
            
            serializer = SubscriptionPlanSerializer(plans, many=True)
            return Response({
                'success': True,
                'vendor_service_type': vendor_service_type,
                'plans': serializer.data,
                'total_plans': len(serializer.data)
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e),
                'plans': []
            }, status=200)

# class ServiceSpecificPlansAPI(APIView):
#     permission_classes = [permissions.IsAuthenticated]
    
#     def get(self, request):
#         try:
#             vendor = request.user.vendor
            
#             # Get vendor's service type
#             vendor_service_type = None
#             if vendor.vendor_type == 'service' and vendor.vendor_subtype:
#                 vendor_service_type = vendor.vendor_subtype
            
#             # Query plans
#             if vendor_service_type:
#                 # Get plans specific to vendor's service type plus 'all' plans
#                 plans = SubscriptionPlan.objects.filter(
#                     is_active=True
#                 ).filter(
#                     Q(service_type=vendor_service_type) | 
#                     Q(service_type='all')
#                 ).order_by('amount')
#             else:
#                 # Show all active plans if vendor has no specific service type
#                 plans = SubscriptionPlan.objects.filter(is_active=True)
            
#             serializer = SubscriptionPlanSerializer(plans, many=True)
#             return Response({
#                 'success': True,
#                 'vendor_service_type': vendor_service_type,
#                 'plans': serializer.data,
#                 'total_plans': len(serializer.data)
#             })
#         except Exception as e:
#             return Response({
#                 'success': False,
#                 'error': str(e),
#                 'plans': []
#             }, status=200)
        

#for real razorpay integration remove this commented code 
# subscription_views.py CreateRazorpayOrderAPI update for real integration
""" from django.conf import settings
import razorpay

class CreateRazorpayOrderAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(csrf_exempt)
    def post(self, request):
        try:
            data = request.data
            amount = data.get('amount', 0)
            subscription_plan_id = data.get('subscription_plan_id')
            
            if not subscription_plan_id or not amount:
                return Response({
                    'success': False,
                    'error': 'Subscription plan ID and amount are required'
                }, status=400)
            
            # Get subscription plan
            try:
                plan = SubscriptionPlan.objects.get(id=subscription_plan_id, is_active=True)
            except SubscriptionPlan.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Subscription plan not found or inactive'
                }, status=404)
            
            # Get vendor
            try:
                vendor = request.user.vendor
            except:
                return Response({
                    'success': False,
                    'error': 'Vendor profile not found'
                }, status=400)
            
            # Initialize Razorpay client
            try:
                razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            except:
                return Response({
                    'success': False,
                    'error': 'Razorpay configuration error'
                }, status=500)
            
            # Create Razorpay order
            order_data = {
                'amount': int(amount),  # Amount in paise
                'currency': 'INR',
                'receipt': f'sub_{plan.id}_{vendor.id}',
                'payment_capture': 1,
                'notes': {
                    'subscription_plan_id': plan.id,
                    'vendor_id': vendor.id,
                    'business_name': vendor.business_name
                }
            }
            
            order = razorpay_client.order.create(data=order_data)
            
            # Create pending subscription record
            vendor_subscription = VendorSubscription.objects.create(
                vendor=vendor,
                subscription_plan=plan,
                payment_status='pending',
                razorpay_order_id=order['id'],
                amount=plan.amount
            )
            
            return Response({
                'success': True,
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key_id': settings.RAZORPAY_KEY_ID,
                'subscription_id': vendor_subscription.id
            })
            
        except Exception as e:
            print(f"Create order error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=400) 
 """
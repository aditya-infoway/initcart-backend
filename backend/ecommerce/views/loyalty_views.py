# ecommerce/views/loyalty_views.py

from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

from users.models import User
from ecommerce.models.loyalty import LoyaltyPointsConfig, LoyaltyPointsTransaction
from ecommerce.serializers.loyalty_serializers import (
    LoyaltyPointsConfigSerializer, 
    LoyaltyPointsTransactionSerializer,
    LoyaltyPointsCalculatorSerializer,
    LoyaltyPointsReportSerializer
)

# Solution 1: ecommerce/permissions.py से import करें
from ecommerce.permissions import IsSuperAdmin

class LoyaltyPointsConfigViewSet(viewsets.ModelViewSet):
    """CRUD for loyalty points configuration (Super Admin only)"""
    serializer_class = LoyaltyPointsConfigSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['points_type', 'earned_on', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['priority', 'created_at', 'valid_from']
    ordering = ['-priority', '-created_at']
    
    def get_queryset(self):
        return LoyaltyPointsConfig.objects.all()
    
    def perform_create(self, serializer):
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle active status"""
        config = self.get_object()
        config.is_active = not config.is_active
        config.save()
        
        return Response({
            'success': True,
            'message': f"Configuration {'activated' if config.is_active else 'deactivated'}",
            'is_active': config.is_active
        })
    
    @action(detail=False, methods=['get'])
    def active_rules(self, request):
        """Get all active rules"""
        from django.utils import timezone
        
        active_rules = LoyaltyPointsConfig.objects.filter(
            is_active=True,
            valid_from__lte=timezone.now()
        ).exclude(
            valid_to__lt=timezone.now()
        ).order_by('-priority')
        
        serializer = self.get_serializer(active_rules, many=True)
        return Response({
            'success': True,
            'count': active_rules.count(),
            'data': serializer.data
        })
    
    @action(detail=False, methods=['post'])
    def calculate_points(self, request):
        """Calculate points for an order amount"""
        serializer = LoyaltyPointsCalculatorSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        result = serializer.calculate_points()
        return Response({
            'success': True,
            'data': result
        })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get loyalty points system summary"""
        total_rules = LoyaltyPointsConfig.objects.count()
        active_rules = LoyaltyPointsConfig.objects.filter(is_active=True).count()
        expired_rules = LoyaltyPointsConfig.objects.filter(
            valid_to__lt=timezone.now()
        ).count()
        
        # Points statistics
        total_points_earned = LoyaltyPointsTransaction.objects.filter(
            transaction_type='earned'
        ).aggregate(total=Sum('points'))['total'] or 0
        
        total_points_used = LoyaltyPointsTransaction.objects.filter(
            transaction_type='used'
        ).aggregate(total=Sum('points'))['total'] or 0
        
        active_customers = User.objects.filter(
            role='customer',
            loyalty_transactions__isnull=False
        ).distinct().count()
        
        return Response({
            'success': True,
            'data': {
                'rules': {
                    'total': total_rules,
                    'active': active_rules,
                    'expired': expired_rules
                },
                'points': {
                    'total_earned': total_points_earned,
                    'total_used': total_points_used,
                    'active_points': total_points_earned - total_points_used,
                    'monetary_value': round((total_points_earned - total_points_used) * 0.1, 2)
                },
                'customers': {
                    'with_points': active_customers
                }
            }
        })


class LoyaltyPointsTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """View loyalty points transactions (Super Admin only)"""
    serializer_class = LoyaltyPointsTransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['transaction_type', 'customer', 'config']
    search_fields = ['customer__username', 'customer__email', 'description']
    ordering_fields = ['created_at', 'points']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return LoyaltyPointsTransaction.objects.select_related(
            'customer', 'order', 'config'
        ).all()
    
    @action(detail=False, methods=['post'])
    def adjust_points(self, request):
        """Manually adjust customer points (Super Admin only)"""
        from ecommerce.models.customer import CustomerProfile
        
        customer_id = request.data.get('customer_id')
        points = request.data.get('points')
        reason = request.data.get('reason', 'Manual adjustment')
        
        if not customer_id or not points:
            return Response({
                'success': False,
                'message': 'Customer ID and points are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from users.models import User
            customer = User.objects.get(id=customer_id, role='customer')
            
            # Get or create customer profile
            profile, created = CustomerProfile.objects.get_or_create(
                user=customer,
                defaults={
                    'full_name': customer.get_full_name() or customer.username,
                    'email': customer.email
                }
            )
            
            # Calculate current balance
            current_balance = profile.loyalty_points
            
            # Create adjustment transaction
            transaction = LoyaltyPointsTransaction.objects.create(
                customer=customer,
                points=abs(int(points)),
                transaction_type='adjusted',
                description=f"Admin adjustment: {reason}",
                balance_after=current_balance + int(points)
            )
            
            # Update customer's points in profile (optional)
            # You can store total points in profile or calculate dynamically
            
            return Response({
                'success': True,
                'message': f"Points adjusted successfully",
                'transaction_id': transaction.id,
                'old_balance': current_balance,
                'new_balance': current_balance + int(points),
                'adjustment': int(points)
            })
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Customer not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error adjusting points: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def customer_report(self, request):
        """Get customer-wise points report"""
        customer_id = request.query_params.get('customer_id')
        
        if customer_id:
            try:
                from users.models import User
                customer = User.objects.get(id=customer_id, role='customer')
                
                transactions = LoyaltyPointsTransaction.objects.filter(
                    customer=customer
                ).order_by('-created_at')
                
                total_earned = transactions.filter(
                    transaction_type='earned'
                ).aggregate(total=Sum('points'))['total'] or 0
                
                total_used = transactions.filter(
                    transaction_type='used'
                ).aggregate(total=Sum('points'))['total'] or 0
                
                current_balance = total_earned - total_used
                
                serializer = self.get_serializer(transactions, many=True)
                
                return Response({
                    'success': True,
                    'data': {
                        'customer': {
                            'id': customer.id,
                            'username': customer.username,
                            'email': customer.email
                        },
                        'points_summary': {
                            'total_earned': total_earned,
                            'total_used': total_used,
                            'current_balance': current_balance,
                            'monetary_value': round(current_balance * 0.1, 2)
                        },
                        'transactions': serializer.data
                    }
                })
                
            except User.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Customer not found'
                }, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'success': False,
            'message': 'Customer ID is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def generate_report(self, request):
        """Generate loyalty points report"""
        serializer = LoyaltyPointsReportSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        query = Q()
        
        # Apply filters
        if data.get('start_date'):
            query &= Q(created_at__date__gte=data['start_date'])
        
        if data.get('end_date'):
            query &= Q(created_at__date__lte=data['end_date'])
        
        if data.get('customer_id'):
            query &= Q(customer_id=data['customer_id'])
        
        if data.get('transaction_type'):
            query &= Q(transaction_type=data['transaction_type'])
        
        # Get transactions
        transactions = LoyaltyPointsTransaction.objects.filter(query).select_related(
            'customer', 'order', 'config'
        )
        
        # Calculate summary
        summary = transactions.aggregate(
            total_points=Sum('points'),
            transaction_count=Count('id')
        )
        
        # Group by transaction type
        by_type = transactions.values('transaction_type').annotate(
            total_points=Sum('points'),
            count=Count('id')
        )
        
        # Group by date
        by_date = transactions.extra(
            {'date': "DATE(created_at)"}
        ).values('date').annotate(
            total_points=Sum('points'),
            count=Count('id')
        ).order_by('-date')
        
        serializer = self.get_serializer(transactions, many=True)
        
        return Response({
            'success': True,
            'data': {
                'summary': summary,
                'by_transaction_type': list(by_type),
                'by_date': list(by_date),
                'transactions': serializer.data
            }
        })


class LoyaltyPointsAPIView(APIView):
    """Public API for customers to check their points"""
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
            
            # Get recent transactions
            transactions = LoyaltyPointsTransaction.objects.filter(
                customer=request.user
            ).order_by('-created_at')[:20]
            
            # Calculate points from config rules (optional)
            active_rules = LoyaltyPointsConfig.objects.filter(
                is_active=True,
                valid_from__lte=timezone.now()
            ).exclude(
                valid_to__lt=timezone.now()
            ).count()
            
            serializer = LoyaltyPointsTransactionSerializer(transactions, many=True)
            
            return Response({
                'success': True,
                'data': {
                    'available_points': profile.loyalty_points,
                    'points_value': profile.available_points_value,
                    'active_rules_count': active_rules,
                    'total_spent': profile.total_spent,
                    'total_orders': profile.total_orders,
                    'transactions': serializer.data
                }
            })
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error fetching loyalty points: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
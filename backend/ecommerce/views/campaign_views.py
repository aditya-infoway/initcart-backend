# ecommerce/views/campaign_views.py
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from django.db.models import Q, Count
from datetime import date, datetime, timedelta
import json
from PIL import Image
import io
from django.core.files.base import ContentFile
import os

from ecommerce.models.campaign import Campaign, CampaignParticipation, CampaignProduct
from ecommerce.models.vendor import Vendor
from ecommerce.models.product import Product
from ecommerce.serializers.campaign_serializers import (
    CampaignSerializer, CampaignParticipationSerializer,
    CampaignProductSerializer, VendorCampaignParticipationSerializer,
    SuperAdminCampaignParticipationDetailSerializer
)
from ecommerce.serializers.vendor_serializers import VendorSerializer
from django.core.files.storage import default_storage
from PIL import Image
import io

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_vendor_for_user(user):
    """
    Helper function to get vendor for user
    Returns Vendor object or None
    """
    # Method 1: Check vendor_profile (if related_name exists)
    if hasattr(user, 'vendor_profile'):
        return user.vendor_profile
    
    # Method 2: Try to get vendor directly by user
    try:
        vendor = Vendor.objects.get(user=user)
        return vendor
    except Vendor.DoesNotExist:
        pass
    
    # Method 3: Try by email
    try:
        vendor = Vendor.objects.get(email=user.email)
        return vendor
    except Vendor.DoesNotExist:
        pass
    
    return None

def get_vendors_for_dropdown(campaign=None, current_date=None):
    """
    Get vendors for dropdown based on date logic
    NEW LOGIC: जिस vendor को आज किसी भी campaign में select/participate कर दिया गया है,
    वो आज के लिए दूसरे campaign में नहीं दिखेगा।
    """
    if current_date is None:
        current_date = date.today()
    
    # Get all active and approved vendors
    all_vendors = Vendor.objects.filter(status='active', vendor_type='product', is_approved=True)
    
    # CRITICAL FIX: Get vendors who have been selected in ANY campaign today
    # This includes both: participated AND selected by super admin
    
    # 1. Vendors who have participated today (in any campaign)
    vendors_participated_today = CampaignParticipation.objects.filter(
        applied_at__date=current_date
    ).values_list('vendor_id', flat=True)
    
    # 2. Vendors who are selected in any campaign (created/updated today)
    # We need to check campaigns that were created/updated today
    today_start = datetime.combine(current_date, datetime.min.time())
    today_end = datetime.combine(current_date, datetime.max.time())
    
    campaigns_created_today = Campaign.objects.filter(
        Q(created_at__date=current_date) | Q(updated_at__date=current_date)
    )
    
    vendors_selected_today = set()
    for camp in campaigns_created_today:
        vendors_selected_today.update(camp.selected_vendors.values_list('id', flat=True))
    
    # 3. Combine both lists - ये vendors आज के लिए ब्लॉक हैं
    blocked_vendor_ids = set(list(vendors_participated_today) + list(vendors_selected_today))
    
    print(f"DEBUG: Today's date: {current_date}")
    print(f"DEBUG: Total vendors: {all_vendors.count()}")
    print(f"DEBUG: Vendors participated today: {len(vendors_participated_today)}")
    print(f"DEBUG: Vendors selected today: {len(vendors_selected_today)}")
    print(f"DEBUG: Blocked vendors: {len(blocked_vendor_ids)}")
    
    # Exclude blocked vendors
    available_vendors = all_vendors.exclude(id__in=blocked_vendor_ids)
    
    print(f"DEBUG: Available vendors: {available_vendors.count()}")
    
    return available_vendors

# =========================================================
# UPCOMING DEAL COUNTER
# =========================================================

class UpcomingDealsCountAPI(APIView):
    """Get count of upcoming deals and next deal details"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        now = timezone.now()
        
        # Get upcoming deals (starting in future)
        upcoming_deals = Campaign.objects.filter(
            start_datetime__gt=now,
            status__in=['Draft', 'Active']
        ).order_by('start_datetime')
        
        # Next deal
        next_deal = upcoming_deals.first()
        
        # Count by type
        flash_count = upcoming_deals.filter(campaign_type='Flash').count()
        deal_of_day_count = upcoming_deals.filter(campaign_type='Deal of the Day').count()
        featured_count = upcoming_deals.filter(campaign_type='Featured').count()
        
        response_data = {
            'total_upcoming': upcoming_deals.count(),
            'by_type': {
                'flash': flash_count,
                'deal_of_day': deal_of_day_count,
                'featured': featured_count
            },
            'next_deal': None
        }
        
        if next_deal:
            time_diff = next_deal.start_datetime - now
            response_data['next_deal'] = {
                'id': next_deal.id,
                'name': next_deal.campaign_name,
                'type': next_deal.campaign_type,
                'start_datetime': next_deal.start_datetime,
                'countdown_seconds': int(time_diff.total_seconds())
            }
        
        return Response(response_data, status=status.HTTP_200_OK)

# =========================================================
# SUPER ADMIN VIEWS
# =========================================================

class CampaignListCreateAPI(generics.ListCreateAPIView):
    serializer_class = CampaignSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        now = timezone.now()
        queryset = Campaign.objects.all().order_by('-created_at')
        
        # ✅ FIX: Campaign type filter properly apply karo
        campaign_type = self.request.query_params.get('campaign_type')
        if campaign_type:
            # Sirf exact match karo, case-sensitive bhi ho sakta hai
            queryset = queryset.filter(campaign_type__iexact=campaign_type)
            print(f"DEBUG: Filtering by campaign_type: {campaign_type}")
            print(f"DEBUG: Found {queryset.count()} campaigns")
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        else:
            # By default, hide expired campaigns
            queryset = queryset.exclude(
                Q(status='Expired') | 
                Q(end_datetime__lt=now, status='Inactive')
            )
        
        return queryset
    
    def perform_create(self, serializer):
        # Save with creator
        campaign = serializer.save(created_by=self.request.user)
        
        # Handle vendor selection logic
        selected_vendors = self.request.data.get('selected_vendors', [])
        if selected_vendors:
            campaign.selected_vendors.set(selected_vendors)
            campaign.save()
            
class CampaignDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def perform_update(self, serializer):
        campaign = serializer.save()
        if campaign.campaign_type == 'Deal of the Day' and campaign.status == 'Active':
            # Deactivate all other active Deal of the Day campaigns
            Campaign.objects.filter(
                campaign_type='Deal of the Day',
                status='Active'
            ).exclude(id=campaign.id).update(
                status='Inactive',
                updated_at=timezone.now()
            )
        
        # Update vendor selection if changed
        if 'selected_vendors' in self.request.data:
            selected_vendors = self.request.data.get('selected_vendors', [])
            campaign.selected_vendors.set(selected_vendors)
            campaign.save()    

# =========================================================
# VENDOR SELECTION MANAGEMENT
# =========================================================

class CampaignVendorSelectionAPI(APIView):
    """Manage vendor selection for campaigns"""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            vendor_ids = request.data.get('vendor_ids', [])
            action = request.data.get('action', 'replace')  # add, remove, replace
            
            today = date.today()
            selected_vendors_info = []
            
            if action == 'add':
                # Add vendors to selection
                vendors = Vendor.objects.filter(id__in=vendor_ids, status='active', is_approved=True)
                
                # Check if any vendor has already participated today
                vendors_with_request_today = CampaignParticipation.objects.filter(
                    campaign=campaign,
                    vendor__in=vendors,
                    applied_at__date=today
                ).values_list('vendor_id', flat=True)
                
                valid_vendors = []
                for vendor in vendors:
                    if vendor.id in vendors_with_request_today:
                        selected_vendors_info.append({
                            'id': vendor.id,
                            'name': vendor.business_name,
                            'status': 'already_participated_today',
                            'message': f'{vendor.business_name} has already participated today'
                        })
                    else:
                        valid_vendors.append(vendor)
                        selected_vendors_info.append({
                            'id': vendor.id,
                            'name': vendor.business_name,
                            'status': 'added'
                        })
                
                campaign.selected_vendors.add(*valid_vendors)
                message = f"Added {len(valid_vendors)} vendors to selection"
                
            elif action == 'remove':
                # Remove vendors from selection
                vendors = Vendor.objects.filter(id__in=vendor_ids)
                campaign.selected_vendors.remove(*vendors)
                message = f"Removed {len(vendor_ids)} vendors from selection"
                
                for vendor in vendors:
                    selected_vendors_info.append({
                        'id': vendor.id,
                        'name': vendor.business_name,
                        'status': 'removed'
                    })
                    
            else:
                # Replace selection (default)
                vendors = Vendor.objects.filter(id__in=vendor_ids, status='active', is_approved=True)
                
                # Check if any vendor has already participated today
                vendors_with_request_today = CampaignParticipation.objects.filter(
                    campaign=campaign,
                    vendor__in=vendors,
                    applied_at__date=today
                ).values_list('vendor_id', flat=True)
                
                valid_vendors = []
                for vendor in vendors:
                    if vendor.id in vendors_with_request_today:
                        selected_vendors_info.append({
                            'id': vendor.id,
                            'name': vendor.business_name,
                            'status': 'already_participated_today',
                            'message': f'{vendor.business_name} has already participated today'
                        })
                    else:
                        valid_vendors.append(vendor)
                        selected_vendors_info.append({
                            'id': vendor.id,
                            'name': vendor.business_name,
                            'status': 'selected'
                        })
                
                campaign.selected_vendors.set(valid_vendors)
                message = f"Updated vendor selection with {len(valid_vendors)} vendors"
            
            campaign.save()
            
            return Response({
                'message': message,
                'selected_vendors_count': campaign.selected_vendors.count(),
                'selected_vendors_info': selected_vendors_info,
                'selected_vendors': VendorSerializer(campaign.selected_vendors.all(), many=True).data
            }, status=status.HTTP_200_OK)
            
        except Campaign.DoesNotExist:
            return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
        
class CampaignAvailableVendorsAPI(APIView):
    """Get available vendors for campaign based on GLOBAL date logic"""
    permission_classes = [permissions.IsAdminUser]
    
    def get(self, request, campaign_id=None):
        try:
            campaign = None
            if campaign_id:
                campaign = Campaign.objects.get(id=campaign_id)
            
            target_date_str = request.query_params.get('date')
            
            if target_date_str:
                try:
                    target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
                except ValueError:
                    target_date = date.today()
            else:
                target_date = date.today()
            
            # Get available vendors based on GLOBAL logic
            available_vendors = get_vendors_for_dropdown(campaign, target_date)
            
            # For existing campaign, check which vendors are already selected
            selected_vendor_ids = []
            if campaign:
                selected_vendor_ids = list(campaign.selected_vendors.values_list('id', flat=True))
            
            vendor_data = []
            for vendor in available_vendors:
                # Check if vendor has already participated today (in any campaign)
                has_participated_today = CampaignParticipation.objects.filter(
                    vendor=vendor,
                    applied_at__date=target_date
                ).exists()
                
                # Check if vendor is selected in this specific campaign (if editing)
                is_selected_in_this_campaign = vendor.id in selected_vendor_ids if campaign else False
                
                vendor_data.append({
                    'id': vendor.id,
                    'business_name': vendor.business_name,
                    'email': vendor.email,
                    'phone': vendor.phone,
                    'is_selected': is_selected_in_this_campaign,
                    'has_participated_today': has_participated_today,
                    'products_count': vendor.products.count(),
                    'category_names': list(vendor.products.values_list('category__name', flat=True).distinct())
                })
            
            return Response({
                'date': target_date.strftime('%Y-%m-%d'),
                'total_vendors': available_vendors.count(),
                'selected_vendors_count': len(selected_vendor_ids) if campaign else 0,
                'vendors': vendor_data,
                'logic_info': 'जिस vendor को आज किसी भी campaign में select/participate कर दिया गया है, वो आज के लिए दूसरे campaign में नहीं दिखेगा।'
            }, status=status.HTTP_200_OK)
            
        except Campaign.DoesNotExist:
            return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

# =========================================================
# VENDOR VIEWS
# =========================================================

class VendorCampaignListAPI(generics.ListAPIView):
    serializer_class = CampaignSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        vendor = get_vendor_for_user(self.request.user)
        if not vendor:
            print(f"DEBUG: No vendor found for user {self.request.user.id}")
            return Campaign.objects.none()
        
        now = timezone.now()
        
        # ✅ FIX: Sirf Active campaigns jo expired nahi hui
        campaigns = Campaign.objects.filter(
            status='Active',
            end_datetime__gt=now  # Sirf end date future mein ho
        )
        
        print(f"DEBUG: Total Active campaigns: {campaigns.count()}")
        
        # Filter campaigns where vendor can participate
        available_campaigns = []
        
        for campaign in campaigns:
            print(f"\nDEBUG: Checking campaign {campaign.id}: {campaign.campaign_name}")
            print(f"  Start: {campaign.start_datetime}")
            print(f"  End: {campaign.end_datetime}")
            print(f"  Now: {now}")
            print(f"  Has started: {campaign.start_datetime <= now}")  # Sirf info ke liye
            print(f"  Has ended: {campaign.end_datetime <= now}")
            print(f"  Selected vendors count: {campaign.selected_vendors.count()}")
            
            # Check vendor selection
            if campaign.selected_vendors.exists():
                if vendor in campaign.selected_vendors.all():
                    print(f"  ✅ Vendor {vendor.id} is SELECTED")
                    available_campaigns.append(campaign.id)
                else:
                    print(f"  ❌ Vendor {vendor.id} is NOT selected")
                    # Show selected vendors IDs for debugging
                    selected_ids = list(campaign.selected_vendors.values_list('id', flat=True))
                    print(f"  Selected vendor IDs: {selected_ids}")
            else:
                print(f"  ✅ No vendor restrictions")
                available_campaigns.append(campaign.id)
        
        final_queryset = Campaign.objects.filter(id__in=available_campaigns)
        print(f"\nDEBUG: Final available campaigns count: {final_queryset.count()}")
        
        return final_queryset

class VendorCampaignDetailAPI(generics.RetrieveAPIView):
    serializer_class = CampaignSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        vendor = get_vendor_for_user(self.request.user)
        if not vendor:
            return Campaign.objects.none()
        
        now = timezone.now()
        
        queryset = Campaign.objects.filter(
            Q(status='Active') | Q(status='Draft'),
            start_datetime__lte=now,
            end_datetime__gte=now
        )
        
        # Check if vendor is selected
        if self.request.user.is_superuser:
            return queryset
        
        # For vendors, filter only campaigns they can access
        available_campaigns = []
        for campaign in queryset:
            if campaign.selected_vendors.exists():
                if vendor in campaign.selected_vendors.all():
                    available_campaigns.append(campaign.id)
            else:
                available_campaigns.append(campaign.id)
        
        return Campaign.objects.filter(id__in=available_campaigns)

class ParticipateInCampaignAPI(APIView):
    """Vendor participation with validation"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, campaign_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            campaign = Campaign.objects.get(
                id=campaign_id,
                status='Active',
                start_datetime__lte=timezone.now(),
                end_datetime__gte=timezone.now()
            )
            
            # ✅ CRITICAL FIX: पहले selected_vendors check करो
            if campaign.selected_vendors.exists():
                #  Strict check - सिर्फ selected vendors को allow करो
                if vendor not in campaign.selected_vendors.all():
                    return Response({
                        'error': 'Access Denied! आप इस campaign के लिए selected नहीं हैं। '
                                'केवल selected vendors ही participate कर सकते हैं।'
                    }, status=status.HTTP_403_FORBIDDEN)
            
            # Rest of the code same rahega...
            # Check if already participated today
            today = date.today()
            if CampaignParticipation.objects.filter(
                campaign=campaign,
                vendor=vendor,
                applied_at__date=today
            ).exists():
                return Response({
                    'error': 'You have already sent a participation request today. '
                            'You can send another request tomorrow.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check category match
            campaign_categories = campaign.categories.all()
            vendor_category_ids = vendor.products.values_list('category_id', flat=True).distinct()
            
            common_categories = campaign_categories.filter(id__in=vendor_category_ids).exists()
            if not common_categories:
                category_names = ", ".join([cat.name for cat in campaign_categories])
                return Response({
                    'error': f'You have no products in campaign categories: {category_names}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create participation
            participation = CampaignParticipation.objects.create(
                campaign=campaign,
                vendor=vendor,
                status='Pending'
            )
            
            return Response({
                'message': 'Successfully applied for campaign! Now add your products.',
                'participation': CampaignParticipationSerializer(participation).data,
                'minimum_requirements': {
                    'minimum_products': campaign.minimum_product_limit,
                    'minimum_discount': campaign.minimum_discount
                },
                'note': 'You cannot send another request for this campaign today'
            }, status=status.HTTP_201_CREATED)
            
        except Campaign.DoesNotExist:
            return Response({'error': 'Campaign not found or not active'}, 
                          status=status.HTTP_404_NOT_FOUND)

class AddProductsToCampaignAPI(APIView):
    """Add products to campaign with validation"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, participation_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            participation = CampaignParticipation.objects.get(
                id=participation_id,
                vendor=vendor,
                status='Pending'
            )
            
            campaign = participation.campaign
            products_data = request.data.get('products', [])
            
            if not products_data:
                return Response({'error': 'No products selected'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Check minimum product limit
            current_count = participation.campaign_products.count()
            if current_count + len(products_data) < campaign.minimum_product_limit:
                return Response({
                    'error': f'Minimum {campaign.minimum_product_limit} products required. '
                            f'You have {current_count} products, adding {len(products_data)}.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check maximum limit
            if current_count + len(products_data) > campaign.max_products_per_vendor:
                return Response({
                    'error': f'You can only add {campaign.max_products_per_vendor} products'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            created_products = []
            validation_errors = []
            
            for product_data in products_data:
                product_id = product_data.get('product_id')
                
                if not product_id:
                    continue
                
                try:
                    product = vendor.products.get(id=product_id, status='approved')
                    
                    # Check if already added
                    if CampaignProduct.objects.filter(participation=participation, product=product).exists():
                        continue
                    
                    # Validate discount against minimum
                    discount_type = product_data.get('discount_type')
                    discount_value = product_data.get('discount_value')
                    special_price = product_data.get('special_price')
                    
                    if campaign.minimum_discount > 0:
                        if discount_type == 'percentage':
                            if not discount_value or discount_value < campaign.minimum_discount:
                                validation_errors.append({
                                    'product_id': product_id,
                                    'error': f'Discount must be at least {campaign.minimum_discount}%'
                                })
                                continue
                        elif discount_type == 'flat' and special_price:
                            # Calculate percentage discount
                            product_stock = product.stocks.first()
                            if product_stock:
                                original_price = float(product_stock.selling_price)
                                discount_percentage = ((original_price - float(special_price)) / original_price) * 100
                                
                                if discount_percentage < campaign.minimum_discount:
                                    validation_errors.append({
                                        'product_id': product_id,
                                        'error': f'Discount must be at least {campaign.minimum_discount}% '
                                                f'(current: {discount_percentage:.1f}%)'
                                    })
                                    continue
                    
                    # Create campaign product
                    campaign_product = CampaignProduct.objects.create(
                        participation=participation,
                        product=product,
                        discount_percentage=discount_value if discount_type == 'percentage' else None,
                        special_price=special_price if discount_type == 'flat' else None,
                        deal_of_day_placement=product_data.get('deal_of_day_placement'),
                        status='Pending'
                    )
                    
                    created_products.append({
                        'id': campaign_product.id,
                        'product_id': product.id,
                        'product_name': product.product_name,
                        'original_price': campaign_product.original_price,
                        'final_price': campaign_product.final_price,
                        'status': campaign_product.status
                    })
                    
                except Exception as e:
                    validation_errors.append({
                        'product_id': product_id,
                        'error': str(e)
                    })
                    continue
            
            if not created_products:
                return Response({
                    'error': 'No products were added',
                    'validation_errors': validation_errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'message': f'{len(created_products)} products added successfully!',
                'added_products': created_products,
                'validation_errors': validation_errors,
                'total_added': len(created_products),
                'remaining_slots': campaign.max_products_per_vendor - (current_count + len(created_products)),
                'minimum_requirements_check': {
                    'minimum_products': campaign.minimum_product_limit,
                    'current_products': current_count + len(created_products),
                    'meets_minimum': (current_count + len(created_products)) >= campaign.minimum_product_limit
                }
            }, status=status.HTTP_201_CREATED)
            
        except CampaignParticipation.DoesNotExist:
            return Response({'error': 'Participation not found'}, status=status.HTTP_404_NOT_FOUND)

class VendorCampaignParticipationListAPI(generics.ListAPIView):
    serializer_class = VendorCampaignParticipationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        vendor = get_vendor_for_user(self.request.user)
        
        if not vendor:
            return CampaignParticipation.objects.none()
            
        participations = CampaignParticipation.objects.filter(vendor=vendor).order_by('-applied_at')
        return participations
    
    def get_serializer_context(self):
        """Add request context to serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class RemoveProductFromCampaignAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request, product_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            campaign_product = CampaignProduct.objects.get(
                id=product_id,
                participation__vendor=vendor,
                status='Pending'  # Can only remove pending products
            )
            
            product_name = campaign_product.product.product_name
            campaign_product.delete()
            
            return Response({
                'message': f'Product "{product_name}" removed from campaign'
            }, status=status.HTTP_200_OK)
            
        except CampaignProduct.DoesNotExist:
            return Response({'error': 'Product not found or cannot be removed'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VendorCampaignParticipationDetailAPI(generics.RetrieveAPIView):
    serializer_class = VendorCampaignParticipationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        vendor = get_vendor_for_user(self.request.user)
        
        if not vendor:
            return CampaignParticipation.objects.none()
            
        return CampaignParticipation.objects.filter(vendor=vendor)

class VendorProductDetailsAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, product_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get vendor's product
            product = vendor.products.get(id=product_id, status='approved')
            
            # Get product stock details
            product_stock = product.stocks.first()
            
            response_data = {
                'id': product.id,
                'product_name': product.product_name,
                'category_id': product.category_id,
                'category_name': product.category.name if product.category else '',
                'status': product.status,
                'original_price': float(product_stock.selling_price) if product_stock else 0,
                'mrp': float(product_stock.mrp) if product_stock else 0,
                'stock_quantity': product_stock.stock_quantity if product_stock else 0,
                'stocks': []
            }
            
            # Add all stock variants
            for stock in product.stocks.all():
                response_data['stocks'].append({
                    'id': stock.id,
                    'selling_price': float(stock.selling_price),
                    'mrp': float(stock.mrp),
                    'color': stock.color,
                    'size': stock.size,
                    'stock_quantity': stock.stock_quantity
                })
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except vendor.products.model.DoesNotExist:
            return Response({'error': 'Product not found or not approved'}, 
                          status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# =========================================================
# DEAL OF THE DAY PRODUCT PLACEMENT
# =========================================================

class DealOfDayProductsAPI(APIView):
    """Get products for Deal of the Day with placement"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        now = timezone.now()
        
        # Get active Deal of the Day campaigns
        deal_of_day_campaigns = Campaign.objects.filter(
            campaign_type='Deal of the Day',
            status='Active',
            start_datetime__lte=now,
            end_datetime__gte=now
        )
        
        if not deal_of_day_campaigns.exists():
            return Response({'products': [], 'message': 'No active Deal of the Day'})
        
        campaign = deal_of_day_campaigns.first()
        
        # Get approved campaign products with placement
        campaign_products = CampaignProduct.objects.filter(
            participation__campaign=campaign,
            status='Approved',
            participation__status='Approved'
        ).select_related('product', 'participation__vendor')
        
        # Organize by placement
        main_products = campaign_products.filter(deal_of_day_placement='main')[:5]
        banner_products = campaign_products.filter(deal_of_day_placement='banner')[:3]
        product_list_products = campaign_products.filter(deal_of_day_placement='product_list')[:20]
        
        # If no placement specified, use all
        if not any([main_products.exists(), banner_products.exists(), product_list_products.exists()]):
            all_products = campaign_products[:20]
            main_products = all_products[:5]
            banner_products = all_products[5:8]
            product_list_products = all_products[8:28]
        
        # Serialize data
        main_serializer = CampaignProductSerializer(main_products, many=True)
        banner_serializer = CampaignProductSerializer(banner_products, many=True)
        product_list_serializer = CampaignProductSerializer(product_list_products, many=True)
        
        return Response({
            'campaign': {
                'id': campaign.id,
                'name': campaign.campaign_name,
                'description': campaign.description,
                'end_datetime': campaign.end_datetime
            },
            'products_by_placement': {
                'main': main_serializer.data,
                'banner': banner_serializer.data,
                'product_list': product_list_serializer.data
            },
            'countdown_seconds': int((campaign.end_datetime - now).total_seconds())
        }, status=status.HTTP_200_OK)

class SetDealOfDayPlacementAPI(APIView):
    """Set placement for Deal of the Day products"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, product_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            campaign_product = CampaignProduct.objects.get(
                id=product_id,
                participation__vendor=vendor
            )
            
            # Check if campaign is Deal of the Day
            if campaign_product.participation.campaign.campaign_type != 'Deal of the Day':
                return Response({'error': 'This is not a Deal of the Day campaign'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            placement = request.data.get('placement')
            if placement not in ['main', 'banner', 'product_list']:
                return Response({'error': 'Invalid placement type'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Update placement
            campaign_product.deal_of_day_placement = placement
            campaign_product.save()
            
            return Response({
                'message': f'Product placement set to {placement}',
                'product': CampaignProductSerializer(campaign_product).data
            }, status=status.HTTP_200_OK)
            
        except CampaignProduct.DoesNotExist:
            return Response({'error': 'Product not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

# =========================================================
# CAMPAIGN DASHBOARD
# =========================================================

class CampaignDashboardAPI(APIView):
    """Enhanced dashboard with upcoming deals"""
    permission_classes = [permissions.IsAdminUser]
    
    def get(self, request):
        now = timezone.now()
        
        # Basic stats
        total_campaigns = Campaign.objects.count()
        active_campaigns = Campaign.objects.filter(status='Active').count()
        draft_campaigns = Campaign.objects.filter(status='Draft').count()
        
        total_participations = CampaignParticipation.objects.count()
        pending_participations = CampaignParticipation.objects.filter(status='Pending').count()
        approved_participations = CampaignParticipation.objects.filter(status='Approved').count()
        
        total_products = CampaignProduct.objects.count()
        pending_products = CampaignProduct.objects.filter(status='Pending').count()
        approved_products = CampaignProduct.objects.filter(status='Approved').count()
        
        # Upcoming deals
        upcoming_deals = Campaign.objects.filter(
            start_datetime__gt=now,
            status__in=['Draft', 'Active']
        ).order_by('start_datetime')[:5]
        
        upcoming_data = []
        for deal in upcoming_deals:
            time_diff = deal.start_datetime - now
            upcoming_data.append({
                'id': deal.id,
                'name': deal.campaign_name,
                'type': deal.campaign_type,
                'start_datetime': deal.start_datetime,
                'countdown_seconds': int(time_diff.total_seconds()),
                'vendor_count': deal.selected_vendors.count()
            })
        
        # Campaigns ending soon (within 24 hours)
        ending_soon = Campaign.objects.filter(
            end_datetime__gt=now,
            end_datetime__lt=now + timedelta(hours=24),
            status='Active'
        ).order_by('end_datetime')[:5]
        
        ending_data = []
        for campaign in ending_soon:
            time_diff = campaign.end_datetime - now
            ending_data.append({
                'id': campaign.id,
                'name': campaign.campaign_name,
                'end_datetime': campaign.end_datetime,
                'remaining_hours': int(time_diff.total_seconds() / 3600),
                'approved_products': campaign.approved_products_count
            })
        
        return Response({
            'campaigns': {
                'total': total_campaigns,
                'active': active_campaigns,
                'draft': draft_campaigns,
            },
            'participations': {
                'total': total_participations,
                'pending': pending_participations,
                'approved': approved_participations,
            },
            'products': {
                'total': total_products,
                'pending': pending_products,
                'approved': approved_products,
            },
            'upcoming_deals': {
                'count': upcoming_deals.count(),
                'deals': upcoming_data
            },
            'ending_soon': {
                'count': ending_soon.count(),
                'campaigns': ending_data
            }
        })

# =========================================================
# PRODUCT APPROVAL VIEWS
# =========================================================

class ApproveCampaignProductAPI(APIView):
    """Approve individual product with minimum requirements check"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, product_id):
        try:
            campaign_product = CampaignProduct.objects.get(id=product_id)
            campaign = campaign_product.participation.campaign
            
            # Check if product is already approved
            if campaign_product.status == 'Approved':
                return Response({'error': 'Product already approved'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Check minimum discount
            if campaign.minimum_discount > 0:
                if campaign_product.discount_percentage:
                    if campaign_product.discount_percentage < campaign.minimum_discount:
                        return Response({
                            'error': f'Discount must be at least {campaign.minimum_discount}%. '
                                    f'Current discount: {campaign_product.discount_percentage}%'
                        }, status=status.HTTP_400_BAD_REQUEST)
                elif campaign_product.special_price:
                    original_price = campaign_product.original_price
                    special_price = float(campaign_product.special_price)
                    discount_percentage = ((original_price - special_price) / original_price) * 100
                    
                    if discount_percentage < campaign.minimum_discount:
                        return Response({
                            'error': f'Discount must be at least {campaign.minimum_discount}%. '
                                    f'Current discount: {discount_percentage:.1f}%'
                        }, status=status.HTTP_400_BAD_REQUEST)
            
            # Approve the product
            campaign_product.status = 'Approved'
            campaign_product.approved_at = timezone.now()
            campaign_product.save()
            
            # Check if participation now meets minimum requirements
            participation = campaign_product.participation
            meets, message = participation.meets_minimum_requirements
            
            return Response({
                'message': 'Product approved successfully',
                'product': CampaignProductSerializer(campaign_product).data,
                'meets_minimum_requirements': meets,
                'requirements_message': message
            }, status=status.HTTP_200_OK)
            
        except CampaignProduct.DoesNotExist:
            return Response({'error': 'Campaign product not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

class RejectCampaignProductAPI(APIView):
    """Reject individual product"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, product_id):
        try:
            campaign_product = CampaignProduct.objects.get(id=product_id)
            
            # Check if product is already rejected
            if campaign_product.status == 'Rejected':
                return Response({'error': 'Product already rejected'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get rejection reason
            rejection_reason = request.data.get('rejection_reason', '')
            
            # Reject the product
            campaign_product.status = 'Rejected'
            campaign_product.rejection_reason = rejection_reason
            campaign_product.save()
            
            return Response({
                'message': 'Product rejected successfully',
                'product': CampaignProductSerializer(campaign_product).data
            }, status=status.HTTP_200_OK)
            
        except CampaignProduct.DoesNotExist:
            return Response({'error': 'Campaign product not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

class ApproveCampaignProductBulkAPI(APIView):
    """Approve multiple products at once"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, participation_id):
        try:
            participation = CampaignParticipation.objects.get(id=participation_id)
            product_ids = request.data.get('product_ids', [])
            
            if not product_ids:
                return Response({'error': 'No product IDs provided'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get pending products
            pending_products = participation.campaign_products.filter(
                id__in=product_ids, 
                status='Pending'
            )
            
            if not pending_products.exists():
                return Response({'error': 'No pending products found with given IDs'},
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Approve products
            updated_count = pending_products.update(
                status='Approved',
                approved_at=timezone.now()
            )
            
            return Response({
                'message': f'{updated_count} products approved successfully',
                'approved_count': updated_count
            }, status=status.HTTP_200_OK)
            
        except CampaignParticipation.DoesNotExist:
            return Response({'error': 'Participation not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

class RejectCampaignProductBulkAPI(APIView):
    """Reject multiple products at once"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, participation_id):
        try:
            participation = CampaignParticipation.objects.get(id=participation_id)
            product_ids = request.data.get('product_ids', [])
            rejection_reason = request.data.get('rejection_reason', '')
            
            if not product_ids:
                return Response({'error': 'No product IDs provided'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get pending products
            pending_products = participation.campaign_products.filter(
                id__in=product_ids, 
                status='Pending'
            )
            
            if not pending_products.exists():
                return Response({'error': 'No pending products found with given IDs'},
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Reject products
            updated_count = pending_products.update(
                status='Rejected',
                rejection_reason=rejection_reason
            )
            
            return Response({
                'message': f'{updated_count} products rejected',
                'rejected_count': updated_count
            }, status=status.HTTP_200_OK)
            
        except CampaignParticipation.DoesNotExist:
            return Response({'error': 'Participation not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

class ApproveParticipationWithProductsAPI(APIView):
    """Approve participation and all its pending products"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, participation_id):
        try:
            participation = CampaignParticipation.objects.get(
                id=participation_id, 
                status='Pending'
            )
            
            # Approve all pending products
            pending_products = participation.campaign_products.filter(status='Pending')
            product_count = pending_products.count()
            
            if product_count == 0:
                return Response({'error': 'No pending products to approve'},
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Check product limit
            if product_count > participation.campaign.max_products_per_vendor:
                return Response({
                    'error': f'Cannot approve. Vendor has {product_count} products, '
                            f'limit is {participation.campaign.max_products_per_vendor}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Approve all products
            pending_products.update(
                status='Approved',
                approved_at=timezone.now()
            )
            
            # Approve the participation
            participation.status = 'Approved'
            participation.approved_at = timezone.now()
            participation.approved_by = request.user
            participation.save()
            
            return Response({
                'message': f'Participation approved with {product_count} products',
                'participation': CampaignParticipationSerializer(participation).data,
                'approved_products': product_count
            }, status=status.HTTP_200_OK)
            
        except CampaignParticipation.DoesNotExist:
            return Response({'error': 'Participation not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

class CampaignParticipationProductsAPI(generics.ListAPIView):
    """Get all products for a specific participation"""
    serializer_class = CampaignProductSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        participation_id = self.kwargs.get('participation_id')
        
        try:
            participation = CampaignParticipation.objects.get(id=participation_id)
            
            # Get all campaign products with proper prefetching
            queryset = CampaignProduct.objects.filter(
                participation_id=participation_id
            ).select_related(
                'product',
                'product__vendor',
                'product__category'
            ).prefetch_related('product__stocks')
            
            return queryset
            
        except CampaignParticipation.DoesNotExist:
            return CampaignProduct.objects.none()
        except Exception as e:
            return CampaignProduct.objects.none()

# =========================================================
# APPROVAL VIEWS
# =========================================================

class ApproveCampaignParticipationAPI(APIView):
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, participation_id):
        try:
            participation = CampaignParticipation.objects.get(id=participation_id)
            
            if participation.status != 'Pending':
                return Response({'error': 'Participation is not pending'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Check if there are any approved products
            approved_products = participation.campaign_products.filter(status='Approved')
            if approved_products.count() == 0:
                return Response({
                    'error': 'Cannot approve participation without any approved products'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Approve the participation
            participation.status = 'Approved'
            participation.approved_at = timezone.now()
            participation.approved_by = request.user
            participation.save()
            
            return Response({
                'message': 'Campaign participation approved successfully',
                'participation': CampaignParticipationSerializer(participation).data
            }, status=status.HTTP_200_OK)
            
        except CampaignParticipation.DoesNotExist:
            return Response({'error': 'Participation not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

class RejectCampaignParticipationAPI(APIView):
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, participation_id):
        try:
            participation = CampaignParticipation.objects.get(id=participation_id)
            
            if participation.status != 'Pending':
                return Response({'error': 'Participation is not pending'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            rejection_reason = request.data.get('rejection_reason', '')
            
            # Reject all pending products
            participation.campaign_products.filter(status='Pending').update(
                status='Rejected',
                rejection_reason=rejection_reason
            )
            
            # Reject the participation
            participation.status = 'Rejected'
            participation.rejection_reason = rejection_reason
            participation.save()
            
            return Response({
                'message': 'Campaign participation rejected',
                'participation': CampaignParticipationSerializer(participation).data
            }, status=status.HTTP_200_OK)
            
        except CampaignParticipation.DoesNotExist:
            return Response({'error': 'Participation not found'}, 
                          status=status.HTTP_404_NOT_FOUND)

# =========================================================
# PUBLIC VIEWS
# =========================================================

# ecommerce/views/campaign_views.py में सिर्फ Active campaigns दिखाओ

class ActiveCampaignsAPI(generics.ListAPIView):
    serializer_class = CampaignSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        now = timezone.now()
        
        # ✅ TRICK: केवल वही campaigns दिखाओ जो अभी active हैं
        return Campaign.objects.filter(
            status='Active',
            start_datetime__lte=now,  # start हो चुकी है
            end_datetime__gte=now      # अभी खत्म नहीं हुई
        ).order_by('-created_at')

class CampaignProductsAPI(generics.ListAPIView):
    serializer_class = CampaignProductSerializer
    permission_classes=[permissions.AllowAny]
    
    def get_queryset(self):
        now = timezone.now()
        campaign_id = self.kwargs.get('campaign_id')
        
        # ✅ TRICK: केवल Active campaign के products दिखाओ
        return CampaignProduct.objects.filter(
            participation__campaign_id=campaign_id,
            participation__campaign__status='Active',
            participation__campaign__end_datetime__gte=now,  # अभी खत्म नहीं हुई
            status='Approved'
        ).select_related('product', 'participation__vendor')

# =========================================================
# SUPER ADMIN DETAIL VIEW
# =========================================================

class SuperAdminCampaignParticipationDetailAPI(generics.RetrieveAPIView):
    """Get detailed view of vendor participation with all products"""
    serializer_class = SuperAdminCampaignParticipationDetailSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = CampaignParticipation.objects.all()

# =========================================================
# VENDOR DAILY PARTICIPATION CHECK
# =========================================================

class VendorDailyParticipationCheckAPI(APIView):
    """Check if vendor can participate in a campaign today"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, campaign_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            campaign = Campaign.objects.get(id=campaign_id)
            today = date.today()
            
            # Check if vendor has already participated today
            has_participated_today = CampaignParticipation.objects.filter(
                campaign=campaign,
                vendor=vendor,
                applied_at__date=today
            ).exists()
            
            # Check if vendor is selected (if selection exists)
            is_selected = True  # Default to True if no selection
            if campaign.selected_vendors.exists():
                is_selected = vendor in campaign.selected_vendors.all()
            
            return Response({
                'vendor_id': vendor.id,
                'campaign_id': campaign.id,
                'today': today,
                'has_participated_today': has_participated_today,
                'is_selected': is_selected,
                'can_participate_today': not has_participated_today and is_selected,
                'message': 'You can participate today' if not has_participated_today and is_selected 
                          else 'Cannot participate today (already participated or not selected)'
            }, status=status.HTTP_200_OK)
            
        except Campaign.DoesNotExist:
            return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

# =========================================================
# DEBUG VIEWS
# =========================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def debug_vendor_info(request):
    """
    Debug endpoint to check vendor info
    """
    vendor = get_vendor_for_user(request.user)
    
    debug_info = {
        'user': {
            'id': request.user.id,
            'email': request.user.email,
            'username': request.user.username,
            'is_staff': request.user.is_staff,
            'is_superuser': request.user.is_superuser,
        },
        'vendor': None,
        'has_vendor_profile': hasattr(request.user, 'vendor_profile'),
    }
    
    if vendor:
        debug_info['vendor'] = {
            'id': vendor.id,
            'business_name': vendor.business_name,
            'email': vendor.email,
            'status': vendor.status,
            'is_approved': vendor.is_approved,
            'products_count': vendor.products.count(),
            'product_categories': list(vendor.products.values_list('category_id', flat=True).distinct())
        }
    
    return Response(debug_info)


# ecommerce/views/campaign_views.py में निम्नलिखित class add करें
class CampaignParticipationsListAPI(generics.ListAPIView):
    """Get all participations for a specific campaign"""
    serializer_class = CampaignParticipationSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        campaign_id = self.request.query_params.get('campaign_id')
        
        if not campaign_id:
            return CampaignParticipation.objects.none()
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            
            # Get all participations for this campaign
            participations = CampaignParticipation.objects.filter(
                campaign=campaign
            ).select_related(
                'vendor',
                'campaign'
            ).prefetch_related(
                'campaign_products'
            ).order_by('-applied_at')
            
            return participations
            
        except Campaign.DoesNotExist:
            return CampaignParticipation.objects.none()
        except Exception as e:
            print(f"Error fetching participations: {e}")
            return CampaignParticipation.objects.none()
class SaveBannerDetailsAPI(APIView):
    """Save hero banner details for Deal of the Day - SUPER ADMIN ONLY"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request):
        # 🚨 DEBUG: Print request details
        print("\n" + "="*50)
        print("SAVE BANNER API CALLED")
        print("="*50)
        print(f"User: {request.user}")
        print(f"Is Admin: {request.user.is_staff} / {request.user.is_superuser}")
        print(f"Method: {request.method}")
        print(f"Content-Type: {request.content_type}")
        print(f"FILES keys: {list(request.FILES.keys())}")
        print(f"POST keys: {list(request.POST.keys())}")
        print(f"POST data: {dict(request.POST)}")
        print(f"Product ID: {request.data.get('product_id')}")
        print(f"Remove banner: {request.data.get('remove_banner')}")
        print("="*50 + "\n")
        
        try:
            product_id = request.data.get('product_id')
            if not product_id:
                print("❌ ERROR: No product ID provided")
                return Response({'error': 'Product ID is required'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            print(f"✅ Product ID: {product_id}")
            
            try:
                campaign_product = CampaignProduct.objects.get(id=product_id)
                print(f"✅ Campaign product found: {campaign_product.id}")
                print(f"   Product: {campaign_product.product.product_name}")
                print(f"   Campaign: {campaign_product.participation.campaign.campaign_name}")
                print(f"   Campaign type: {campaign_product.participation.campaign.campaign_type}")
            except CampaignProduct.DoesNotExist:
                print(f"❌ ERROR: CampaignProduct with id {product_id} not found")
                return Response({'error': 'Campaign product not found'}, 
                              status=status.HTTP_404_NOT_FOUND)
            
            # Check if campaign is Deal of the Day
            campaign_type = campaign_product.participation.campaign.campaign_type
            print(f"📊 Campaign type: {campaign_type}")
            
            if campaign_type != 'Deal of the Day':
                print(f"❌ ERROR: Not Deal of the Day, it's {campaign_type}")
                return Response({'error': 'This is not a Deal of the Day campaign'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Handle remove banner
            if request.data.get('remove_banner') == 'true':
                print("🗑️ REMOVE BANNER requested")
                # Delete old image file
                if campaign_product.banner_image:
                    print(f"   Deleting old image: {campaign_product.banner_image.url}")
                    campaign_product.banner_image.delete(save=False)
                else:
                    print("   No old image to delete")
                
                campaign_product.banner_image = None
                campaign_product.banner_title = ''
                campaign_product.banner_subtitle = ''
                campaign_product.banner_button_url = ''
                campaign_product.is_banner_configured = False
                campaign_product.save()
                print("✅ Banner removed successfully")
                
                serializer = CampaignProductSerializer(
                    campaign_product, 
                    context={'request': request}
                )
                return Response({
                    'message': 'Banner removed successfully',
                    'product': serializer.data
                }, status=status.HTTP_200_OK)
            
            # Process image if provided
            banner_image = request.FILES.get('banner_image')
            print(f"📸 Banner image provided: {banner_image is not None}")
            
            if banner_image:
                print(f"   Image name: {banner_image.name}")
                print(f"   Image size: {banner_image.size} bytes")
                print(f"   Content type: {banner_image.content_type}")
                
                try:
                    # Open image with PIL
                    img = Image.open(banner_image)
                    original_width, original_height = img.size
                    print(f"   Original dimensions: {original_width}x{original_height}")
                    
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'LA', 'P'):
                        print(f"   Converting from {img.mode} to RGB")
                        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = rgb_img
                    elif img.mode != 'RGB':
                        print(f"   Converting from {img.mode} to RGB")
                        img = img.convert('RGB')
                    
                    # Target dimensions
                    target_width = 1920
                    target_height = 700
                    
                    # Calculate aspect ratios
                    target_ratio = target_width / target_height
                    original_ratio = original_width / original_height
                    
                    print(f"   Target ratio: {target_ratio:.2f}")
                    print(f"   Original ratio: {original_ratio:.2f}")
                    
                    if original_ratio > target_ratio:
                        # Image is wider - crop width
                        new_width = int(original_height * target_ratio)
                        new_height = original_height
                        left = (original_width - new_width) // 2
                        top = 0
                        print(f"   Cropping width: {new_width}x{new_height}, left={left}")
                        
                    elif original_ratio < target_ratio:
                        # Image is taller - crop height
                        new_width = original_width
                        new_height = int(original_width / target_ratio)
                        left = 0
                        top = (original_height - new_height) // 2
                        print(f"   Cropping height: {new_width}x{new_height}, top={top}")
                        
                    else:
                        # Perfect ratio
                        new_width = original_width
                        new_height = original_height
                        left = 0
                        top = 0
                        print(f"   Perfect ratio, no crop needed")
                    
                    # Crop the image
                    if original_ratio != target_ratio:
                        img = img.crop((left, top, left + new_width, top + new_height))
                        print(f"   After crop: {img.size[0]}x{img.size[1]}")
                    
                    # Resize to target dimensions
                    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    print(f"   After resize: {img.size[0]}x{img.size[1]}")
                    
                    # Save the processed image
                    output = io.BytesIO()
                    img.save(output, format='JPEG', quality=85, optimize=True)
                    output.seek(0)
                    print(f"   Saved to BytesIO, size: {output.getbuffer().nbytes} bytes")
                    
                    # Generate filename
                    original_name = banner_image.name
                    name, ext = os.path.splitext(original_name)
                    filename = f"{name}_1920x700_{product_id}.jpg"
                    print(f"   New filename: {filename}")
                    
                    # Delete old image if exists
                    if campaign_product.banner_image:
                        print(f"   Deleting old image: {campaign_product.banner_image.url}")
                        campaign_product.banner_image.delete(save=False)
                    
                    # Save new image
                    campaign_product.banner_image.save(
                        filename,
                        ContentFile(output.getvalue()),
                        save=False
                    )
                    print("   ✅ New image saved")
                    
                except Exception as e:
                    print(f"❌ ERROR processing image: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    return Response({
                        'error': f'Error processing image: {str(e)}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate required fields
            banner_title = request.data.get('banner_title', '')
            print(f"📝 Banner title: '{banner_title}'")
            
            if not banner_title:
                print("❌ ERROR: Banner title is empty")
                return Response({
                    'error': 'Banner title is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Save other fields
            campaign_product.banner_title = banner_title
            campaign_product.banner_subtitle = request.data.get('banner_subtitle', '')
            campaign_product.banner_button_url = request.data.get('banner_button_url', '')
            campaign_product.is_banner_configured = True
            campaign_product.save()
            print("✅ Banner details saved to database")
            
            # Return serialized data with full URLs
            serializer = CampaignProductSerializer(
                campaign_product, 
                context={'request': request}
            )
            print("✅ Serializer data prepared")
            
            return Response({
                'message': 'Banner details saved successfully',
                'product': serializer.data
            }, status=status.HTTP_200_OK)
            
        except CampaignProduct.DoesNotExist:
            print(f"❌ ERROR: Campaign product not found")
            return Response({'error': 'Campaign product not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VendorUpdateCampaignProductAPI(APIView):
    """Vendor can update discount for approved products - status goes back to pending"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, product_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            campaign_product = CampaignProduct.objects.get(
                id=product_id,
                participation__vendor=vendor,
                status__in=['Approved', 'Pending']  # Vendor can update approved or pending products
            )
            
            campaign = campaign_product.participation.campaign
            
            # Check if campaign is still active
            if not campaign.is_active:
                return Response({'error': 'Campaign is not active'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get new discount data
            discount_type = request.data.get('discount_type')
            discount_value = request.data.get('discount_value')
            special_price = request.data.get('special_price')
            
            # Validate discount based on campaign type
            if campaign.campaign_type != "Featured":
                if not discount_type or (not discount_value and not special_price):
                    return Response({'error': 'Discount is required for this campaign'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            
            # Check minimum discount requirement for Flash and Deal of the Day
            if campaign.campaign_type != "Featured" and campaign.minimum_discount > 0:
                if discount_type == 'percentage':
                    if not discount_value or discount_value < campaign.minimum_discount:
                        return Response({
                            'error': f'Minimum {campaign.minimum_discount}% discount required'
                        }, status=status.HTTP_400_BAD_REQUEST)
                elif discount_type == 'flat' and special_price:
                    # Calculate percentage discount
                    original_price = campaign_product.original_price
                    special_price_val = float(special_price)
                    discount_percentage = ((original_price - special_price_val) / original_price) * 100
                    
                    if discount_percentage < campaign.minimum_discount:
                        return Response({
                            'error': f'Minimum {campaign.minimum_discount}% discount required. '
                                    f'Current: {discount_percentage:.1f}%'
                        }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update product details
            if discount_type == 'percentage':
                campaign_product.discount_percentage = discount_value
                campaign_product.special_price = None
            elif discount_type == 'flat':
                campaign_product.discount_percentage = None
                campaign_product.special_price = special_price
            else:
                campaign_product.discount_percentage = None
                campaign_product.special_price = None
            
            # For Deal of the Day, check if placement needs to be updated
            if campaign.campaign_type == "Deal of the Day":
                new_placement = request.data.get('deal_of_day_placement')
                if new_placement in ['main', 'banner', 'product_list']:
                    campaign_product.deal_of_day_placement = new_placement
                    
                    # If changing to banner and banner was configured by super admin
                    if new_placement == 'banner' and campaign_product.is_banner_configured:
                        campaign_product.is_banner_configured = False  # Reset banner config
        
            # Mark as updated by vendor and set status to pending
            campaign_product.discount_updated = True
            campaign_product.vendor_updated_at = timezone.now()
            campaign_product.status = 'Pending'  # Go back to pending for admin approval
            
            campaign_product.save()
            
            return Response({
                'message': 'Product updated successfully. Waiting for admin approval.',
                'product': CampaignProductSerializer(campaign_product).data
            }, status=status.HTTP_200_OK)
            
        except CampaignProduct.DoesNotExist:
            return Response({'error': 'Product not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateDealOfDayPlacementAPI(APIView):
    """Vendor can update Deal of the Day placement for approved products"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, product_id):
        try:
            vendor = get_vendor_for_user(request.user)
            if not vendor:
                return Response({'error': 'User is not a vendor'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            campaign_product = CampaignProduct.objects.get(
                id=product_id,
                participation__vendor=vendor,
                status__in=['Approved', 'Pending']
            )
            
            campaign = campaign_product.participation.campaign
            
            if campaign.campaign_type != 'Deal of the Day':
                return Response({'error': 'This is not a Deal of the Day campaign'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            placement = request.data.get('deal_of_day_placement')
            if placement not in ['main', 'banner', 'product_list']:
                return Response({'error': 'Invalid placement type'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Update placement
            old_placement = campaign_product.deal_of_day_placement
            campaign_product.deal_of_day_placement = placement
            
            # If changing to banner and banner was configured by super admin
            if placement == 'banner' and old_placement != 'banner' and campaign_product.is_banner_configured:
                campaign_product.is_banner_configured = False  # Reset banner config
            
            # If product was approved, set back to pending for placement change
            if campaign_product.status == 'Approved':
                campaign_product.status = 'Pending'
                campaign_product.discount_updated = True
                campaign_product.vendor_updated_at = timezone.now()
            
            campaign_product.save()
            
            return Response({
                'message': f'Product placement updated to {get_placement_label(placement)}. '
                          f'Waiting for admin approval.' if campaign_product.status == 'Pending' 
                          else 'Product placement updated successfully.',
                'product': CampaignProductSerializer(campaign_product).data
            }, status=status.HTTP_200_OK)
            
        except CampaignProduct.DoesNotExist:
            return Response({'error': 'Product not found'}, 
                          status=status.HTTP_404_NOT_FOUND)


def get_placement_label(placement: str) -> str:
    """Helper function to get placement label"""
    placements = {
        'main': 'Main Section',
        'banner': 'Hero Banner',
        'product_list': 'Product List'
    }
    return placements.get(placement, placement)      


class DealOfDayMainProductsAPI(APIView):
    """Get approved Deal of the Day products with 'main' placement for slider"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        now = timezone.now()
        
        # Get active Deal of the Day campaigns
        deal_of_day_campaigns = Campaign.objects.filter(
            campaign_type='Deal of the Day',
            status='Active',
            start_datetime__lte=now,
            end_datetime__gte=now
        )
        
        if not deal_of_day_campaigns.exists():
            return Response({
                'products': [],
                'message': 'No active Deal of the Day campaign'
            })
        
        campaign = deal_of_day_campaigns.first()
        
        # Get approved campaign products with 'main' placement
        main_products = CampaignProduct.objects.filter(
            participation__campaign=campaign,
            status='Approved',
            deal_of_day_placement='main'
        ).select_related(
            'product',
            'product__vendor',
            'participation'
        ).prefetch_related(
            'product__stocks',
            'product__gallery'
        ).order_by('?')[:10]
        
        # Serialize the data
        products_data = []
        for cp in main_products:
            product = cp.product
            stock = product.stocks.first()

            # ✅ Correct image fallback chain
            image_url = None
            if product.main_image:
                image_url = request.build_absolute_uri(product.main_image.url)
            elif product.thumbnail_image:
                image_url = request.build_absolute_uri(product.thumbnail_image.url)
            elif hasattr(product, 'gallery') and product.gallery.exists():
                first_gallery = product.gallery.first()
                if first_gallery and first_gallery.image:
                    image_url = request.build_absolute_uri(first_gallery.image.url)
            elif stock and stock.variant_image:
                image_url = request.build_absolute_uri(stock.variant_image.url)

            original_price = cp.original_price
            final_price = cp.final_price
            discount_percentage = cp.discount_percentage

            if not discount_percentage and cp.special_price:
                discount_percentage = round(
                    ((float(original_price) - float(cp.special_price)) / float(original_price)) * 100
                )

            products_data.append({
                'id': product.id,
                'campaign_product_id': cp.id,
                'name': product.product_name,
                'price': final_price,
                'old_price': original_price,
                'discount_percentage': discount_percentage,
                'image': image_url,
                'gallery': [
                    {'image': request.build_absolute_uri(img.image.url)}
                    for img in product.gallery.all()[:4]
                    if img.image
                ] if hasattr(product, 'gallery') else [],
                'stocks': [{
                    'id': stock.id,
                    'mrp': float(stock.mrp) if stock.mrp else 0,
                    'selling_price': float(stock.selling_price) if stock.selling_price else 0,
                    'final_price': float(final_price) if final_price else 0,
                    'maximum_order_quantity': stock.maximum_order_quantity or 10
                }] if stock else [],
                'vendor_name': product.vendor.business_name if product.vendor else '',
                'campaign_name': campaign.campaign_name,
                'end_datetime': campaign.end_datetime
            })
        
        # Get countdown seconds
        countdown_seconds = int((campaign.end_datetime - now).total_seconds()) if campaign else 0
        
        return Response({
            'campaign': {
                'id': campaign.id,
                'name': campaign.campaign_name,
                'end_datetime': campaign.end_datetime,
                'countdown_seconds': countdown_seconds
            },
            'products': products_data,
            'total_products': len(products_data)
        }, status=status.HTTP_200_OK)
        
class DealOfDayAdminProductsAPI(APIView):
    """Get all Deal of the Day products for admin with proper filtering"""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        now = timezone.now()

        deal_of_day_campaigns = Campaign.objects.filter(
            campaign_type='Deal of the Day',
            status='Active',
            start_datetime__lte=now,
            end_datetime__gte=now
        )

        if not deal_of_day_campaigns.exists():
            return Response({
                'products': [],
                'message': 'No active Deal of the Day campaign'
            })

        campaign = deal_of_day_campaigns.first()

        main_products = CampaignProduct.objects.filter(
            participation__campaign=campaign,
            status='Approved',
            deal_of_day_placement='main'
        ).select_related(
            'product',
            'product__vendor',
            'participation'
        ).prefetch_related(
            'product__stocks',
            'product__gallery'
        ).order_by('?')[:10]

        products_data = []
        for cp in main_products:
            product = cp.product
            stock = product.stocks.first()

            # ✅ Fallback chain: main_image → thumbnail → gallery → variant_image
            # ✅ main_image pehle check karo (yahi filled hai)
            image_url = None
            if product.main_image:
                image_url = request.build_absolute_uri(product.main_image.url)
            elif product.thumbnail_image:
                image_url = request.build_absolute_uri(product.thumbnail_image.url)
            elif hasattr(product, 'gallery') and product.gallery.exists():
                first_gallery = product.gallery.first()
                if first_gallery and first_gallery.image:
                    image_url = request.build_absolute_uri(first_gallery.image.url)
            elif stock and stock.variant_image:
                image_url = request.build_absolute_uri(stock.variant_image.url)

            original_price = cp.original_price
            final_price = cp.final_price
            discount_percentage = cp.discount_percentage
            if not discount_percentage and cp.special_price:
                discount_percentage = round(
                    ((original_price - float(cp.special_price)) / original_price) * 100
                )

            products_data.append({
                'id': product.id,
                'campaign_product_id': cp.id,
                'name': product.product_name,
                'price': final_price,
                'old_price': original_price,
                'discount_percentage': discount_percentage,
                'image': image_url,           # ✅ Now populated correctly
                'gallery': [
                    {'image': request.build_absolute_uri(img.image.url)}
                    for img in product.gallery.all()[:4]
                    if img.image
                ] if hasattr(product, 'gallery') else [],
                'stocks': [{
                    'id': stock.id,
                    'mrp': float(stock.mrp),
                    'selling_price': float(stock.selling_price),
                    'final_price': final_price,
                    'maximum_order_quantity': stock.maximum_order_quantity or 10
                }] if stock else [],
                'vendor_name': product.vendor.business_name if product.vendor else '',
                'campaign_name': campaign.campaign_name,
                'end_datetime': campaign.end_datetime
            })

        countdown_seconds = int((campaign.end_datetime - now).total_seconds())

        return Response({
            'campaign': {
                'id': campaign.id,
                'name': campaign.campaign_name,
                'end_datetime': campaign.end_datetime,
                'countdown_seconds': countdown_seconds
            },
            'products': products_data,
            'total_products': len(products_data)
        }, status=status.HTTP_200_OK)

class DealOfDayAllProductsAPI(APIView):
    """Get ALL products from active Deal of the Day campaign - Complete version with images and details"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        now = timezone.now()
        
        # Get active Deal of the Day campaign
        deal_of_day_campaign = Campaign.objects.filter(
            campaign_type='Deal of the Day',
            status='Active',
            start_datetime__lte=now,
            end_datetime__gte=now
        ).first()
        
        if not deal_of_day_campaign:
            return Response({
                'success': False,
                'message': 'No active Deal of the Day campaign',
                'products': []
            }, status=status.HTTP_200_OK)
        
        # Get ALL approved campaign products (without placement filter)
        campaign_products = CampaignProduct.objects.filter(
            participation__campaign=deal_of_day_campaign,
            status='Approved',
        ).select_related(
            'product',
            'product__vendor',
            'product__category',
            'product__brand',
            'participation'
        ).prefetch_related(
            'product__stocks',
            'product__gallery'
        ).order_by('-added_at')
        
        # Serialize products like DealOfDayMainProductsAPI
        products_data = []
        for cp in campaign_products:
            product = cp.product
            
            # Get product stock
            stock = product.stocks.first()
            
            # Calculate prices
            original_price = float(cp.original_price) if cp.original_price else 0
            final_price = float(cp.final_price) if cp.final_price else 0
            discount_percentage = cp.discount_percentage
            
            if not discount_percentage and cp.special_price:
                discount_percentage = round(((original_price - float(cp.special_price)) / original_price) * 100)
            
            # Get main image URL
            main_image = None
            if product.main_image:
                main_image = request.build_absolute_uri(product.main_image.url) if request else product.main_image.url
            elif product.thumbnail_image:
                main_image = request.build_absolute_uri(product.thumbnail_image.url) if request else product.thumbnail_image.url
            elif hasattr(product, 'gallery') and product.gallery.exists():
                first_gallery = product.gallery.first()
                if first_gallery and first_gallery.image:
                    main_image = request.build_absolute_uri(first_gallery.image.url) if request else first_gallery.image.url
            
            # Get gallery images
            gallery_images = []
            if hasattr(product, 'gallery'):
                for img in product.gallery.all()[:4]:
                    if img.image:
                        img_url = request.build_absolute_uri(img.image.url) if request else img.image.url
                        gallery_images.append({
                            'id': img.id,
                            'image': img_url
                        })
            
            # Get stocks data
            stocks_data = []
            for s in product.stocks.all():
                stocks_data.append({
                    'id': s.id,
                    'mrp': float(s.mrp) if s.mrp else 0,
                    'selling_price': float(s.selling_price) if s.selling_price else 0,
                    'final_price': final_price,
                    'stock_quantity': s.stock_quantity,
                    'maximum_order_quantity': s.maximum_order_quantity or 10,
                    'color': s.color,
                    'size': s.size
                })
            
            # Complete product data like MainProductsAPI
            product_data = {
                'id': cp.id,
                'campaign_product_id': cp.id,
                'product_id': product.id,
                'name': product.product_name,
                'product_name': product.product_name,
                'short_description': product.short_description,
                'full_description': product.full_description,
                'description': product.short_description or product.full_description,
                'price': final_price,
                'final_price': final_price,
                'old_price': original_price,
                'original_price': original_price,
                'special_price': float(cp.special_price) if cp.special_price else None,
                'discount_percentage': discount_percentage,
                'deal_of_day_placement': cp.deal_of_day_placement,
                'image': main_image,
                'main_image': main_image,
                'thumbnail_image': main_image,
                'gallery': gallery_images,
                'stocks': stocks_data,
                'in_stock': any(s.get('stock_quantity', 0) > 0 for s in stocks_data),
                'vendor_name': product.vendor.business_name if product.vendor else '',
                'vendor_id': product.vendor.id if product.vendor else None,
                'vendor_details': {
                    'id': product.vendor.id if product.vendor else None,
                    'business_name': product.vendor.business_name if product.vendor else '',
                    'email': product.vendor.email if product.vendor else '',
                    'phone': product.vendor.phone if product.vendor else ''
                } if product.vendor else None,
                # 🔥 FIXED: category_name की जगह name use kiya
                'category_name': product.category.name if product.category else None,
                'category_id': product.category.id if product.category else None,
                'brand_name': product.brand.brand_name if product.brand else None,
                'brand_id': product.brand.id if product.brand else None,
                'rating': float(product.rating) if hasattr(product, 'rating') and product.rating else 4.0,
                'review_count': product.review_count if hasattr(product, 'review_count') else 0,
                'campaign_name': deal_of_day_campaign.campaign_name,
                'campaign_id': deal_of_day_campaign.id,
                'end_datetime': deal_of_day_campaign.end_datetime,
                'countdown_seconds': int((deal_of_day_campaign.end_datetime - now).total_seconds())
            }
            
            products_data.append(product_data)
        
        # Get countdown seconds
        countdown_seconds = int((deal_of_day_campaign.end_datetime - now).total_seconds())
        
        return Response({
            'success': True,
            'campaign': {
                'id': deal_of_day_campaign.id,
                'name': deal_of_day_campaign.campaign_name,
                'description': deal_of_day_campaign.description,
                'start_datetime': deal_of_day_campaign.start_datetime,
                'end_datetime': deal_of_day_campaign.end_datetime,
                'minimum_discount': deal_of_day_campaign.minimum_discount,
                'countdown_seconds': countdown_seconds
            },
            'countdown_seconds': countdown_seconds,
            'total_products': len(products_data),
            'products': products_data
        }, status=status.HTTP_200_OK)
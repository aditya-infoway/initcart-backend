# views.py
from django.utils import timezone 
from ecommerce.models.campaign import Campaign , CampaignProduct
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import BigAd, MobileBanner, MobileCategoryCard, MobileDealCard, SmallAd
from .serializers import BigAdSerializer, MobileBannerSerializer, MobileCategoryCardSerializer, MobileDealCardSerializer, SmallAdSerializer
from .models import SliderImage
from .serializers import SliderImageSerializer
from ecommerce.models.vendor import Vendor
from django.contrib.auth import get_user_model
from .models import SuperAdminProfile
from .serializers import SuperAdminProfileSerializer,initAdminFooterSerializer

from django.core.cache import cache

class CombinedBannersAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cache_key = "combined_banners_data"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        banners = []
        now = timezone.now()

        deal_of_day_campaigns = Campaign.objects.filter(
            campaign_type='Deal of the Day',
            status='Active',
            start_datetime__lte=now,
            end_datetime__gte=now
        )

        if deal_of_day_campaigns.exists():
            campaign = deal_of_day_campaigns.first()

            # ✅ prefetch product.stocks taaki loop me extra query na lage
            banner_products = CampaignProduct.objects.filter(
                participation__campaign=campaign,
                status='Approved',
                deal_of_day_placement='banner',
                banner_image__isnull=False,
                banner_title__isnull=False
            ).exclude(
                banner_image=''
            ).select_related(
                'product', 'participation__vendor'
            ).prefetch_related('product__stocks')

            for product in banner_products:
                product_url = product.banner_button_url
                if not product_url and product.product:
                    product_url = f"/product/{product.product.id}/"

                banner_image_url = None
                if product.banner_image:
                    # ✅ banner_image hai toh stock query karo hi mat
                    banner_image_url = request.build_absolute_uri(product.banner_image.url)
                elif product.product:
                    # ✅ prefetch_related ki wajah se ye ab cached list se aayega, DB hit nahi karega
                    stocks = list(product.product.stocks.all())
                    if stocks and stocks[0].variant_image:
                        banner_image_url = request.build_absolute_uri(stocks[0].variant_image.url)

                banners.append({
                    'id': f"deal_{product.id}",
                    'type': 'deal_of_day',
                    'image': banner_image_url,
                    'title': product.banner_title or '',
                    'subtitle': product.banner_subtitle or '',
                    'button_text': 'Shop Now',
                    'button_url': product_url,
                    'product_id': product.product.id if product.product else None,
                    'campaign_id': campaign.id,
                    'campaign_name': campaign.campaign_name,
                    'sort_order': 1
                })

        try:
            regular_banners = SliderImage.objects.all().order_by('-id')
            for banner in regular_banners:
                if banner.image:
                    banners.append({
                        'id': f"regular_{banner.id}",
                        'type': 'regular',
                        'image': request.build_absolute_uri(banner.image.url),
                        'title': '', 'subtitle': '', 'button_text': '', 'button_url': '',
                        'product_id': None, 'campaign_id': None, 'campaign_name': None,
                        'sort_order': 2
                    })
        except Exception as e:
            print(f"Error fetching regular banners: {e}")

        banners.sort(key=lambda x: x.get('sort_order', 999))

        # ✅ 60 second cache — banners itni jaldi change nahi hote
        cache.set(cache_key, banners, 60)

        return Response(banners, status=status.HTTP_200_OK)

class SliderImageUploadView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = SliderImage.objects.all().order_by("-id")
        serializer = SliderImageSerializer(
            qs,
            many=True,
            context={"request": request}
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = SliderImageSerializer(
            data=request.data,
            context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)



class SliderImageDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    def delete(self, request, pk):
        try:
            obj = SliderImage.objects.get(pk=pk)
            obj.delete()
            return Response({"message": "Deleted"})
        except SliderImage.DoesNotExist:
            return Response(status=404)
        
    def put(self, request, pk):
        obj = get_object_or_404(SliderImage, pk=pk)

        # image replace
        if "image" in request.FILES:
            obj.image = request.FILES["image"]
            obj.save()

        serializer = SliderImageSerializer(
            obj,
            context={"request": request}
        )
        return Response(serializer.data)
    
class SliderImageView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = SliderImage.objects.all().order_by("-id")
        serializer = SliderImageSerializer(
            qs,
            many=True,
            context={"request": request}
        )
        return Response(serializer.data)


# ===== BIG AD (only one record) =====

class BigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = BigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            BigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = BigAd.objects.first()

        # if exists → update
        if obj:
            ser = BigAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # else → create first time
        ser = BigAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = BigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            BigAdSerializer(obj, context={"request": request}).data
        )
    
class SmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = SmallAd.objects.all().order_by("slot")
        return Response(
            SmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")

        if slot not in ["1", "2", 1, 2]:
            return Response(
                {"error": "slot must be 1 or 2"},
                status=400
            )

        obj = SmallAd.objects.filter(slot=slot).first()

        # update if exists
        if obj:
            ser = SmallAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # create if not exists yet
        ser = SmallAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = SmallAd.objects.all().order_by("slot")
        return Response(
            SmallAdSerializer(qs, many=True, context={"request": request}).data
        )
        

User = get_user_model()


class DashboardStatsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        total_product_vendors = Vendor.objects.filter(
            vendor_type="product"
        ).count()

        total_service_vendors = Vendor.objects.filter(
            vendor_type="service"
        ).count()

        total_login_users = User.objects.filter(
            is_active=True, 
            role='customer'
        ).count()


        return Response({
            "totalProductVendor": total_product_vendors,
            "totalServiceVendor": total_service_vendors,
            "totalLoginUsers": total_login_users,
        }) 

class SuperAdminProfileAPI(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        obj = SuperAdminProfile.objects.first()
        if not obj:
            return Response({})

        data = SuperAdminProfileSerializer(
            obj,
            context={"request": request}  # ✅ Context pass karo
        ).data

        data["joinDate"] = request.user.date_joined.date()
        return Response(data)

    def post(self, request):
        obj = SuperAdminProfile.objects.first()
        if obj:
            # Already exists, update it instead
            ser = SuperAdminProfileSerializer(
                obj, 
                data=request.data, 
                partial=True,
                context={"request": request}  # ✅ ADD THIS
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response({
                "success": True,
                "message": "Profile updated successfully",
                "data": ser.data
            }, status=status.HTTP_200_OK)

        # Create new profile
        ser = SuperAdminProfileSerializer(
            data=request.data,
            context={"request": request}  # ✅ ADD THIS
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({
            "success": True,
            "message": "Profile created successfully",
            "data": ser.data
        }, status=status.HTTP_201_CREATED)

    def put(self, request):
        obj = SuperAdminProfile.objects.first()
        if not obj:
            # Create if not exists
            ser = SuperAdminProfileSerializer(
                data=request.data,
                context={"request": request}  # ✅ ADD THIS
            )
        else:
            # Update existing
            ser = SuperAdminProfileSerializer(
                obj, 
                data=request.data, 
                partial=True,
                context={"request": request}  # ✅ ADD THIS
            )

        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({
            "success": True,
            "message": "Profile updated successfully",
            "data": ser.data
        })



class initAdminDetailsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = SuperAdminProfile.objects.first()
        if not obj:
            return Response({}, status=200)

        return Response(
            initAdminFooterSerializer(
                obj,
                context={"request": request}  # ✅ ADD THIS
            ).data
        )
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.uploadedfile import InMemoryUploadedFile
import logging

logger = logging.getLogger(__name__)

class MobileBannerListView(APIView):
    """Get all mobile banners (public)"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        banners = MobileBanner.objects.filter(is_active=True).order_by('order')
        serializer = MobileBannerSerializer(banners, many=True, context={'request': request})
        return Response(serializer.data)


class MobileBannerManageView(APIView):
    """Manage mobile banners (admin only)"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get(self, request):
        """Get all banners for admin"""
        if not request.user.is_superuser:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        banners = MobileBanner.objects.all().order_by('order')
        serializer = MobileBannerSerializer(banners, many=True, context={'request': request})
        print("Sending banners:", len(banners), "banners")  # Debug
        return Response(serializer.data)
    
    def post(self, request):
        """Create new banner"""
        if not request.user.is_superuser:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        print("=== POST Request Debug ===")
        print("POST data:", request.POST)
        print("FILES data:", request.FILES)
        print("Has image:", 'image' in request.FILES)
        
        try:
            # Manual save for debugging
            banner = MobileBanner()
            banner.title = request.POST.get('title', '')
            banner.subtitle = request.POST.get('subtitle', '')
            banner.button_text = request.POST.get('button_text', '')
            banner.button_url = request.POST.get('button_url', '')
            banner.order = int(request.POST.get('order', 0))
            banner.is_active = request.POST.get('is_active', 'true').lower() == 'true'
            
            if 'image' in request.FILES:
                print("Image found:", request.FILES['image'].name)
                banner.image = request.FILES['image']
            else:
                print("No image in request!")
                return Response({'error': 'Image is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            banner.save()
            print("Banner saved with ID:", banner.id)
            
            serializer = MobileBannerSerializer(banner, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print("Error creating banner:", str(e))
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        """Update banner"""
        if not request.user.is_superuser:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            banner = MobileBanner.objects.get(pk=pk)
        except MobileBanner.DoesNotExist:
            return Response({'error': 'Banner not found'}, status=status.HTTP_404_NOT_FOUND)
        
        print("=== PUT Request Debug ===")
        print("POST data:", request.POST)
        print("FILES data:", request.FILES)
        
        try:
            banner.title = request.POST.get('title', banner.title)
            banner.subtitle = request.POST.get('subtitle', banner.subtitle)
            banner.button_text = request.POST.get('button_text', banner.button_text)
            banner.button_url = request.POST.get('button_url', banner.button_url)
            banner.order = int(request.POST.get('order', banner.order))
            banner.is_active = request.POST.get('is_active', str(banner.is_active)).lower() == 'true'
            
            if 'image' in request.FILES:
                print("Updating image:", request.FILES['image'].name)
                banner.image = request.FILES['image']
            
            banner.save()
            print("Banner updated successfully")
            
            serializer = MobileBannerSerializer(banner, context={'request': request})
            return Response(serializer.data)
            
        except Exception as e:
            print("Error updating banner:", str(e))
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, pk):
        """Partial update banner"""
        if not request.user.is_superuser:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            banner = MobileBanner.objects.get(pk=pk)
        except MobileBanner.DoesNotExist:
            return Response({'error': 'Banner not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if 'is_active' in request.data:
            banner.is_active = request.data['is_active']
            banner.save()
        
        serializer = MobileBannerSerializer(banner, context={'request': request})
        return Response(serializer.data)
    
    def delete(self, request, pk):
        """Delete banner"""
        if not request.user.is_superuser:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            banner = MobileBanner.objects.get(pk=pk)
            banner.delete()
            return Response({'message': 'Banner deleted successfully'}, status=status.HTTP_200_OK)
        except MobileBanner.DoesNotExist:
            return Response({'error': 'Banner not found'}, status=status.HTTP_404_NOT_FOUND)

class MobileCategoryCardAPIView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        cards = MobileCategoryCard.objects.filter(is_active=True)
        serializer = MobileCategoryCardSerializer(cards, many=True, context={'request': request})
        return Response(serializer.data)


class MobileDealCardAPIView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        deal_type = request.query_params.get('type', None)
        queryset = MobileDealCard.objects.filter(is_active=True)
        if deal_type:
            queryset = queryset.filter(deal_type=deal_type)
        serializer = MobileDealCardSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)        
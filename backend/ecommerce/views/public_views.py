#ecommerce/views/public_views.py
from rest_framework import generics, filters
from django.db.models import Prefetch
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from ecommerce.models.product import Product, ProductStock
from ecommerce.models.vendor import Brand, Vendor
from ecommerce.models.order import Cart
from decimal import Decimal
from ecommerce.models.coupon import Coupon, CouponUsage
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Q, F
from django.utils import timezone
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from ecommerce.serializers.product_serializers import ProductSerializer
from ecommerce.serializers.vendor_serializers import BrandSerializer 
from ecommerce.serializers.public_serializers import PublicVendorSerializer
from ecommerce.serializers.category_serializers import CategorySerializer, SubCategorySerializer, SubSubCategorySerializer
from ecommerce.serializers.public_serializers import (  # Import public serializers
    PublicCategorySerializer, 
    PublicSubCategorySerializer, 
    PublicSubSubCategorySerializer,
    PublicVendorSerializer,
    PublicBrandSerializer,
    PublicProductSerializer,
    PublicCouponSerializer,
    ApplyCouponSerializer,  
    CouponValidationResponseSerializer,
    ProductCouponSerializer,

)
from rest_framework import generics, filters
from rest_framework.pagination import PageNumberPagination

class ProductPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PublicProductListAPI(generics.ListAPIView):
    """Get all approved products - with server-side filters + pagination"""
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]
    pagination_class = ProductPagination

    def get_queryset(self):
        queryset = Product.objects.filter(status="approved")

        # Category filter (comma-separated ids)
        category_ids = self.request.query_params.get('category_ids')
        if category_ids:
            ids = [int(i) for i in category_ids.split(',') if i.strip().isdigit()]
            if ids:
                queryset = queryset.filter(category_id__in=ids)

        # Brand filter
        brand_ids = self.request.query_params.get('brand_ids')
        if brand_ids:
            ids = [int(i) for i in brand_ids.split(',') if i.strip().isdigit()]
            if ids:
                queryset = queryset.filter(brand_id__in=ids)

        # Condition filter
        conditions = self.request.query_params.get('conditions')
        if conditions:
            cond_list = [c.strip() for c in conditions.split(',') if c.strip()]
            if cond_list:
                queryset = queryset.filter(product_condition__in=cond_list)

        # Vendor / product name search
        vendor_search = self.request.query_params.get('vendor_search')
        if vendor_search:
            queryset = queryset.filter(
                Q(vendor__business_name__icontains=vendor_search) |
                Q(product_name__icontains=vendor_search)
            )

        # Price filter
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price or max_price:
            stock_filter = Q()
            if min_price:
                stock_filter &= Q(final_price__gte=min_price)
            if max_price:
                stock_filter &= Q(final_price__lte=max_price)
            matching_ids = ProductStock.objects.filter(stock_filter).values_list('product_id', flat=True)
            queryset = queryset.filter(id__in=matching_ids)

        queryset = queryset.select_related(
            'vendor', 'brand', 'category', 'subcategory', 'subsubcategory'
        ).prefetch_related('stocks', 'gallery').order_by('-created_at')

        return queryset.distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    
class PublicProductDetailAPI(generics.RetrieveAPIView):
    """Get single product details"""
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]
    queryset = Product.objects.filter(status="approved")
    
    def get_queryset(self):
        return Product.objects.filter(status="approved").select_related(
            'vendor', 'brand', 'category', 'subcategory', 'subsubcategory'
        ).prefetch_related('stocks', 'gallery')
        
    def get_serializer_context(self):
        """Add request to serializer context for absolute URLs"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context    

class PublicBrandListAPI(generics.ListAPIView):
    serializer_class = PublicBrandSerializer
    permission_classes = [AllowAny]
    queryset = Brand.objects.filter(status="active").order_by('brand_name')
     
# s CATEGORY APIs - UPDATED (public serializers use karen)
class PublicCategoryListAPI(generics.ListAPIView):
    serializer_class = PublicCategorySerializer  #  Use public serializer
    permission_classes = [AllowAny]
    queryset = Category.objects.filter(status=True).order_by('name')
    
    

class PublicSubCategoryListAPI(generics.ListAPIView):
    serializer_class = PublicSubCategorySerializer  # Use public serializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        category_id = self.request.query_params.get('category')
        queryset = SubCategory.objects.filter(status=True)
        
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

class PublicSubSubCategoryListAPI(generics.ListAPIView):
    serializer_class = PublicSubSubCategorySerializer  #  Use public serializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        subcategory_id = self.request.query_params.get('subcategory')
        queryset = SubSubCategory.objects.filter(status=True)
        
        if subcategory_id:
            queryset = queryset.filter(subcategory_id=subcategory_id)
        return queryset


class PublicVendorListAPI(generics.ListAPIView):
    serializer_class = PublicVendorSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        return Vendor.objects.filter(
            status='active', 
            is_approved=True,
            vendor_type='product'
        ).order_by('-created_at')
    
class CategoryProductsAPI(generics.ListAPIView):
    """
    API to get products based on category/subcategory/subsubcategory
    Supports query parameters: category, subcategory, subsubcategory
    """
    serializer_class = PublicProductSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = ['category', 'subcategory', 'subsubcategory', 'brand', 'vendor']
    search_fields = ['product_name', 'short_description', 'keywords']
    ordering_fields = ['created_at', 'product_name']
    
    def get_queryset(self):
        queryset = Product.objects.filter(status="approved")
        
        # Get query parameters
        category_id = self.request.query_params.get('category')
        subcategory_id = self.request.query_params.get('subcategory')
        subsubcategory_id = self.request.query_params.get('subsubcategory')
        
        # Apply filters with proper hierarchy
        if subsubcategory_id:
            # If subsubcategory is selected, filter by that
            queryset = queryset.filter(subsubcategory_id=subsubcategory_id)
        
        elif subcategory_id:
            # If only subcategory is selected, filter by that
            queryset = queryset.filter(subcategory_id=subcategory_id)
        
        elif category_id:
            # If only category is selected, filter by that
            queryset = queryset.filter(category_id=category_id)
        
        # Additional filters
        brand_id = self.request.query_params.get('brand')
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        
        vendor_id = self.request.query_params.get('vendor')
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)
        
        # Price filter
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        
        if min_price or max_price:
            # We need to filter based on stock prices
            from ecommerce.models.product import ProductStock
            stock_filter = Q()
            
            if min_price:
                stock_filter &= Q(final_price__gte=min_price)
            if max_price:
                stock_filter &= Q(final_price__lte=max_price)
            
            # Get product IDs with matching stock prices
            matching_stocks = ProductStock.objects.filter(stock_filter).values_list('product_id', flat=True)
            queryset = queryset.filter(id__in=matching_stocks)
        
        # In-stock filter
        in_stock = self.request.query_params.get('in_stock')
        if in_stock == 'true':
            # Get product IDs with available stock
            available_stocks = ProductStock.objects.filter(stock_quantity__gt=0).values_list('product_id', flat=True)
            queryset = queryset.filter(id__in=available_stocks)
        
        # Prefetch related data for better performance
        queryset = queryset.select_related(
            'vendor', 
            'brand', 
            'category', 
            'subcategory', 
            'subsubcategory'
        ).prefetch_related('stocks', 'gallery')
        
        return queryset.order_by('-created_at')
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    
    
class SubCategoryProductsAPIView(APIView):
    """
    API to get products for multiple subcategories at once
    Returns: Dictionary with subcategory_id as key and list of products as value
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            # Get subcategory IDs from query params (comma-separated)
            subcategory_ids = request.query_params.get('subcategory_ids', '')
            products_per_subcat = int(request.query_params.get('products_per_subcat', 4))
            
            if not subcategory_ids:
                return Response({
                    'success': False,
                    'message': 'subcategory_ids parameter is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse IDs
            id_list = [int(id.strip()) for id in subcategory_ids.split(',') if id.strip()]
            
            result = {}
            
            for subcat_id in id_list:
                # Get 4 random approved products for this subcategory
                products = Product.objects.filter(
                    subcategory_id=subcat_id,
                    status='approved'
                ).select_related(
                    'vendor', 'brand'
                ).prefetch_related(
                    Prefetch('stocks', queryset=ProductStock.objects.all()),
                    'gallery'
                ).order_by('?')[:products_per_subcat]  # Random order
                
                # Serialize products
                product_serializer = PublicProductSerializer(
                    products, 
                    many=True, 
                    context={'request': request}
                )
                
                # Get subcategory details
                try:
                    subcategory = SubCategory.objects.get(id=subcat_id, status=True)
                    subcat_data = {
                        'id': subcategory.id,
                        'name': subcategory.name,
                        'icon_url': request.build_absolute_uri(subcategory.icon.url) if subcategory.icon else None,
                        'category_name': subcategory.category.name if subcategory.category else None,
                        'category_id': subcategory.category.id if subcategory.category else None,
                    }
                except SubCategory.DoesNotExist:
                    subcat_data = None
                
                result[str(subcat_id)] = {
                    'subcategory': subcat_data,
                    'products': product_serializer.data,
                    'product_count': len(product_serializer.data)
                }
            
            return Response({
                'success': True,
                'data': result
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PublicCouponListView(APIView):
    """Get all active coupons"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        try:
            # Get all active coupons
            now = timezone.now()
            coupons = Coupon.objects.filter(
                status='active',
                start_date__lte=now,
                expire_date__gte=now
            ).filter(
                Q(max_count__isnull=True) | Q(used_count__lt=F('max_count'))
            ).order_by('-created_at')
            
            serializer = PublicCouponSerializer(coupons, many=True)
            
            return Response({
                'success': True,
                'count': coupons.count(),
                'coupons': serializer.data
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ValidateCouponAPIView(APIView):
    """Validate coupon code"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = ApplyCouponSerializer(data=request.data)
        
        if serializer.is_valid():
            coupon = serializer.validated_data['coupon_code']
            
            # For authenticated users, check per user limit
            user = request.user if request.user.is_authenticated else None
            if user and coupon:
                if not coupon.is_valid_for_user(user):
                    return Response({
                        'success': False,
                        'valid': False,
                        'message': 'You have already used this coupon maximum times'
                    })
            
            coupon_data = PublicCouponSerializer(coupon).data
            
            return Response({
                'success': True,
                'valid': True,
                'message': 'Coupon is valid',
                'coupon': coupon_data
            })
        
        return Response({
            'success': False,
            'valid': False,
            'message': serializer.errors.get('coupon_code', ['Invalid coupon code'])[0]
        }, status=status.HTTP_400_BAD_REQUEST)


class ProductCouponsAPIView(APIView):
    """Get coupons applicable to a specific product"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, status='approved')
            
            # Get all active coupons
            now = timezone.now()
            coupons = Coupon.objects.filter(
                status='active',
                start_date__lte=now,
                expire_date__gte=now
            ).filter(
                Q(max_count__isnull=True) | Q(used_count__lt=F('max_count'))
            )
            
            applicable_coupons = []
            for coupon in coupons:
                if coupon.can_be_applied_to_product(product):
                    applicable_coupons.append(coupon)
            
            serializer = PublicCouponSerializer(applicable_coupons, many=True)
            
            return Response({
                'success': True,
                'product_id': product_id,
                'product_name': product.product_name,
                'coupons': serializer.data,
                'count': len(applicable_coupons)
            })
            
        except Product.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CartCouponsAPIView(APIView):
    """Get coupons applicable to cart items"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            # Get user's cart items
            cart_items = Cart.objects.filter(customer=request.user).select_related(
                'product_stock', 'product_stock__product'
            )
            
            if not cart_items.exists():
                return Response({
                    'success': True,
                    'message': 'Cart is empty',
                    'coupons': [],
                    'cart_total': 0
                })
            
            # Calculate cart total
            cart_total = Decimal("0.00")
            for item in cart_items:
                cart_total += Decimal(str(item.item_total))
            
            # Get all active coupons
            now = timezone.now()
            all_coupons = Coupon.objects.filter(
                status='active',
                start_date__lte=now,
                expire_date__gte=now
            ).filter(
                Q(max_count__isnull=True) | Q(used_count__lt=F('max_count'))
            )
            
            applicable_coupons = []
            for coupon in all_coupons:
                # Check if coupon is valid for user
                if not coupon.is_valid_for_user(request.user):
                    continue
                
                # Check minimum order value
                if cart_total < Decimal(str(coupon.min_order_value)):
                    continue
                
                # Check if coupon can be applied to any cart item
                coupon_applicable = False
                applicable_items_total = 0
                
                for cart_item in cart_items:
                    product = cart_item.product_stock.product
                    if coupon.can_be_applied_to_product(product):
                        coupon_applicable = True
                        applicable_items_total += cart_item.item_total
                
                if coupon_applicable:
                    coupon_data = PublicCouponSerializer(coupon).data
                    coupon_data['applicable_amount'] = str(applicable_items_total)
                    coupon_data['discount_amount'] = str(
                        coupon.calculate_discount(Decimal(str(applicable_items_total)))
                    )
                    applicable_coupons.append(coupon_data)
            
            return Response({
                'success': True,
                'cart_total': str(cart_total),
                'coupons': applicable_coupons,
                'count': len(applicable_coupons)
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request):
        """Apply coupon to cart"""
        try:
            # Get cart items
            cart_items = Cart.objects.filter(customer=request.user).select_related(
                'product_stock', 'product_stock__product'
            )
            
            if not cart_items.exists():
                return Response({
                    'success': False,
                    'message': 'Cart is empty'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate coupon
            serializer = ApplyCouponSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': serializer.errors.get('coupon_code', ['Invalid coupon code'])[0]
                }, status=status.HTTP_400_BAD_REQUEST)
            
            coupon = serializer.validated_data['coupon_code']
            
            # Check if coupon is valid for user
            if not coupon.is_valid_for_user(request.user):
                return Response({
                    'success': False,
                    'message': 'You have already used this coupon maximum times'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Calculate cart total
            cart_total = Decimal("0.00")
            for item in cart_items:
                cart_total += Decimal(str(item.item_total))
            
            # Check minimum order value
            if cart_total < Decimal(str(coupon.min_order_value)):
                return Response({
                    'success': False,
                    'message': f'Minimum order value for this coupon is ₹{coupon.min_order_value}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Calculate applicable amount and discount
            applicable_items_total = Decimal("0.00")
            applicable_items = []
            
            for cart_item in cart_items:
                product = cart_item.product_stock.product
                if coupon.can_be_applied_to_product(product):
                    applicable_items_total += Decimal(str(cart_item.item_total))
                    applicable_items.append({
                        'product_id': product.id,
                        'product_name': product.product_name,
                        'quantity': cart_item.quantity,
                        'price': str(cart_item.item_total)
                    })
            
            if applicable_items_total == 0:
                return Response({
                    'success': False,
                    'message': 'This coupon cannot be applied to any item in your cart'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Calculate discount
            discount_amount = coupon.calculate_discount(applicable_items_total)
            
            # Store coupon in session for checkout
            request.session['applied_coupon'] = {
                'code': coupon.code,
                'id': coupon.id,
                'discount_amount': str(discount_amount),
                'applicable_items': applicable_items,
                'applicable_amount': str(applicable_items_total)
            }
            request.session.modified = True
            print(type(cart_total))
            print(type(discount_amount))
            coupon_data = PublicCouponSerializer(coupon).data
            final_amount = cart_total - Decimal(str(discount_amount))

            return Response({
                'success': True,
                'message': 'Coupon applied successfully!',
                'coupon': coupon_data,
                'discount_amount': str(discount_amount),
                'applicable_amount': str(applicable_items_total),
                'cart_total': str(cart_total),
                'final_amount': str(final_amount)
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request):
        """Remove applied coupon from cart"""
        try:
            if 'applied_coupon' in request.session:
                del request.session['applied_coupon']
                request.session.modified = True
            
            return Response({
                'success': True,
                'message': 'Coupon removed successfully'
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorCouponsAPIView(APIView):
    """Get coupons for a specific vendor"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, vendor_id):
        try:
            now = timezone.now()
            coupons = Coupon.objects.filter(
                vendor_id=vendor_id,
                status='active',
                start_date__lte=now,
                expire_date__gte=now
            ).filter(
                Q(max_count__isnull=True) | Q(used_count__lt=F('max_count'))
            ).order_by('-created_at')
            
            serializer = PublicCouponSerializer(coupons, many=True)
            
            return Response({
                'success': True,
                'vendor_id': vendor_id,
                'coupons': serializer.data,
                'count': coupons.count()
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def available_coupons_for_product(request, product_id):
    """Get available coupons for a specific product"""
    try:
        from ecommerce.models.product import Product
        product = Product.objects.get(id=product_id, status='approved')
        
        # Get all active coupons
        now = timezone.now()
        coupons = Coupon.objects.filter(
            status='active',
            start_date__lte=now,
            expire_date__gte=now
        ).filter(
            Q(max_count__isnull=True) | Q(used_count__lt=F('max_count'))
        )
        
        applicable_coupons = []
        for coupon in coupons:
            if coupon.can_be_applied_to_product(product):
                applicable_coupons.append(coupon)
        
        serializer = PublicCouponSerializer(applicable_coupons, many=True)
        
        return Response({
            'success': True,
            'product_id': product_id,
            'product_name': product.product_name,
            'coupons': serializer.data,
            'count': len(applicable_coupons)
        })
        
    except Product.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Product not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PublicFeaturedCategoryListAPI(generics.ListAPIView):
    """
    API to get only featured categories
    """
    serializer_class = PublicCategorySerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        # ✅ Only return featured categories that are active
        return Category.objects.filter(
            status=True,
            is_featured=True
        ).order_by('-featured_order', 'name')


class WebHomeCategoriesAPIView(APIView):
    """
    API to get all categories marked as web_home with their products
    Returns: List of categories with their products for homepage sliders
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            # Get all categories with web_home=True and status=True
            categories = Category.objects.filter(
                web_home=True, 
                status=True
            ).order_by('name')
            
            result = []
            
            for category in categories:
                # ✅ FIXED: Use 'status' instead of 'is_active'
                products = Product.objects.filter(
                    category=category,
                    status='approved'  # status field se filter kiya
                ).select_related(
                    'vendor', 'brand'
                ).prefetch_related(
                    Prefetch('stocks', queryset=ProductStock.objects.all()),  # stock filter optional
                    'gallery'
                ).distinct()[:20]
                
                # Serialize products using PublicProductSerializer
                product_serializer = PublicProductSerializer(
                    products, 
                    many=True, 
                    context={'request': request}
                )
                
                # Serialize category
                category_serializer = PublicCategorySerializer(
                    category, 
                    context={'request': request}
                )
                
                # Get total product count for "View All" link
                total_products = Product.objects.filter(
                    category=category, 
                    status='approved'
                ).count()
                
                result.append({
                    'category': category_serializer.data,
                    'products': product_serializer.data,
                    'total_products': total_products
                })
            
            return Response({
                'success': True,
                'count': len(result),
                'data': result
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    def get_serializer_context(self):
        """Add request to serializer context for absolute URLs"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context                
    
    
class ProductSearchAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        search = request.GET.get("query", "").strip()

        print("="*50)
        print(f"🔍 ProductSearchAPIView called with query: '{search}'")
        print("="*50)

        queryset = Product.objects.filter(status="approved").select_related(
            "category", "subcategory", "subsubcategory", "brand", "vendor"
        ).prefetch_related("stocks")

        print(f"📊 Total approved products: {queryset.count()}")

        if search:
            queryset = queryset.filter(
                Q(product_name__icontains=search) |
                Q(sku__icontains=search) |
                Q(product_condition__icontains=search) |
                Q(keywords__icontains=search) |
                Q(category__name__icontains=search) |
                Q(subcategory__name__icontains=search) |
                Q(subsubcategory__name__icontains=search) |
                Q(brand__brand_name__icontains=search) |
                Q(vendor__business_name__icontains=search)
            )

        queryset = queryset[:20]

        result = []

        for product in queryset:
            stock = product.stocks.first()

            price = 0
            variant_image = None

            if stock:
                price = stock.selling_price
                if stock.variant_image:
                    variant_image = request.build_absolute_uri(stock.variant_image.url)

            # Image fallback
            main_image = request.build_absolute_uri(product.main_image.url) if product.main_image else None

            product_data = {
                "id": product.id,
                "productName": product.product_name or "",
                "sku": product.sku or "",
                "productCondition": product.product_condition or "",
                "keywords": product.keywords or "",
                "category": product.category.name if product.category else "",
                "subcategory": product.subcategory.name if product.subcategory else "",
                "subsubcategory": product.subsubcategory.name if product.subsubcategory else "",
                "brand": product.brand.brand_name if product.brand else "",
                "vendor_name": product.vendor.business_name if product.vendor else "",
                "price": price,

                # ✅ Final image logic
                "image": variant_image if variant_image else main_image
            }

            result.append(product_data)

        return Response(result)
    
class SearchProductsAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.GET.get("keywords", "").strip()
        if not query:
            return Response({"error": "Query parameter is required."}, status=400)

        queryset = Product.objects.filter(status="approved").select_related(
            "category", "subcategory", "subsubcategory", "brand"
        )

        queryset = queryset.filter(
            Q(product_name__icontains=query) |
            Q(sku__icontains=query) |
            Q(product_condition__icontains=query) |
            Q(keywords__icontains=query) |
            Q(category__name__icontains=query) |
            Q(subcategory__name__icontains=query) |
            Q(subsubcategory__name__icontains=query) |
            Q(brand__brand_name__icontains=query)
        )[:20]

        serializer = ProductSerializer(queryset, many=True)
        return Response({"products": serializer.data})
    
from django.db.models import Min, Value, DecimalField
from django.db.models.functions import Coalesce

class ProductSortListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):

        sort = request.GET.get("sort")

        # ✅ remove status filter
        qs = Product.objects.filter(status="approved")

        qs = qs.annotate(
            sort_price=Min("stocks__final_price")
        )

        if sort == "price_asc":
            qs = qs.order_by("sort_price")

        elif sort == "price_desc":
            qs = qs.order_by("-sort_price")

        elif sort == "newest":
            qs = qs.order_by("-created_at")

        print("COUNT =", qs.count())  # debug

        serializer = ProductSerializer(qs, many=True)
        return Response(serializer.data)
    
class ProductConditionFilterAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):

        condition_param = request.GET.get("condition")   # new,used
        sort = request.GET.get("sort")

        qs = Product.objects.filter(status="approved")

        # -------------------------
        # CONDITION FILTER
        # -------------------------
        if condition_param:
            conditions = [c.strip() for c in condition_param.split(",")]
            qs = qs.filter(product_condition__in=conditions)

        # -------------------------
        # PRICE ANNOTATE
        # -------------------------
        qs = qs.annotate(
            sort_price=Min("stocks__final_price")
        )

        # -------------------------
        # SORTING (optional)
        # -------------------------
        if sort == "price_asc":
            qs = qs.order_by("sort_price")

        elif sort == "price_desc":
            qs = qs.order_by("-sort_price")

        elif sort == "newest":
            qs = qs.order_by("-created_at")

        else:
            qs = qs.order_by("-created_at")

        print("FILTER CONDITIONS =", condition_param)
        print("COUNT =", qs.count())

        serializer = ProductSerializer(qs, many=True)
        return Response(serializer.data)
    
class VendorSearchAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        search = request.GET.get("query", "").strip()
        if not search:
            return Response([])
        
        # Search vendors by business name
        vendors = Vendor.objects.filter(
            status='active',
            is_approved=True,
            business_name__icontains=search
        )
        result = list(vendors.values('id', 'business_name', 'store_logo')[:10])
        return Response(result)

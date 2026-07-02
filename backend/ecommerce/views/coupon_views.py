# ecommerce/views/coupon_views.py

from rest_framework import viewsets, status, permissions
from ecommerce.models.order import Cart
from ecommerce.models.product import ProductStock
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.db.models import Q, F
from ecommerce.models.product import Product, ProductGallery,ProductStock
from ecommerce.serializers.product_serializers import ProductSerializer
from django.db import transaction
from rest_framework.exceptions import ValidationError
from django.db.models import Q, F
from ecommerce.models.coupon import Coupon, CouponUsage
from ecommerce.serializers.coupon_serializers import (
    CouponSerializer, 
    CouponWriteSerializer,  # ADD THIS
    CouponUsageSerializer,
    ApplyCouponSerializer,
    AvailableCouponSerializer,
    CategorySerializer,
    ProductMinimalSerializer,
    SubCategorySerializer,
    SubSubCategorySerializer,
    CouponReadSerializer
)
from ecommerce.models.product import Product, Category, SubCategory, SubSubCategory
from django.contrib.auth import get_user_model

User = get_user_model()


class IsVendorOrReadOnly(permissions.BasePermission):
    """Permission to allow vendors to create/edit coupons, others can only view"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Only vendors can create/update/delete coupons
        return hasattr(request.user, 'vendor') and request.user.vendor is not None


class VendorCouponViewSet(viewsets.ModelViewSet):

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return CouponReadSerializer
        return CouponWriteSerializer
    
    permission_classes = [permissions.IsAuthenticated]
    
    def _validate_duplicate_coupon(self, vendor, apply_on, products, categories, coupon_id=None):
        """
        Prevent multiple ACTIVE coupons on same product/category
        """

        qs = Coupon.objects.filter(
            vendor=vendor,
            status="active"
        )

        if coupon_id:
            qs = qs.exclude(id=coupon_id)

        # Product level duplicate
        if apply_on == "product" and products:
            if qs.filter(products__in=products).exists():
                raise ValidationError({
                    "products": "One or more selected products already have an active coupon."
                })

        #  Category level duplicate
        if apply_on == "category" and categories:
            if qs.filter(categories__in=categories).exists():
                raise ValidationError({
                    "categories": "One or more selected categories already have an active coupon."
                })


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        vendor = request.user.vendor

        with transaction.atomic():
            self._validate_duplicate_coupon(
                vendor=vendor,
                apply_on=data.get("apply_on"),
                products=data.get("products", []),
                categories=data.get("categories", [])
            )

            coupon = serializer.save(vendor=vendor)

        read_serializer = CouponSerializer(
            coupon,
            context=self.get_serializer_context()
        )

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        """Vendors can only see their own coupons"""
        if hasattr(self.request.user, 'vendor') and self.request.user.vendor:
            return Coupon.objects.filter(vendor=self.request.user.vendor)
        return Coupon.objects.none()
    
    def get_serializer_context(self):
        """Pass request context to serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    @action(detail=False, methods=['get'])
    def vendor_data(self, request):
        """Get vendor's products and categories for dropdowns"""
        try:
            if not hasattr(request.user, 'vendor') or not request.user.vendor:
                return Response(
                    {"error": "Vendor not found"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            vendor = request.user.vendor
            
            # Get vendor's approved products
            products = Product.objects.filter(vendor=vendor, status="approved")
            
            # Get DISTINCT categories from vendor's products
            category_ids = products.filter(category__isnull=False) \
                                 .values_list('category__id', flat=True) \
                                 .distinct()
            categories = Category.objects.filter(id__in=category_ids)
            
            # Get DISTINCT subcategories
            subcategory_ids = products.filter(subcategory__isnull=False) \
                                    .values_list('subcategory__id', flat=True) \
                                    .distinct()
            subcategories = SubCategory.objects.filter(id__in=subcategory_ids)
            
            # Get DISTINCT subsubcategories
            subsubcategory_ids = products.filter(subsubcategory__isnull=False) \
                                       .values_list('subsubcategory__id', flat=True) \
                                       .distinct()
            subsubcategories = SubSubCategory.objects.filter(id__in=subsubcategory_ids)
            
            # Serialize data
            product_serializer = ProductMinimalSerializer(products, many=True)
            category_serializer = CategorySerializer(categories, many=True)
            subcategory_serializer = SubCategorySerializer(subcategories, many=True)
            subsubcategory_serializer = SubSubCategorySerializer(subsubcategories, many=True)
            
            return Response({
                'success': True,
                'products': product_serializer.data,
                'categories': category_serializer.data,
                'subcategories': subcategory_serializer.data,
                'subsubcategories': subsubcategory_serializer.data,
                'counts': {
                    'products': products.count(),
                    'categories': categories.count(),
                    'subcategories': subcategories.count(),
                    'subsubcategories': subsubcategories.count()
                }
            })
            
        except Exception as e:
            print(f"Error in vendor_data: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return Response({
                'error': str(e),
                'details': 'Internal server error in vendor_data endpoint'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def usage_stats(self, request, pk=None):
        """Get usage statistics for a coupon"""
        coupon = self.get_object()
        usages = CouponUsage.objects.filter(coupon=coupon)
        
        data = {
            'coupon': CouponSerializer(coupon).data,
            'total_usage': usages.count(),
            'usage_by_user': {},
            'recent_usages': CouponUsageSerializer(usages[:10], many=True).data
        }
        
        # Group by user
        for usage in usages[:20]:  # Limit to first 20 users
            user_email = usage.user.email
            if user_email not in data['usage_by_user']:
                data['usage_by_user'][user_email] = 0
            data['usage_by_user'][user_email] += 1
        
        return Response(data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        partial = kwargs.pop('partial', False)

        write_serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial
        )
        write_serializer.is_valid(raise_exception=True)

        data = write_serializer.validated_data
        vendor = request.user.vendor

        with transaction.atomic():
            self._validate_duplicate_coupon(
                vendor=vendor,
                apply_on=data.get("apply_on", instance.apply_on),
                products=data.get("products", instance.products.all()),
                categories=data.get("categories", instance.categories.all()),
                coupon_id=instance.id
            )

            coupon = write_serializer.save()

        read_serializer = CouponSerializer(
            coupon,
            context=self.get_serializer_context()
        )

        return Response(read_serializer.data)

class CouponCheckoutAPIView(APIView):
    """API for checkout-related coupon operations"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get available coupons for current user's cart"""
        # Get cart items from session or request
        cart_items = request.session.get('cart', [])
        
        if not cart_items:
            return Response([])
        
        # Get all valid coupons
        now = timezone.now()
        valid_coupons = Coupon.objects.filter(
            status='active',
            start_date__lte=now,
            expire_date__gte=now
        ).filter(
            Q(max_count__isnull=True) | Q(used_count__lt=F('max_count'))
        )
        
        # Filter coupons that can be applied to cart items
        available_coupons = []
        for coupon in valid_coupons:
            applicable_items = []
            for item in cart_items:
                product_id = item.get('product_id')
                if not product_id:
                    continue
                    
                try:
                    product = Product.objects.get(id=product_id)
                    if coupon.can_be_applied_to_product(product):
                        applicable_items.append({
                            'product': product,
                            'quantity': item.get('quantity', 1),
                            'price': item.get('price', 0)
                        })
                except Product.DoesNotExist:
                    continue
            
            if applicable_items:
                # Calculate total applicable amount
                total_applicable_amount = Decimal("0.00")

                for item in applicable_items:
                    price = Decimal(str(item['price']))
                    quantity = Decimal(str(item['quantity']))
                    total_applicable_amount += price * quantity
                
                
                if total_applicable_amount >= coupon.min_order_value:
                    coupon_data = AvailableCouponSerializer(coupon).data
                    coupon_data['applicable_items'] = applicable_items
                    coupon_data['total_applicable_amount'] = total_applicable_amount
                    available_coupons.append(coupon_data)
        
        return Response(available_coupons)
    
    def post(self, request):
        from decimal import Decimal
        from ecommerce.models.order import Cart

        # Get DB cart items
        cart_items = Cart.objects.filter(customer=request.user).select_related(
            'product_stock',
            'product_stock__product'
        )

        if not cart_items.exists():
            return Response({
                "success": False,
                "message": "Cart is empty"
            }, status=400)

        coupon_code = request.data.get("coupon_code", "").upper().strip()

        try:
            coupon = Coupon.objects.get(code=coupon_code)
        except Coupon.DoesNotExist:
            return Response({
                "success": False,
                "message": "Invalid coupon code"
            }, status=400)

        if not coupon.is_valid():
            return Response({
                "success": False,
                "message": "Coupon expired or inactive"
            }, status=400)

        total_applicable_amount = Decimal("0.00")
        applicable_items = []

        for item in cart_items:
            product = item.product_stock.product
            price = Decimal(str(item.product_stock.price))
            quantity = Decimal(str(item.quantity))

            if coupon.can_be_applied_to_product(product):
                line_total = price * quantity
                total_applicable_amount += line_total

                applicable_items.append(item)

        if total_applicable_amount < coupon.min_order_value:
            return Response({
                "success": False,
                "message": f"Minimum order value should be ₹{coupon.min_order_value}"
            }, status=400)

        discount = coupon.calculate_discount(total_applicable_amount)

        if discount > total_applicable_amount:
            discount = total_applicable_amount

        final_total = total_applicable_amount - discount

        return Response({
            "success": True,
            "coupon_code": coupon.code,
            "discount_amount": str(discount),
            "total_applicable_amount": str(total_applicable_amount),
            "final_total": str(final_total)
        })
    
    def delete(self, request):
        """Remove applied coupon"""
        if 'applied_coupon' in request.session:
            del request.session['applied_coupon']
            request.session.modified = True
        
        return Response({
            'success': True,
            'message': 'Coupon removed successfully!'
        })


class PublicCouponAPIView(APIView):
    """Public API for coupon validation"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """Validate coupon code"""
        coupon_code = request.data.get('coupon_code', '').upper().strip()
        
        if not coupon_code:
            return Response({
                'valid': False,
                'message': 'Coupon code is required.'
            })
        
        try:
            coupon = Coupon.objects.get(code=coupon_code)
        except Coupon.DoesNotExist:
            return Response({
                'valid': False,
                'message': 'Invalid coupon code.'
            })
        
        # Check validity
        if not coupon.is_valid():
            return Response({
                'valid': False,
                'message': 'This coupon is not valid or has expired.'
            })
        
        return Response({
            'valid': True,
            'coupon': AvailableCouponSerializer(coupon).data
        })


class CustomerCouponUsageViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for customers to view their coupon usage"""
    serializer_class = CouponUsageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CouponUsage.objects.filter(user=self.request.user)

    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return coupon usages for current user"""
        return CouponUsage.objects.filter(user=self.request.user)

class VendorCouponDataAPIView(APIView):
    """API to get vendor's data for coupon creation"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get vendor's products and categories"""
        try:
            if not hasattr(request.user, 'vendor') or not request.user.vendor:
                return Response(
                    {"error": "Vendor not found"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            vendor = request.user.vendor
            
            # Get vendor's approved products
            products = Product.objects.filter(vendor=vendor, status="approved")
            
            # Get categories from products
            category_ids = products.filter(category__isnull=False) \
                                 .values_list('category__id', flat=True) \
                                 .distinct()
            categories = Category.objects.filter(id__in=category_ids)
            
            # Get subcategories
            subcategory_ids = products.filter(subcategory__isnull=False) \
                                    .values_list('subcategory__id', flat=True) \
                                    .distinct()
            subcategories = SubCategory.objects.filter(id__in=subcategory_ids)
            
            # Get subsubcategories
            subsubcategory_ids = products.filter(subsubcategory__isnull=False) \
                                       .values_list('subsubcategory__id', flat=True) \
                                       .distinct()
            subsubcategories = SubSubCategory.objects.filter(id__in=subsubcategory_ids)
            
            # Serialize
            product_serializer = ProductMinimalSerializer(products, many=True)
            category_serializer = CategorySerializer(categories, many=True)
            subcategory_serializer = SubCategorySerializer(subcategories, many=True)
            subsubcategory_serializer = SubSubCategorySerializer(subsubcategories, many=True)
            
            return Response({
                'success': True,
                'products': product_serializer.data,
                'categories': category_serializer.data,
                'subcategories': subcategory_serializer.data,
                'subsubcategories': subsubcategory_serializer.data,
                'counts': {
                    'products': products.count(),
                    'categories': categories.count(),
                    'subcategories': subcategories.count(),
                    'subsubcategories': subsubcategories.count()
                }
            })
            
        except Exception as e:
            print(f"Error getting vendor data: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)    

class CouponProductsView(APIView):
    """API to get products that a coupon can be applied to"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, coupon_id):
        try:
            # 🔐 Vendor ka hi coupon
            coupon = Coupon.objects.get(
                id=coupon_id,
                vendor=request.user.vendor
            )

            products = Product.objects.none()

            # 🎯 CATEGORY BASED COUPON
            if coupon.apply_on == "category":

                if coupon.subsubcategories.exists():
                    products = Product.objects.filter(
                        subsubcategory__in=coupon.subsubcategories.all(),
                        vendor=request.user.vendor,
                        status="approved"
                    )

                elif coupon.subcategories.exists():
                    products = Product.objects.filter(
                        subcategory__in=coupon.subcategories.all(),
                        vendor=request.user.vendor,
                        status="approved"
                    )

                elif coupon.categories.exists():
                    products = Product.objects.filter(
                        category__in=coupon.categories.all(),
                        vendor=request.user.vendor,
                        status="approved"
                    )

            # 🎯 PRODUCT BASED COUPON
            elif coupon.apply_on == "product":
                products = coupon.products.filter(
                    vendor=request.user.vendor,
                    status="approved"
                )

            # 🔃 Sorting
            products = products.order_by("product_name")

            serializer = ProductSerializer(
                products,
                many=True,
                context={"request": request}
            )

            return Response({
                "success": True,
                "coupon": {
                    "id": coupon.id,
                    "code": coupon.code,
                    "title": coupon.title,
                    "apply_on": coupon.apply_on,
                },
                "products": serializer.data,
                "count": products.count()
            })

        except Coupon.DoesNotExist:
            return Response(
                {"success": False, "error": "Coupon not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ecommerce/views/coupon_views.py mein naya view add karen

class VendorCouponUsageDetailsView(APIView):
    """Get detailed coupon usage for vendor's own products only"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, coupon_id):
        try:
            # 🔐 Vendor ka hi coupon
            coupon = Coupon.objects.get(
                id=coupon_id,
                vendor=request.user.vendor
            )
            
            # Get all coupon usages for this coupon
            coupon_usages = CouponUsage.objects.filter(coupon=coupon).select_related(
                'user', 'order'
            )
            
            detailed_usage = []
            total_discount_given = 0
            total_vendor_amount = 0
            
            for usage in coupon_usages:
                if usage.order:
                    # Get order items for this vendor only
                    order_items = usage.order.items.filter(vendor=request.user.vendor)
                    
                    if order_items.exists():
                        # Calculate vendor's total from this order
                        vendor_items_total = Decimal("0.00")

                        for item in order_items:
                            vendor_items_total += Decimal(str(item.total_price))
                        
                        # Calculate applicable discount proportion for vendor's items
                        order_total = Decimal(str(usage.order.total_amount))
                        if order_total > 0:
                            discount_amount = Decimal(str(usage.discount_amount))
                            vendor_discount_share = (vendor_items_total / order_total) * discount_amount
                        else:
                            vendor_discount_share = Decimal("0.00")
                        
                        # Prepare vendor's products details
                        vendor_products = []
                        for item in order_items:
                            vendor_products.append({
                                'product_id': item.product.id,
                                'product_name': item.product_name,
                                'quantity': item.quantity,
                                'unit_price': str(item.unit_price),
                                'total_price': str(item.total_price)
                            })
                        
                        detailed_usage.append({
                            'usage_id': usage.id,
                            'user_email': usage.user.email,
                            'order_id': usage.order.id,
                            'order_number': usage.order.order_number,
                            'order_date': usage.order.created_at,
                            'discount_amount': str(usage.discount_amount),
                            'vendor_discount_share': vendor_discount_share,
                            'used_at': usage.used_at,
                            'vendor_products': vendor_products,
                            'total_vendor_amount': vendor_items_total,
                            'payment_status': usage.order.payment_status,
                            'order_status': usage.order.order_status
                        })
                        
                        total_discount_given += vendor_discount_share
                        total_vendor_amount += vendor_items_total
            
            # Get applicable products for this coupon
            products = Product.objects.none()
            
            if coupon.apply_on == "category":
                if coupon.subsubcategories.exists():
                    products = Product.objects.filter(
                        subsubcategory__in=coupon.subsubcategories.all(),
                        vendor=request.user.vendor,
                        status="approved"
                    )
                elif coupon.subcategories.exists():
                    products = Product.objects.filter(
                        subcategory__in=coupon.subcategories.all(),
                        vendor=request.user.vendor,
                        status="approved"
                    )
                elif coupon.categories.exists():
                    products = Product.objects.filter(
                        category__in=coupon.categories.all(),
                        vendor=request.user.vendor,
                        status="approved"
                    )
            elif coupon.apply_on == "product":
                products = coupon.products.filter(
                    vendor=request.user.vendor,
                    status="approved"
                )
            
            # Statistics
            total_usage_count = len(detailed_usage)
            avg_discount_per_order = Decimal("0.00")
            avg_order_value = Decimal("0.00")

            if total_usage_count > 0:
                avg_discount_per_order = total_discount_given / Decimal(str(total_usage_count))
                avg_order_value = total_vendor_amount / Decimal(str(total_usage_count))
            
            return Response({
                "success": True,
                "coupon": {
                    "id": coupon.id,
                    "code": coupon.code,
                    "title": coupon.title,
                    "apply_on": coupon.apply_on,
                    "coupon_type": coupon.coupon_type,
                    "discount_percent": coupon.discount_percent,
                    "discount_amount": coupon.discount_amount,
                    "min_order_value": str(coupon.min_order_value),
                    "max_count": coupon.max_count,
                    "used_count": coupon.used_count,
                    "remaining_uses": coupon.max_count - coupon.used_count if coupon.max_count else None,
                    "status": coupon.status,
                    "start_date": coupon.start_date,
                    "expire_date": coupon.expire_date,
                    "is_valid": coupon.is_valid()
                },
                "usage_data": detailed_usage,
                "statistics": {
                    "total_usage_count": total_usage_count,
                    "total_discount_given": str(total_discount_given.quantize(Decimal("0.01"))),
                    "total_vendor_sales": str(total_vendor_amount.quantize(Decimal("0.01"))),
                    "average_discount_per_order": str(avg_discount_per_order.quantize(Decimal("0.01"))),
                    "average_order_value": str(avg_order_value.quantize(Decimal("0.01")))
                },
                "count": {
                    "products": products.count(),
                    "usages": total_usage_count
                }
            })

        except Coupon.DoesNotExist:
            return Response(
                {"success": False, "error": "Coupon not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"Error in VendorCouponUsageDetailsView: {str(e)}")
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
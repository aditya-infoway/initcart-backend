# pos/views/website_item_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework import status
from django.db.models import Q
from django.shortcuts import get_object_or_404

from pos.models.items import items
from pos.serializers.item_serializers import (
    WebsiteItemListSerializer,
    ApproveItemToProductSerializer,
    ItemWithVariantsSerializer
)
from pos.services.item_product_sync import ItemToProductSyncService
from ecommerce.permissions import IsSuperAdmin


# pos/views/website_item_views.py

from rest_framework.pagination import PageNumberPagination

class WebsiteItemsListAPI(APIView):
    """List all items from branch that are marked for website display"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def get(self, request):
        branch = getattr(request.user, 'branch', None)
        
        if not branch:
            return Response(
                {"error": "User has no branch associated"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get items from this branch that are marked for website display
        items_qs = items.objects.filter(
            branch=branch,
            website_display=True
        ).order_by('-created_at')
        
        # Optional filters
        status_filter = request.GET.get('status')
        if status_filter and status_filter != 'all':
            items_qs = items_qs.filter(website_status=status_filter)
        
        search = request.GET.get('search')
        if search:
            items_qs = items_qs.filter(
                Q(itemName__icontains=search) |
                Q(category__icontains=search) |
                Q(brand__icontains=search)
            )
        
        # Pagination parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 15))
        
        # Calculate pagination
        total_count = items_qs.count()
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1
        
        # Ensure page is within bounds
        page = max(1, min(page, total_pages if total_pages > 0 else 1))
        
        # Calculate offset and limit
        offset = (page - 1) * page_size
        paginated_items = items_qs[offset:offset + page_size]
        
        # Serialize the paginated items
        serializer = WebsiteItemListSerializer(paginated_items, many=True)
        
        # Return paginated response
        return Response({
            "success": True,
            "branch_type": branch.branch_type,
            "count": total_count,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": page_size,
            "next": f"?page={page + 1}&page_size={page_size}" if page < total_pages else None,
            "previous": f"?page={page - 1}&page_size={page_size}" if page > 1 else None,
            "items": serializer.data
        }, status=status.HTTP_200_OK)


class WebsiteItemDetailAPI(APIView):
    """Get details of a single item for website display"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def get(self, request, pk):
        branch = getattr(request.user, 'branch', None)
        
        if not branch:
            return Response(
                {"error": "User has no branch associated"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            item = items.objects.select_related(
                'c_brand', 'c_category', 'c_subCategory', 'c_subSubCategory', 'branch'
            ).prefetch_related('variants').get(id=pk, branch=branch)
            serializer = ItemWithVariantsSerializer(item)
            
            # Log for debugging
            print(f"🔍 Item data for {pk}: {serializer.data}")
            
            # Return data in the format frontend expects
            return Response({
                "item": serializer.data
            }, status=status.HTTP_200_OK)
            
        except items.DoesNotExist:
            return Response(
                {"error": "Item not found"},
                status=status.HTTP_404_NOT_FOUND
            )

class UpdateWebsiteItemAPI(APIView):
    """Update item and sync changes to linked product"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def put(self, request, pk):
        return self._update_item(request, pk)
    
    def patch(self, request, pk):
        return self._update_item(request, pk)
    
    def _update_item(self, request, pk):
        import json
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from django.utils import timezone
        
        branch = getattr(request.user, 'branch', None)  
        
        if not branch:
            return Response(
                {"error": "User has no branch associated"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            item = items.objects.get(id=pk, branch=branch)
        except items.DoesNotExist:
            return Response(
                {"error": "Item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        print(f"\n{'='*60}")
        print(f"📥 UPDATING ITEM {pk}: {item.itemName}")
        print(f"{'='*60}")
        
        # Debug: Print all incoming data
        print("📋 REQUEST DATA:")
        for key, value in request.data.items():
            print(f"  {key}: {str(value)[:100]}...")
        
        # If item was approved and now being edited, set status to pending
        original_status = item.website_status
        if original_status == 'approved':
            item.website_status = 'pending'
            print(f"🔄 Status changed to pending")
        
        # ========== HANDLE IMAGES ==========
        
        if 'main_image' in request.FILES:
            item.main_image = request.FILES['main_image']
            print(f"✅ Updated main_image")
        
        if 'thumbnail_image' in request.FILES:
            item.thumbnail_image = request.FILES['thumbnail_image']
            print(f"✅ Updated thumbnail_image")
        
        # Handle variant images
        for key in request.FILES:
            if key.startswith('variant_images_'):
                try:
                    variant_index = int(key.split('_')[-1])
                    variants = list(item.variants.all())
                    if variant_index < len(variants):
                        variant = variants[variant_index]
                        variant.variant_image = request.FILES[key]
                        variant.save()
                        print(f"✅ Updated variant {variant_index} image")
                except (ValueError, IndexError):
                    pass
        
        # Handle gallery images
        gallery_images = request.FILES.getlist('gallery_images')
        if gallery_images:
            print(f"📸 Received {len(gallery_images)} new gallery images")
            existing_gallery = item.gallery or []
            if not isinstance(existing_gallery, list):
                existing_gallery = []
            
            for img in gallery_images:
                timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
                filename = f"items/gallery/{item.id}_{timestamp}_{img.name}"
                saved_path = default_storage.save(filename, ContentFile(img.read()))
                existing_gallery.append(saved_path)
                print(f"✅ Saved gallery image: {saved_path}")
            
            item.gallery = existing_gallery
        
        # Handle existing gallery URLs
        if 'existing_gallery_urls' in request.data:
            existing_urls = request.data['existing_gallery_urls']
            if isinstance(existing_urls, str):
                try:
                    existing_urls = json.loads(existing_urls)
                    # Clean URLs to just paths
                    cleaned_urls = []
                    for url in existing_urls:
                        if isinstance(url, str):
                            # Remove base URL if present
                            if 'http://localhost:8000' in url:
                                url = url.replace('http://localhost:8000', '')
                            cleaned_urls.append(url)
                    item.gallery = cleaned_urls
                    print(f"📸 Keeping {len(cleaned_urls)} existing gallery images")
                except json.JSONDecodeError as e:
                    print(f"⚠️ Error parsing existing_gallery_urls: {e}")
        
        # ========== HANDLE TEXT FIELDS (CRITICAL) ==========
        
        # Short Description
        if 'short_description' in request.data:
            value = request.data['short_description']
            item.short_description = str(value).strip() if value and value != 'null' else ''
            print(f"✅ short_description: '{item.short_description[:50] if item.short_description else 'EMPTY'}'")
        
        # Full Description
        if 'full_description' in request.data:
            value = request.data['full_description']
            item.full_description = str(value).strip() if value and value != 'null' else ''
            print(f"✅ full_description: '{item.full_description[:50] if item.full_description else 'EMPTY'}'")
        
        # Keywords
        if 'keywords' in request.data:
            value = request.data['keywords']
            item.keywords = str(value).strip() if value and value != 'null' else ''
            print(f"✅ keywords: '{item.keywords[:50] if item.keywords else 'EMPTY'}'")
        
        # Product Condition
        if 'product_condition' in request.data:
            value = request.data['product_condition']
            item.product_condition = str(value).strip() if value and value != 'null' else 'New'
            print(f"✅ product_condition: {item.product_condition}")
        
        # Return Policy
        if 'return_policy' in request.data:
            value = request.data['return_policy']
            item.return_policy = str(value).strip() if value and value != 'null' else ''
            print(f"✅ return_policy: '{item.return_policy[:50] if item.return_policy else 'EMPTY'}'")
        
        # Estimated Delivery Time
        if 'estimated_delivery_time' in request.data:
            value = request.data['estimated_delivery_time']
            item.estimated_delivery_time = str(value).strip() if value and value != 'null' else ''
            print(f"✅ estimated_delivery_time: {item.estimated_delivery_time}")
        
        # ========== BOOLEAN FIELDS ==========
        
        if 'free_shipping' in request.data:
            value = request.data['free_shipping']
            if isinstance(value, str):
                item.free_shipping = value.lower() in ['true', '1', 'yes', 'on']
            else:
                item.free_shipping = bool(value)
            print(f"✅ free_shipping: {item.free_shipping}")
        
        if 'warranty_available' in request.data:
            value = request.data['warranty_available']
            if isinstance(value, str):
                item.warranty_available = value.lower() in ['true', '1', 'yes', 'on']
            else:
                item.warranty_available = bool(value)
            print(f"✅ warranty_available: {item.warranty_available}")
        
        # ========== WARRANTY TEXT FIELDS ==========
        
        if 'warranty_period' in request.data:
            value = request.data['warranty_period']
            item.warranty_period = str(value).strip() if value and value != 'null' else ''
            print(f"✅ warranty_period: {item.warranty_period}")
        
        if 'warranty_type' in request.data:
            value = request.data['warranty_type']
            item.warranty_type = str(value).strip() if value and value != 'null' else ''
            print(f"✅ warranty_type: {item.warranty_type}")
        
        if 'warranty_description' in request.data:
            value = request.data['warranty_description']
            item.warranty_description = str(value).strip() if value and value != 'null' else ''
            print(f"✅ warranty_description: '{item.warranty_description[:50] if item.warranty_description else 'EMPTY'}'")
        
        # ========== JSON FIELDS ==========
        
        # Description Features
        if 'description_features' in request.data:
            value = request.data['description_features']
            print(f"📝 description_features raw type: {type(value)}")
            
            if isinstance(value, str) and value and value != 'null':
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        item.description_features = parsed
                        print(f"✅ description_features parsed: {len(parsed)} items")
                    else:
                        item.description_features = []
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON decode error: {e}")
                    item.description_features = []
            elif isinstance(value, list):
                item.description_features = value
                print(f"✅ description_features as list: {len(value)} items")
            else:
                item.description_features = []
        
        # Specifications
        if 'specifications' in request.data:
            value = request.data['specifications']
            print(f"📝 specifications raw type: {type(value)}")
            
            if isinstance(value, str) and value and value != 'null':
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        item.specifications = parsed
                        print(f"✅ specifications parsed: {len(parsed)} items")
                    else:
                        item.specifications = []
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    item.specifications = []
            elif isinstance(value, list):
                item.specifications = value
                print(f"✅ specifications as list: {len(value)} items")
            else:
                item.specifications = []
        
        # Status
        if 'website_status' in request.data:
            item.website_status = request.data['website_status']
            print(f"✅ website_status: {item.website_status}")
        
        # ========== SAVE THE ITEM ==========
        
        try:
            item.save()
            print(f"\n💾 ITEM SAVED SUCCESSFULLY!")
            print(f"   📝 short_description: '{item.short_description[:50] if item.short_description else 'EMPTY'}'")
            print(f"   📝 full_description: '{item.full_description[:50] if item.full_description else 'EMPTY'}'")
            print(f"   📝 keywords: '{item.keywords[:50] if item.keywords else 'EMPTY'}'")
            print(f"   📋 description_features: {len(item.description_features) if item.description_features else 0} items")
            print(f"   📋 specifications: {len(item.specifications) if item.specifications else 0} items")
            print(f"   🖼️ gallery: {len(item.gallery) if item.gallery else 0} images")
            print(f"{'='*60}\n")
        except Exception as e:
            print(f"❌ Error saving item: {e}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": f"Failed to save item: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Refresh serializer
        serializer = ItemWithVariantsSerializer(item)
        
        # If item has a linked product, update it
        if item.linked_product:
            success, message, product_id = ItemToProductSyncService.update_product_from_item(pk)
            if not success:
                print(f"⚠️ Product update warning: {message}")
        
        message = "Item updated successfully"
        if original_status == 'approved' and item.website_status == 'pending':
            message = "Item updated and sent for re-approval."
        
        return Response({
            "success": True,
            "message": message,
            "item": serializer.data
        }, status=status.HTTP_200_OK)
        
#  NEW: Delete website item and optionally its linked product
class DeleteWebsiteItemAPI(APIView):
    """Delete item and optionally its linked product"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def delete(self, request, pk):
        branch = getattr(request.user, 'branch', None)
        
        if not branch:
            return Response(
                {"error": "User has no branch associated"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            item = items.objects.get(id=pk, branch=branch)
        except items.DoesNotExist:
            return Response(
                {"error": "Item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Optionally delete linked product
        delete_product = request.query_params.get('delete_product', 'false').lower() == 'true'
        
        if delete_product and item.linked_product:
            item.linked_product.delete()
        
        item.delete()
        
        return Response({
            "success": True,
            "message": "Item deleted successfully"
        }, status=status.HTTP_200_OK)


class AdminWebsiteItemsListAPI(APIView):
    """Admin view to list all items pending for website approval"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def get(self, request):
        # Get all items marked for website display
        items_qs = items.objects.filter(
            website_display=True
        ).select_related(
            'branch', 'c_brand', 'c_category', 'c_subCategory', 'c_subSubCategory'
        ).prefetch_related('variants').order_by('-created_at')
        
        # Filter by status
        status_filter = request.GET.get('status', 'pending')
        if status_filter:
            items_qs = items_qs.filter(website_status=status_filter)
        
        #  Fix: Filter by branch - handle both ID and name
        branch_filter = request.GET.get('branch')
        if branch_filter:
            # Try to filter by ID first (if numeric)
            if branch_filter.isdigit():
                items_qs = items_qs.filter(branch_id=int(branch_filter))
            else:
                # Filter by branch name (case-insensitive)
                items_qs = items_qs.filter(branch__branch_name__icontains=branch_filter)
        
        # Use the serializer that includes all fields
        from pos.serializers.item_serializers import AdminWebsiteItemListSerializer
        serializer = AdminWebsiteItemListSerializer(items_qs, many=True)
        
        return Response({
            "success": True,
            "count": items_qs.count(),
            "status_filter": status_filter,
            "items": serializer.data
        }, status=status.HTTP_200_OK)

# NEW: Admin approve/reject item to create product
class AdminApproveWebsiteItemAPI(APIView):
    """Admin approve or reject item for website display"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def patch(self, request, pk):
        try:
            item = items.objects.get(id=pk)
        except items.DoesNotExist:
            return Response(
                {"error": "Item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ApproveItemToProductSerializer(item, data=request.data, partial=True)
        
        if serializer.is_valid():
            updated_item = serializer.save()
            
            message = f"Item {updated_item.website_status}"
            if updated_item.website_status == 'approved' and updated_item.linked_product:
                message = f"Item approved and product created successfully (Product ID: {updated_item.linked_product.id})"
            elif updated_item.website_status == 'approved':
                message = "Item approved but product creation may have issues"
            
            return Response({
                "success": True,
                "message": message,
                "item": {
                    "id": updated_item.id,
                    "name": updated_item.itemName,
                    "status": updated_item.website_status,
                    "linked_product_id": updated_item.linked_product.id if updated_item.linked_product else None
                }
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


#     NEW: Manual sync item to product (force sync)
class ManualSyncItemToProductAPI(APIView):
    """Manually sync an item to product (for debugging/recovery)"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def post(self, request, pk):
        try:
            item = items.objects.get(id=pk)
        except items.DoesNotExist:
            return Response(
                {"error": "Item not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        success, message, product_id = ItemToProductSyncService.sync_item_to_product(pk)
        
        if success:
            return Response({
                "success": True,
                "message": message,
                "product_id": product_id
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "success": False,
                "error": message
            }, status=status.HTTP_400_BAD_REQUEST)


#    NEW: Dashboard stats for website items
class WebsiteItemsDashboardAPI(APIView):
    """Get dashboard statistics for website items"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    
    def get(self, request):
        user = request.user
        
        # Check if user is admin or branch user
        if hasattr(user, 'branch'):
            # Branch user stats
            branch = user.branch
            items_qs = items.objects.filter(branch=branch, website_display=True)
            
            stats = {
                "total_items": items_qs.count(),
                "pending": items_qs.filter(website_status='pending').count(),
                "approved": items_qs.filter(website_status='approved').count(),
                "rejected": items_qs.filter(website_status='rejected').count(),
                "draft": items_qs.filter(website_status='draft').count(),
                "total_variants": sum(item.variants.count() for item in items_qs),
                "total_stock": sum(
                    sum(v.current_stock or v.opStock for v in item.variants.all())
                    for item in items_qs
                )
            }
        else:
            # Admin stats - all items across branches
            items_qs = items.objects.filter(website_display=True)
            
            stats = {
                "total_items": items_qs.count(),
                "pending": items_qs.filter(website_status='pending').count(),
                "approved": items_qs.filter(website_status='approved').count(),
                "rejected": items_qs.filter(website_status='rejected').count(),
                "draft": items_qs.filter(website_status='draft').count(),
                "total_branches": items_qs.values('branch').distinct().count(),
                "total_variants": sum(item.variants.count() for item in items_qs)
            }
        
        return Response(stats, status=status.HTTP_200_OK)
    

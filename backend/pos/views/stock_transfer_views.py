# pos/views/stock_transfer_views.py
# COMPLETE SIMPLIFIED VERSION - No matching logic anywhere

from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.db.models import Sum

from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants
from pos.serializers.stock_transfer_serializers import (
    StockTransferCreateSerializer,
    StockTransferDetailSerializer,
    StockTransferListSerializer,
    variant_info_str,
)
from pos.utils.pagination import StandardResultsSetPagination

class IsSuperAdminRole(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'superadmin'


# ════════════════════════════════════════════════════════════
# STOCK TRANSFER VIEWSET
# ════════════════════════════════════════════════════════════
class StockTransferViewSet(ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsSuperAdminRole]
    http_method_names      = ['get', 'post', 'patch', 'delete']

    def get_queryset(self):
        qs = StockTransfer.objects.prefetch_related('items').all()
        if to_branch := self.request.query_params.get('to_branch'):
            qs = qs.filter(to_branch_id=to_branch)
        if status := self.request.query_params.get('status'):
            qs = qs.filter(status=status)
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return StockTransferCreateSerializer
        if self.action == 'list':
            return StockTransferListSerializer
        return StockTransferDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = StockTransferCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            transfer = serializer.save()
            detail = StockTransferDetailSerializer(transfer)
            return Response({
                'success': True,
                'message': 'Stock Transfer created successfully.',
                'data': detail.data
            }, status=201)
        return Response({'success': False, 'errors': serializer.errors}, status=400)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serialized = StockTransferListSerializer(page, many=True).data
            response = paginator.get_paginated_response(serialized)
            response.data['success'] = True
            return response
        return Response({
            'success': True,
            'data': StockTransferListSerializer(qs, many=True).data,
            'count': qs.count()
        })

    def retrieve(self, request, *args, **kwargs):
        return Response({
            'success': True, 
            'data': StockTransferDetailSerializer(self.get_object()).data
        })

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        transfer = self.get_object()

        if transfer.status == 'completed':
            return Response({'success': False, 'message': 'Already completed.'}, status=400)
        if transfer.status == 'cancelled':
            return Response({'success': False, 'message': 'Cannot complete a cancelled transfer.'}, status=400)

        transfer.status = 'completed'
        transfer.save(update_fields=['status'])

        return Response({
            'success': True,
            'message': f'Transfer {transfer.transfer_no} completed and ready for branch verification.',
            'data': StockTransferDetailSerializer(transfer).data
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status == 'completed':
            return Response({'success': False, 'message': 'Cannot cancel a completed transfer.'}, status=400)
        transfer.status = 'cancelled'
        transfer.save(update_fields=['status'])
        return Response({'success': True, 'message': 'Transfer cancelled.'})


# ════════════════════════════════════════════════════════════
# PREVIEW API (No Matching)
# ════════════════════════════════════════════════════════════
class StockTransferPreviewView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsSuperAdminRole]

    def post(self, request):
        to_branch_id = request.data.get('to_branch_id')
        items_data   = request.data.get('items', [])

        if not to_branch_id:
            return Response({'success': False, 'message': 'Destination branch not selected.'}, status=400)

        try:
            to_branch = Branch.objects.get(id=to_branch_id)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Destination branch not found.'}, status=404)

        preview = []
        total_items = 0
        low_stock_count = 0

        for item_data in items_data:
            try:
                from_variant = ItemVariants.objects.select_related('item').get(
                    id=item_data['from_variant_id']
                )
            except ItemVariants.DoesNotExist:
                continue

            quantity = item_data.get('quantity', 0)
            current_stock = from_variant.current_stock or 0
            sufficient = current_stock >= quantity
            
            total_items += 1
            if not sufficient:
                low_stock_count += 1

            # Check if item exists in destination branch
            dest_item_exists = Items.objects.filter(
                branch=to_branch,
                itemName=from_variant.item.itemName,
                created_by_superadmin=True
            ).exists()
            
            # Check if variant exists in destination branch
            dest_variant_exists = ItemVariants.objects.filter(
                item__branch=to_branch,
                item__itemName=from_variant.item.itemName,
                size=from_variant.size,
                color=from_variant.color,
            ).exists() if dest_item_exists else False

            preview.append({
                'from_variant_id':   from_variant.id,
                'from_item_name':    from_variant.item.itemName,
                'from_variant_info': variant_info_str(from_variant),
                'from_barcode':      from_variant.barcode,
                'from_hsnCode':      from_variant.item.hsnCode or "",
                'from_taxSlab':      from_variant.item.taxSlab or "0%",
                'current_stock':     current_stock,
                'quantity':          quantity,
                'sufficient_stock':  sufficient,
                'dest_item_exists':  dest_item_exists,
                'dest_variant_exists': dest_variant_exists,
                'will_be_created':   not dest_variant_exists,
            })

        return Response({
            'success': True,
            'to_branch': to_branch.branch_name,
            'total_items': total_items,
            'low_stock_count': low_stock_count,
            'items': preview,
        })


# ════════════════════════════════════════════════════════════
# MY BRANCH ITEMS (Super Admin ke transferrable items)
# ════════════════════════════════════════════════════════════
class MyBranchItemsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def get(self, request):
        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Your branch not found.'}, status=404)

        items_qs = Items.objects.filter(
            branch=my_branch,
            created_by_superadmin=True
        ).prefetch_related('variants', 'unit', 'c_brand', 'c_category').order_by('itemName')

        data = []
        for item in items_qs:
            variants = []
            for v in item.variants.all():
                parts = [p for p in [v.color, v.size] if p]
                variant_label = " / ".join(parts) if parts else "Default"

                tax_slab = item.taxSlab or "0"
                tax_slab_clean = tax_slab.replace('%', '') if tax_slab else "0"
                try:
                    gst_rate = float(tax_slab_clean)
                except (ValueError, TypeError):
                    gst_rate = 0.0

                variants.append({
                    'variant_id':     v.id,
                    'variant_label':  variant_label,
                    'display':        f"{item.itemName} — {variant_label}",
                    'size':           v.size or "",
                    'color':          v.color or "",
                    'barcode':        v.barcode or "",
                    'current_stock':  (v.current_stock or 0) if (v.current_stock or 0) > 0 else (v.opStock or 0),
                    'purchase_price': v.purchasePrice or 0,
                    'sales_price':    v.salesPrice or 0,
                    'opStock':        v.opStock or 0,
                    'hsnCode':        item.hsnCode or "",
                    'taxSlab':        tax_slab,
                    'gst_rate':       gst_rate,
                })

            data.append({
                'item_id':       item.id,
                'item_name':     item.itemName,
                'item_code':     getattr(item, 'itemCode', None),
                'hsnCode':       item.hsnCode or "",
                'category':      item.c_category.name if item.c_category else None,
                'brand':         item.c_brand.brand_name if item.c_brand else None,
                'unit':          item.unit.symbol if item.unit else "pc",
                'unit_name':     item.unit.name if item.unit else "Piece",
                'total_stock':   sum(v['current_stock'] for v in variants),
                'variant_count': len(variants),
                'variants':      variants,
                'taxSlab':       item.taxSlab or "0",
            })

        return Response({
            'success':     True,
            'branch_id':   my_branch.id,
            'branch_name': my_branch.branch_name,
            'item_count':  len(data),
            'data':        data,
        })


# ════════════════════════════════════════════════════════════
# BRANCH ITEMS WITH VARIANTS (for destination branch info)
# ════════════════════════════════════════════════════════════
class BranchItemsWithVariantsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def get(self, request, branch_id):
        try:
            branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        items_qs = Items.objects.filter(
            branch_id=branch_id,
            created_by_superadmin=True
        ).prefetch_related('variants').order_by('itemName')

        data = []
        for item in items_qs:
            variants = []
            for v in item.variants.all():
                parts = [p for p in [v.color, v.size] if p]
                variant_label = " / ".join(parts) if parts else "Default"

                tax_slab = item.taxSlab or "0"
                tax_slab_clean = tax_slab.replace('%', '') if tax_slab else "0"
                try:
                    gst_rate = float(tax_slab_clean)
                except (ValueError, TypeError):
                    gst_rate = 0.0

                variants.append({
                    'variant_id':     v.id,
                    'variant_label':  variant_label,
                    'display':        f"{item.itemName} — {variant_label}",
                    'size':           v.size or "",
                    'color':          v.color or "",
                    'barcode':        v.barcode or "",
                    'current_stock':  v.current_stock or 0,
                    'purchase_price': v.purchasePrice or 0,
                    'sales_price':    v.salesPrice or 0,
                    'hsnCode':        item.hsnCode or "",
                    'taxSlab':        tax_slab,
                    'gst_rate':       gst_rate,
                    'opStock':        v.opStock or 0,
                })

            if variants:
                data.append({
                    'item_id':       item.id,
                    'item_name':     item.itemName,
                    'item_code':     getattr(item, 'itemCode', None),
                    'category':      item.c_category.name if item.c_category else None,
                    'brand':         item.c_brand.brand_name if item.c_brand else None,
                    'unit':          item.unit.symbol if item.unit else "pc",
                    'unit_name':     item.unit.name if item.unit else "Piece",
                    'total_stock':   sum(v['current_stock'] for v in variants),
                    'variant_count': len(variants),
                    'variants':      variants,
                    'hsnCode':       item.hsnCode or "",
                    'taxSlab':       item.taxSlab or "0",
                })

        return Response({
            'success':     True,
            'branch_name': branch.branch_name,
            'branch_details': {
                'phone':      branch.phone,
                'email':      branch.email,
                'address':    branch.address,
                'city':       branch.city,
                'state':      branch.state,
                'pincode':    branch.pincode,
                'owner_name': branch.owner_name,
            },
            'item_count': len(data),
            'data':       data,
        })


# ════════════════════════════════════════════════════════════
# BRANCH ROLE PERMISSION
# ════════════════════════════════════════════════════════════
class IsBranchRole(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        
        user_role = request.user.role
        
        # Superadmin ko allow
        if user_role == 'superadmin':
            return True
        
        # Sabhi branch-related roles allow karo
        allowed_roles = [
            'branch', 
            'vendor', 
            'branch_both',      # ✅ ADD THIS
            'branch_customer',   # ✅ ADD THIS
            'branch_agent',      # ✅ ADD THIS
            'branch_single'      # ✅ ADD THIS
        ]
        
        # Agar role 'branch' se start hota hai bhi allow karo
        if user_role in allowed_roles or user_role.startswith('branch'):
            return True
        
        return False


# ════════════════════════════════════════════════════════════
# PENDING STOCK TRANSFERS (Branch ke liye)
# ════════════════════════════════════════════════════════════
class PendingStockTransferView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsBranchRole]

    def get(self, request):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        #  Get transfer_type filter from query params
        transfer_type_filter = request.GET.get('transfer_type', '')
        
        #  Filter transfers based on type
        transfers = StockTransfer.objects.filter(
            to_branch=branch,
            status__in=['completed', 'pending'],  # ✅ dono status allow karo
        ).distinct().prefetch_related('items')
        
        # Apply transfer_type filter if specified
        if transfer_type_filter and transfer_type_filter != 'all':
            if transfer_type_filter == 'manual':
                transfers = transfers.filter(transfer_type='manual')
            elif transfer_type_filter == 'order':
                transfers = transfers.filter(transfer_type='order')

        data = []
        for t in transfers:
            all_items = t.items.all()
            pending_count = all_items.filter(is_stock_updated=False).count()
            all_verified = pending_count == 0

            data.append({
                'id': t.id,
                'transfer_no': t.transfer_no,
                'from_branch_name': t.from_branch.branch_name,
                'to_branch_name': t.to_branch.branch_name,
                'transfer_date': str(t.transfer_date),
                'item_count': all_items.count(),
                'status': 'completed',
                'verification_status': 'verified' if all_verified else 'pending',
                'pending_count': pending_count,
                'total_quantity': all_items.aggregate(total=Sum('quantity'))['total'] or 0,
                'transfer_type': t.transfer_type,  
                'source_order_no': t.source_order.order_id if t.source_order else None,  
            })
        
        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response({'success': True, 'data': paginated}) 

# ════════════════════════════════════════════════════════════
# TRANSFER ITEM DETAIL (Branch ke liye)
# ════════════════════════════════════════════════════════════
# pos/views/stock_transfer_views.py - Complete fixed TransferItemDetailView

class TransferItemDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsBranchRole]

    def get(self, request, transfer_id):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        try:
            transfer = StockTransfer.objects.get(id=transfer_id, to_branch=branch)
        except StockTransfer.DoesNotExist:
            return Response({'success': False, 'message': 'Transfer not found'}, status=404)

        items = transfer.items.all()
        data = []
        for item in items:
            from_item_obj = item.from_item
            from_variant_obj = item.from_variant
            
            tax_slab = getattr(from_item_obj, 'taxSlab', "0") if from_item_obj else "0"
            hsn_code = getattr(from_item_obj, 'hsnCode', "") if from_item_obj else ""
            
            # Get all price and variant details
            purchase_price = from_variant_obj.purchasePrice if from_variant_obj else 0
            branch_price = from_variant_obj.branchPrice if from_variant_obj else 0
            sales_price = from_variant_obj.salesPrice if from_variant_obj else 0
            mrp = from_variant_obj.mrp if from_variant_obj else 0
            barcode = from_variant_obj.barcode if from_variant_obj else ""
            size = from_variant_obj.size if from_variant_obj else ""
            color = from_variant_obj.color if from_variant_obj else ""
            variant_info = item.from_variant_info or ""
            
            data.append({
                'id': item.id,
                'from_item_name': item.from_item_name,
                'from_variant_info': variant_info,
                'from_barcode': barcode,
                'from_size': size,
                'from_color': color,
                'quantity': item.quantity,
                'rate': item.rate,
                'is_stock_updated': item.is_stock_updated,
                'status': 'Verified' if item.is_stock_updated else 'Pending',
                'hsnCode': hsn_code,
                'taxSlab': tax_slab,
                'purchase_price': float(purchase_price),
                'branch_price': float(branch_price),
                'sales_price': float(sales_price),
                'mrp': float(mrp),
            })

        return Response({
            'success': True,
            'transfer_no': transfer.transfer_no,
            'transfer_date': transfer.transfer_date,
            'transfer_type': transfer.transfer_type, 
            'source_order_no': transfer.source_order.order_id if hasattr(transfer, 'source_order') and transfer.source_order else None,
            'from_branch': {
                'name': transfer.from_branch.branch_name,
                'phone': transfer.from_branch.phone,
                'email': transfer.from_branch.email,
                'address': transfer.from_branch.address,
                'city': transfer.from_branch.city,
                'state': transfer.from_branch.state,
            },
            'to_branch': {
                'name': transfer.to_branch.branch_name,
                'phone': transfer.to_branch.phone,
                'email': transfer.to_branch.email,
                'address': transfer.to_branch.address,
            },
            'status': transfer.status,
            'note': transfer.note,
            'items': data
        })


# ════════════════════════════════════════════════════════════
# VERIFY SINGLE ITEM
# ════════════════════════════════════════════════════════════

# pos/views/stock_transfer_views.py - Complete fixed VerifyStockTransferItemView

class VerifyStockTransferItemView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsBranchRole]

    def post(self, request, transfer_id, item_id):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        try:
            transfer = StockTransfer.objects.get(id=transfer_id, to_branch=branch)
        except StockTransfer.DoesNotExist:
            return Response({'success': False, 'message': 'Transfer not found'}, status=404)

        if transfer.status == 'cancelled':
            return Response({'success': False, 'message': 'Transfer has been cancelled.'}, status=400)

        try:
            item = StockTransferItem.objects.get(id=item_id, transfer=transfer)
        except StockTransferItem.DoesNotExist:
            return Response({'success': False, 'message': 'Transfer item not found'}, status=404)

        if item.is_stock_updated:
            return Response({'success': False, 'message': 'Stock already verified'}, status=400)

        website_display = request.data.get('website_display', False)

        with transaction.atomic():
            from_variant = item.from_variant
            
            # ✅ STEP 1: Find or create item in destination branch by barcode
            dest_variant = ItemVariants.objects.filter(
                barcode=from_variant.barcode,
                item__branch=branch
            ).select_related('item').first()
            
            if dest_variant:
                dest_item = dest_variant.item
                print(f"✅ Found variant by barcode: {from_variant.barcode}")
            else:
                print(f"🆕 No variant found by barcode - creating new")
                
                dest_item = Items.objects.filter(
                    branch=branch,
                    itemName=from_variant.item.itemName,
                    created_by_superadmin=True
                ).first()
                
                if not dest_item:
                    dest_item = self._create_full_item(from_variant.item, branch)
                
                dest_variant = ItemVariants.objects.create(
                    item=dest_item,
                    purchasePrice=from_variant.purchasePrice,
                    salesPrice=from_variant.salesPrice,
                    mrp=from_variant.mrp,
                    barcode=from_variant.barcode,
                    opStock=0,
                    current_stock=0,
                    size=from_variant.size,
                    color=from_variant.color,
                    srno=from_variant.srno,
                    warrantydate=from_variant.warrantydate,
                )
                print(f"✅ Created new variant with barcode: {from_variant.barcode}")
            
            # ✅ STEP 2: Update website display on item if requested
            if website_display:
                Items.objects.filter(id=dest_item.id).update(
                    website_display=True,
                    website_status='pending'
                )
                dest_item.refresh_from_db()
            
            # ✅ STEP 3: Check source stock - WITH opStock FALLBACK
            available_stock = from_variant.current_stock or 0
            if available_stock <= 0:
                available_stock = from_variant.opStock or 0
            
            if available_stock < item.quantity:
                return Response({
                    'success': False,
                    'message': f'Insufficient stock. Available: {available_stock} (Current: {from_variant.current_stock or 0}, Opening: {from_variant.opStock or 0}), Required: {item.quantity}'
                }, status=400)
            
            # ✅ STEP 4: Deduct from source - First from current_stock, then from opStock
            if from_variant.current_stock >= item.quantity:
                from_variant.current_stock -= item.quantity
            else:
                remaining = item.quantity - (from_variant.current_stock or 0)
                from_variant.current_stock = 0
                from_variant.opStock = (from_variant.opStock or 0) - remaining
            from_variant.save()
            
            # ✅ STEP 5: Add to destination
            old_stock = dest_variant.current_stock or 0
            dest_variant.current_stock = old_stock + item.quantity
            dest_variant.purchasePrice = from_variant.branchPrice
            dest_variant.save(update_fields=['current_stock', 'purchasePrice'])
            
            # ✅ STEP 6: Mark as verified
            # ✅ FIX: to_variant ab yahan save ho raha hai — pehle ye field
            # kabhi save nahi hoti thi, isliye StockReturn create karte
            # waqt purane records me to_variant NULL milta tha aur
            # IntegrityError (branch_variant_id cannot be null) aata tha.
            item.is_stock_updated = True
            item.website_display_on_verify = website_display
            item.to_variant = dest_variant
            item.save(update_fields=['is_stock_updated', 'website_display_on_verify', 'to_variant'])
            
            # ✅ STEP 7: If all items verified, mark transfer as completed
            if not transfer.items.filter(is_stock_updated=False).exists():
                transfer.status = 'completed'
                transfer.save(update_fields=['status'])

        return Response({
            'success': True,
            'message': f'Verified: {item.quantity} x {item.from_item_name}. Stock deducted from {"current stock" if from_variant.current_stock >= item.quantity else "opening stock"}. Website display: {"Enabled (pending approval)" if website_display else "No"}',
            'data': {
                'website_display_updated': website_display,
                'stock_added': item.quantity,
                'new_stock': dest_variant.current_stock,
                'purchase_price': from_variant.purchasePrice,
                'branch_price': from_variant.branchPrice,
                'sales_price': from_variant.salesPrice,
                'mrp': from_variant.mrp,
                'barcode': from_variant.barcode,
            }
        })

    def _create_full_item(self, source_item, branch):
        """Create complete item with all variants from source"""
        dest_item = Items.objects.create(
            entry_type=source_item.entry_type,
            itemName=source_item.itemName,
            branch=branch,
            brand=source_item.brand,
            c_brand=source_item.c_brand,
            category=source_item.category,
            c_category=source_item.c_category,
            subCategory=source_item.subCategory,
            c_subCategory=source_item.c_subCategory,
            subSubCategory=source_item.subSubCategory,
            c_subSubCategory=source_item.c_subSubCategory,
            group=source_item.group,
            unit=source_item.unit,
            created_by_superadmin=True,
            hsnCode=source_item.hsnCode,
            taxSlab=source_item.taxSlab,
            website_display=False,
            website_status='pending',
            short_description=source_item.short_description,
            full_description=source_item.full_description,
            keywords=source_item.keywords,
            main_image=source_item.main_image,
            thumbnail_image=source_item.thumbnail_image,
            gallery=source_item.gallery,
            product_condition=source_item.product_condition,
            return_policy=source_item.return_policy,
            estimated_delivery_time=source_item.estimated_delivery_time,
            free_shipping=source_item.free_shipping,
            warranty_available=source_item.warranty_available,
            warranty_period=source_item.warranty_period,
            warranty_type=source_item.warranty_type,
            warranty_description=source_item.warranty_description,
            description_features=source_item.description_features,
            specifications=source_item.specifications,
        )
        
        for variant in source_item.variants.all():
            branch_price = variant.branchPrice or variant.salesPrice or 0
            
            ItemVariants.objects.create(
                item=dest_item,
                purchasePrice=branch_price,  # ✅ PURCHASE PRICE = BRANCH PRICE
                salesPrice=variant.salesPrice,
                mrp=variant.mrp,
                barcode=variant.barcode,
                opStock=0,
                current_stock=0,
                size=variant.size,
                color=variant.color,
                srno=variant.srno,
                warrantydate=variant.warrantydate,
                variant_image=variant.variant_image,
                branchPrice=branch_price,  # ✅ BRANCH PRICE bhi set karo
            )
        
        return dest_item

# ════════════════════════════════════════════════════════════
# VERIFY ALL ITEMS
# ════════════════════════════════════════════════════════════
# pos/views/stock_transfer_views.py - Complete fixed VerifyAllStockTransferItemsView

class VerifyAllStockTransferItemsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsBranchRole]

    def post(self, request, transfer_id):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        try:
            transfer = StockTransfer.objects.get(id=transfer_id, to_branch=branch)
        except StockTransfer.DoesNotExist:
            return Response({'success': False, 'message': 'Transfer not found'}, status=404)

        if transfer.status == 'cancelled':
            return Response({'success': False, 'message': 'Transfer has been cancelled.'}, status=400)

        pending_items = transfer.items.filter(is_stock_updated=False)
        
        if not pending_items.exists():
            return Response({'success': False, 'message': 'No pending items'}, status=400)

        website_display = request.data.get('website_display', False)

        verified_count = 0
        errors = []

        with transaction.atomic():
            for item in pending_items:
                from_variant = item.from_variant
                
                # ✅ Check available stock with opStock fallback
                available_stock = from_variant.current_stock or 0
                if available_stock <= 0:
                    available_stock = from_variant.opStock or 0
                
                if available_stock < item.quantity:
                    errors.append(f"{item.from_item_name}: Insufficient stock (Available: {available_stock}, Required: {item.quantity})")
                    continue
                
                dest_variant = ItemVariants.objects.filter(
                    barcode=from_variant.barcode,
                    item__branch=branch
                ).select_related('item').first()
                
                if not dest_variant:
                    dest_item = Items.objects.filter(
                        branch=branch,
                        itemName=from_variant.item.itemName,
                        created_by_superadmin=True
                    ).first()
                    
                    if not dest_item:
                        dest_item = Items.objects.create(
                            entry_type=from_variant.item.entry_type,
                            itemName=from_variant.item.itemName,
                            branch=branch,
                            brand=from_variant.item.brand,
                            c_brand=from_variant.item.c_brand,
                            category=from_variant.item.category,
                            c_category=from_variant.item.c_category,
                            subCategory=from_variant.item.subCategory,
                            c_subCategory=from_variant.item.c_subCategory,
                            subSubCategory=from_variant.item.subSubCategory,
                            c_subSubCategory=from_variant.item.c_subSubCategory,
                            group=from_variant.item.group,
                            unit=from_variant.item.unit,
                            created_by_superadmin=True,
                            hsnCode=from_variant.item.hsnCode,
                            taxSlab=from_variant.item.taxSlab,
                        )
                    
                        branch_price = from_variant.branchPrice or from_variant.salesPrice or 0

                        dest_variant = ItemVariants.objects.create(
                            item=dest_item,
                            purchasePrice=branch_price,  # ✅ PURCHASE PRICE = BRANCH PRICE
                            salesPrice=from_variant.salesPrice,
                            mrp=from_variant.mrp,
                            barcode=from_variant.barcode,
                            opStock=0,
                            current_stock=0,
                            size=from_variant.size,
                            color=from_variant.color,
                            srno=from_variant.srno,
                            branchPrice=branch_price,  # ✅ BRANCH PRICE bhi set karo
                        )
                
                if website_display:
                    Items.objects.filter(id=dest_variant.item.id).update(
                        website_display=True,
                        website_status='pending'
                    )
                
                # ✅ Deduct from source - First from current_stock, then from opStock
                if from_variant.current_stock >= item.quantity:
                    from_variant.current_stock -= item.quantity
                else:
                    remaining = item.quantity - (from_variant.current_stock or 0)
                    from_variant.current_stock = 0
                    from_variant.opStock = (from_variant.opStock or 0) - remaining
                from_variant.save()
                
                dest_variant.current_stock = (dest_variant.current_stock or 0) + item.quantity
                dest_variant.purchasePrice = from_variant.branchPrice
                dest_variant.save(update_fields=['current_stock', 'purchasePrice'])
                
                # ✅ FIX: to_variant ab yahan bhi save ho raha hai — same bug
                # jo VerifyStockTransferItemView me tha, "Verify All" button
                # se verify hone wale items me bhi to_variant NULL reh jaata
                # tha. Isse StockReturn create karte waqt IntegrityError
                # (branch_variant_id cannot be null) aata tha.
                item.is_stock_updated = True
                item.website_display_on_verify = website_display
                item.to_variant = dest_variant
                item.save(update_fields=['is_stock_updated', 'website_display_on_verify', 'to_variant'])
                verified_count += 1

        if not transfer.items.filter(is_stock_updated=False).exists():
            transfer.status = 'completed'
            transfer.save(update_fields=['status'])

        if errors:
            return Response({
                'success': False,
                'message': f'Verified {verified_count} items. Errors: {", ".join(errors)}'
            }, status=400)

        return Response({
            'success': True,
            'message': f'{verified_count} item(s) verified successfully. Website display: {"Enabled" if website_display else "Not changed"}'
        })
        
# ════════════════════════════════════════════════════════════
# MY BRANCH VARIANTS (Branch ke liye)
# ════════════════════════════════════════════════════════════
class MyBranchVariantsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsBranchRole]
 
    def get(self, request):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)
 
        variants = ItemVariants.objects.filter(
            item__branch=branch
        ).select_related('item').order_by('item__itemName')
 
        data = []
        for v in variants:
            parts = [p for p in [v.color, v.size] if p]
            variant_label = " / ".join(parts) if parts else "Default"
            data.append({
                'variant_id':     v.id,
                'item_id':        v.item.id,
                'item_name':      v.item.itemName,
                'variant_label':  variant_label,
                'display':        f"{v.item.itemName} — {variant_label}",
                'size':           v.size,
                'color':          v.color,
                'barcode':        v.barcode,
                'current_stock':  v.current_stock or 0,
                'purchase_price': v.purchasePrice or 0,
                'sales_price':    v.salesPrice or 0,
            })
 
        return Response({
            'success':       True,
            'branch_name':   branch.branch_name,
            'variant_count': len(data),
            'data':          data,
        })
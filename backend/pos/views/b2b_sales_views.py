# pos/views/b2b_sales_views.py
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import transaction
from django.db.models import Sum, Q
from rest_framework import status

from pos.models.account import Account
from pos.models.b2b_sales import B2BSale, B2BSaleItem
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants
from pos.serializers.b2b_sales_serializers import (
    B2BSaleCreateSerializer,
    B2BSaleDetailSerializer,
    B2BSaleListSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination
from pos.models.settings import setting as SettingModel
from pos.utils.gst_calc import calculate_gst_split
from pos.utils.variant_mapping import get_or_create_dest_variant

# ✅ Reuse existing superadmin permission (no duplication)
from pos.views.stock_transfer_views import IsSuperAdminRole


class IsFranchiseBranchRole(IsAuthenticated):
    """Sirf franchise-ownership wali branch (ya superadmin, admin-view ke liye) allow"""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user_role = request.user.role
        if user_role == 'superadmin':
            return True
        allowed_roles = ['branch', 'vendor', 'branch_both', 'branch_customer', 'branch_agent', 'branch_single']
        if not (user_role in allowed_roles or user_role.startswith('branch')):
            return False
        branch = Branch.objects.filter(user=request.user).first()
        return bool(branch and branch.ownership_type == 'franchise')


# ════════════════════════════════════════════════════════════
# B2B SALE VIEWSET (Superadmin side)
# ════════════════════════════════════════════════════════════
class B2BSaleViewSet(ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_queryset(self):
        qs = B2BSale.objects.prefetch_related('items').all()
        if to_branch := self.request.query_params.get('to_branch'):
            qs = qs.filter(to_branch_id=to_branch)
        if st := self.request.query_params.get('status'):
            qs = qs.filter(status=st)
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return B2BSaleCreateSerializer
        if self.action == 'list':
            return B2BSaleListSerializer
        return B2BSaleDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = B2BSaleCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            sale = serializer.save()
            detail = B2BSaleDetailSerializer(sale)
            return Response({
                'success': True,
                'message': f'B2B Sale {sale.sale_no} created. Stock deducted from your branch.',
                'data': detail.data
            }, status=201)
        return Response({'success': False, 'errors': serializer.errors}, status=400)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serialized = B2BSaleListSerializer(page, many=True).data
            response = paginator.get_paginated_response(serialized)
            response.data['success'] = True
            return response
        return Response({'success': True, 'data': B2BSaleListSerializer(qs, many=True).data, 'count': qs.count()})

    def retrieve(self, request, *args, **kwargs):
        return Response({'success': True, 'data': B2BSaleDetailSerializer(self.get_object()).data})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        sale = self.get_object()
        if sale.status == 'completed':
            return Response({'success': False, 'message': 'Cannot cancel a fully verified sale.'}, status=400)
        if sale.status == 'cancelled':
            return Response({'success': False, 'message': 'Already cancelled.'}, status=400)

        with transaction.atomic():
            #  Sirf jo items abhi tak verify NAHI hue, unka stock source branch me wapas
            for item in sale.items.filter(is_stock_updated=False):
                variant = item.from_variant
                variant.current_stock = (variant.current_stock or 0) + item.quantity
                variant.save(update_fields=['current_stock'])
            sale.status = 'cancelled'
            sale.save(update_fields=['status'])

        return Response({'success': True, 'message': 'B2B Sale cancelled. Unverified items ka stock revert ho gaya.'})


# ════════════════════════════════════════════════════════════
# FRANCHISE BRANCHES LIST (destination dropdown + details ke liye)
# ════════════════════════════════════════════════════════════
class FranchiseBranchListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def get(self, request):
        branches = Branch.objects.filter(
            ownership_type='franchise', status='active'
        ).order_by('branch_name')
        data = [{
            'id': b.id,
            'branch_name': b.branch_name,
            'city': b.city,
            'state': b.state,
            'phone': b.phone,          # ✅ NEW
            'email': b.email,          # ✅ NEW
            'address': b.address,      # ✅ NEW
            'pincode': b.pincode,      # ✅ NEW
            'owner_name': b.owner_name,  # ✅ NEW
        } for b in branches]
        return Response({'success': True, 'data': data})


# ════════════════════════════════════════════════════════════
# GST PREVIEW (item entry row ke live tax calc ke liye)
# ════════════════════════════════════════════════════════════
class B2BSaleItemTaxAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from_variant_id = request.data.get("from_variant_id")
        to_branch_id = request.data.get("to_branch_id")
        quantity = request.data.get("quantity", 1)

        if not from_variant_id or not to_branch_id:
            return Response({"error": "from_variant_id and to_branch_id are required"}, status=400)

        try:
            from_variant = ItemVariants.objects.select_related("item", "item__branch").get(id=from_variant_id)
        except ItemVariants.DoesNotExist:
            return Response({"error": "Variant not found"}, status=404)

        try:
            to_branch = Branch.objects.get(id=to_branch_id)
        except Branch.DoesNotExist:
            return Response({"error": "Destination branch not found"}, status=404)

        if to_branch.ownership_type != 'franchise':
            return Response({"error": "Selected branch is not a franchise branch"}, status=400)

        from_branch = from_variant.item.branch
        rate = from_variant.branchPrice or 0
        tax_percent = from_variant.item.taxSlab or "0"

        settings_obj = SettingModel.objects.filter(branch=from_branch).first()
        gst_toggle = getattr(settings_obj, "stock_transfer_gst_toggle", False)
        same_state = (from_branch.state or "") == (to_branch.state or "")

        result = calculate_gst_split(rate, quantity, tax_percent, gst_toggle, same_state)

        available_stock = from_variant.current_stock or 0
        if available_stock <= 0:
            available_stock = from_variant.opStock or 0

        return Response({
            "from_variant_id": from_variant.id,
            "item_name": from_variant.item.itemName,
            "rate": float(rate),
            "quantity": quantity,
            "tax_percent": float(str(tax_percent).replace("%", "") or 0),
            "gst_toggle": gst_toggle,
            "available_stock": available_stock,
            "basic_amount": float(result["basic_amount"]),
            "tax_amount": float(result["tax_amount"]),
            "cgst": float(result["cgst"]),
            "sgst": float(result["sgst"]),
            "igst": float(result["igst"]),
            "net_amount": float(result["net_amount"]),
        }, status=status.HTTP_200_OK)


# ════════════════════════════════════════════════════════════
# PENDING B2B SALES (Franchise branch ke liye)
# ════════════════════════════════════════════════════════════
class PendingB2BSaleView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsFranchiseBranchRole]

    def get(self, request):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        sales = B2BSale.objects.filter(
            to_branch=branch,
            status__in=['pending', 'completed'],
        ).distinct().prefetch_related('items')

        data = []
        for s in sales:
            all_items = s.items.all()
            pending_count = all_items.filter(is_stock_updated=False).count()
            all_verified = pending_count == 0
            data.append({
                'id': s.id,
                'sale_no': s.sale_no,
                'from_branch_name': s.from_branch.branch_name,
                'to_branch_name': s.to_branch.branch_name,
                'sale_date': str(s.sale_date),
                'item_count': all_items.count(),
                'status': s.status,
                'verification_status': 'verified' if all_verified else 'pending',
                'pending_count': pending_count,
                'total_quantity': all_items.aggregate(total=Sum('quantity'))['total'] or 0,
            })

        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response({'success': True, 'data': paginated})


# ════════════════════════════════════════════════════════════
# SALE ITEM DETAIL (Franchise branch verify page ke liye)
# ════════════════════════════════════════════════════════════
class B2BSaleItemDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsFranchiseBranchRole]

    def get(self, request, sale_id):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        try:
            sale = B2BSale.objects.get(id=sale_id, to_branch=branch)
        except B2BSale.DoesNotExist:
            return Response({'success': False, 'message': 'Sale not found'}, status=404)

        data = []
        for item in sale.items.all():
            fv = item.from_variant
            data.append({
                'id': item.id,
                'from_item_name': item.from_item_name,
                'from_variant_info': item.from_variant_info or "",
                'from_barcode': fv.barcode if fv else item.from_barcode,
                'from_size': fv.size if fv else "",
                'from_color': fv.color if fv else "",
                'quantity': item.quantity,
                'rate': item.rate,
                'is_stock_updated': item.is_stock_updated,
                'status': 'Verified' if item.is_stock_updated else 'Pending',
                'hsnCode': getattr(item.from_item, 'hsnCode', "") if item.from_item else "",
                'taxSlab': item.tax_percent or "0",
                'purchase_price': float(fv.purchasePrice) if fv else 0,
                'branch_price': float(fv.branchPrice) if fv else 0,
                'sales_price': float(fv.salesPrice) if fv else 0,
                'mrp': float(fv.mrp) if fv else 0,
                'tax_percent': item.tax_percent or "0",
                'basic_amount': float(item.basic_amount or 0),
                'tax_amount': float(item.tax_amount or 0),
                'cgst': float(item.cgst or 0),
                'sgst': float(item.sgst or 0),
                'igst': float(item.igst or 0),
                'net_amount': float(item.net_amount or 0),
            })

        return Response({
            'success': True,
            'sale_no': sale.sale_no,
            'sale_date': sale.sale_date,
            'from_branch': {
                'name': sale.from_branch.branch_name,
                'phone': sale.from_branch.phone,
                'email': sale.from_branch.email,
                'address': sale.from_branch.address,
                'city': sale.from_branch.city,
                'state': sale.from_branch.state,
            },
            'to_branch': {
                'name': sale.to_branch.branch_name,
                'phone': sale.to_branch.phone,
                'email': sale.to_branch.email,
                'address': sale.to_branch.address,
            },
            'status': sale.status,
            'note': sale.note,
            'items': data,
        })


# ════════════════════════════════════════════════════════════
# VERIFY SINGLE ITEM — sirf ADD hoga destination me (deduct pehle ho chuka)
# ════════════════════════════════════════════════════════════
class VerifyB2BSaleItemView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsFranchiseBranchRole]

    def post(self, request, sale_id, item_id):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        if not Account.objects.filter(branch=branch, group='Sundry Creditor(Main)').exists():
            return Response({
                'success': False,
                'error_code': 'NO_SUNDRY_CREDITOR_ACCOUNT',
                'message': 'Please create a Sundry Creditor(Main) account before verifying stock.'
            }, status=400)

        try:
            sale = B2BSale.objects.get(id=sale_id, to_branch=branch)
        except B2BSale.DoesNotExist:
            return Response({'success': False, 'message': 'Sale not found'}, status=404)

        if sale.status == 'cancelled':
            return Response({'success': False, 'message': 'Sale has been cancelled.'}, status=400)

        try:
            item = B2BSaleItem.objects.get(id=item_id, sale=sale)
        except B2BSaleItem.DoesNotExist:
            return Response({'success': False, 'message': 'Sale item not found'}, status=404)

        if item.is_stock_updated:
            return Response({'success': False, 'message': 'Stock already verified'}, status=400)

        website_display = request.data.get('website_display', False)
        with transaction.atomic():
            from_variant = item.from_variant

            # ✅ FIXED — barcode filter ki jagah FK-mapping based lookup
            # (Stock Transfer verify jaisa hi pattern; VariantBranchMapping
            # already sale-creation time pe ban chuki hoti hai)
            dest_variant, _created = get_or_create_dest_variant(from_variant, branch, sync_fields=True)
            dest_item = dest_variant.item

            if website_display:
                Items.objects.filter(id=dest_item.id).update(website_display=True, website_status='pending')

            # ✅ SIRF ADD — source ka deduction creation time pe ho chuka hai
            dest_variant.current_stock = (dest_variant.current_stock or 0) + item.quantity
            dest_variant.purchasePrice = from_variant.branchPrice
            dest_variant.save(update_fields=['current_stock', 'purchasePrice'])

            item.is_stock_updated = True
            item.website_display_on_verify = website_display
            item.to_variant = dest_variant
            item.save(update_fields=['is_stock_updated', 'website_display_on_verify', 'to_variant'])

            if not sale.items.filter(is_stock_updated=False).exists():
                sale.status = 'completed'
                sale.save(update_fields=['status'])

                from pos.utils.b2b_purchase_entry import create_purchase_entry_from_b2b_sale
                create_purchase_entry_from_b2b_sale(sale)
        return Response({
            'success': True,
            'message': f'Verified: {item.quantity} x {item.from_item_name}. Stock added to your branch.',
            'data': {'new_stock': dest_variant.current_stock, 'barcode': from_variant.barcode}
        })

    def _create_full_item(self, source_item, branch):
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
                purchasePrice=branch_price,
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
                branchPrice=branch_price,
            )
        return dest_item


# ════════════════════════════════════════════════════════════
# VERIFY ALL ITEMS
# ════════════════════════════════════════════════════════════
class VerifyAllB2BSaleItemsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsFranchiseBranchRole]

    def post(self, request, sale_id):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        if not Account.objects.filter(branch=branch, group='Sundry Creditor(Main)').exists():
            return Response({
                'success': False,
                'error_code': 'NO_SUNDRY_CREDITOR_ACCOUNT',
                'message': 'Please create a Sundry Creditor(Main) account before verifying stock.'
            }, status=400)

        try:
            sale = B2BSale.objects.get(id=sale_id, to_branch=branch)
        except B2BSale.DoesNotExist:
            return Response({'success': False, 'message': 'Sale not found'}, status=404)

        if sale.status == 'cancelled':
            return Response({'success': False, 'message': 'Sale has been cancelled.'}, status=400)

        pending_items = sale.items.filter(is_stock_updated=False)
        if not pending_items.exists():
            return Response({'success': False, 'message': 'No pending items'}, status=400)

        website_display = request.data.get('website_display', False)
        verified_count = 0

        # ✅ NEW — isi request ke andar same item dubara process ho toh dobara na bane
        with transaction.atomic():
            for item in pending_items:
                from_variant = item.from_variant

                # ✅ FIXED — barcode/manual-create logic hataya, FK-mapping use karo
                dest_variant, _created = get_or_create_dest_variant(from_variant, branch, sync_fields=True)

                if website_display:
                    Items.objects.filter(id=dest_variant.item.id).update(
                        website_display=True, website_status='pending'
                    )

                dest_variant.current_stock = (dest_variant.current_stock or 0) + item.quantity
                dest_variant.purchasePrice = from_variant.branchPrice
                dest_variant.save(update_fields=['current_stock', 'purchasePrice'])

                item.is_stock_updated = True
                item.website_display_on_verify = website_display
                item.to_variant = dest_variant
                item.save(update_fields=['is_stock_updated', 'website_display_on_verify', 'to_variant'])
                verified_count += 1

            if not sale.items.filter(is_stock_updated=False).exists():
                sale.status = 'completed'
                sale.save(update_fields=['status'])

                from pos.utils.b2b_purchase_entry import create_purchase_entry_from_b2b_sale
                create_purchase_entry_from_b2b_sale(sale)
                
        return Response({'success': True, 'message': f'{verified_count} item(s) verified successfully.'})
    
    
    
# ════════════════════════════════════════════════════════════
# NEXT SALE NO PREVIEW (form open hote hi dikhane ke liye)
# ════════════════════════════════════════════════════════════
class B2BSaleNextNumberView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def get(self, request):
        # ✅ Sirf preview — koi record save nahi hota
        next_no = B2BSale.get_next_sale_no()
        return Response({'success': True, 'sale_no': next_no})    
    
    
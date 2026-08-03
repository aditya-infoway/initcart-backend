# pos/views/b2b_transfer_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from django.db import transaction
from django.db.models import Q

from pos.models.b2b_transfer import B2BOrder, B2BOrderItem, B2BStockTransfer, B2BStockTransferItem
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants
from pos.models.account import Account
from pos.serializers.b2b_transfer_serializers import (
    B2BOrderCreateSerializer, B2BOrderListSerializer, B2BOrderDetailSerializer,
    B2BProcessOrderSerializer, B2BTransferListSerializer, B2BTransferDetailSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination
from pos.models.b2b_transfer import B2BOrderSequence, get_financial_year
from pos.utils.variant_mapping import get_or_create_dest_variant

BRANCH_ROLES = ['branch', 'vendor', 'branch_customer', 'branch_agent', 'branch_both', 'branch_single']


def is_branch_user(user):
    return user.role in BRANCH_ROLES or user.role.startswith('branch')


# ════════════════════════════════════════════════════════════
# Branch selector + eligible items (for "New Order" tab)
# ════════════════════════════════════════════════════════════
class B2BSourceBranchListView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        if not is_branch_user(user):
            return Response({"success": False, "message": "Branch users only."}, status=403)
        my_branch = getattr(user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "No branch assigned."}, status=400)

        branches = Branch.objects.exclude(id=my_branch.id).exclude(user__role='superadmin').order_by('branch_name')
        data = [{
            "branch_id": b.id, "branch_name": b.branch_name, "city": b.city or "",
            "state": b.state or "", "credit_term": b.credit_term or "",
            "owner_name": getattr(b, "owner_name", "") or "",
            "phone": getattr(b, "phone", "") or "",
            "email": getattr(b, "email", "") or "",
            "address": getattr(b, "address", "") or "",
        } for b in branches]
        return Response({"success": True, "data": data})


class B2BSourceBranchItemsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, branch_id):
        user = request.user
        if not is_branch_user(user):
            return Response({"success": False, "message": "Branch users only."}, status=403)
        try:
            source_branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            return Response({"success": False, "message": "Branch not found."}, status=404)

        my_branch = getattr(user, 'branch', None)
        if my_branch and source_branch.id == my_branch.id:
            return Response({"success": False, "message": "Cannot order from your own branch."}, status=400)

        search = request.GET.get('search', '').strip()
        qs = Items.objects.filter(branch=source_branch, created_by_superadmin=True).select_related(
            'c_brand', 'c_category', 'unit'
        ).prefetch_related('variants').order_by('itemName')

        if search:
            qs = qs.filter(Q(itemName__icontains=search) | Q(hsnCode__icontains=search) | Q(c_brand__brand_name__icontains=search))

        paginator = StandardResultsSetPagination()
        paginated_items = paginator.paginate_queryset(qs, request)

        items_list = []
        for item in paginated_items:
            item_data = {
                "item_id": item.id, "item_name": item.itemName,
                "category": item.c_category.name if item.c_category else item.category,
                "hsnCode": item.hsnCode, "taxSlab": item.taxSlab,
                "main_image": request.build_absolute_uri(item.main_image.url) if item.main_image else None,
                "variants": [],
            }
            for v in item.variants.all():
                parts = [p for p in [v.color, v.size] if p]
                variant_label = " / ".join(parts) if parts else "Default"
                branch_price = v.branchPrice or v.salesPrice or 0
                # ✅ Stock is intentionally NOT exposed as a decision factor to the
                # requesting branch — they request what they need; the source branch
                # caps it to real availability at Verify time.
                item_data["variants"].append({
                    "variant_id": v.id, "variant_label": variant_label, "size": v.size, "color": v.color,
                    "barcode": v.barcode, "branch_price": float(branch_price),
                    "sales_price": float(v.salesPrice or 0), "mrp": float(v.mrp or 0),
                    "hsnCode": item.hsnCode, "taxSlab": item.taxSlab,
                })
            if item_data["variants"]:
                item_data["variant_count"] = len(item_data['variants'])
                items_list.append(item_data)

        return paginator.get_paginated_response({
            "success": True, "source_branch_name": source_branch.branch_name,
            "credit_term": source_branch.credit_term or "", "data": items_list,
        })


# ════════════════════════════════════════════════════════════
# Orders: create + my-orders (requesting branch B)
# ════════════════════════════════════════════════════════════
class B2BOrderListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        my_branch = getattr(user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "No branch assigned."}, status=400)
        search = request.GET.get('search', '').strip()
        qs = B2BOrder.objects.filter(requesting_branch=my_branch).prefetch_related('items').order_by('-created_at')
        if search:
            qs = qs.filter(Q(order_id__icontains=search) | Q(note__icontains=search))
        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response({"success": True, "orders": B2BOrderListSerializer(paginated, many=True).data})

    def post(self, request):
        if not is_branch_user(request.user):
            return Response({"success": False, "message": "Branch users only."}, status=403)
        serializer = B2BOrderCreateSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            order = serializer.save()
            return Response({"success": True, "message": f"Order {order.order_id} placed!", "order_id": order.order_id, "id": order.id}, status=201)
        return Response(serializer.errors, status=400)


class B2BOrderDetailView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, order_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            order = B2BOrder.objects.prefetch_related('items').get(
                Q(requesting_branch=my_branch) | Q(source_branch=my_branch), id=order_id,
            )
        except B2BOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)
        return Response({"success": True, "order": B2BOrderDetailSerializer(order).data})


# ════════════════════════════════════════════════════════════
# Incoming Orders (source branch A processes them)
# ════════════════════════════════════════════════════════════
class B2BIncomingOrderListView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        my_branch = getattr(request.user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "No branch assigned."}, status=400)
        qs = B2BOrder.objects.filter(source_branch=my_branch).prefetch_related('items').order_by('-created_at')
        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response({"success": True, "orders": B2BOrderListSerializer(paginated, many=True).data})


class B2BProcessOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, order_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            order = B2BOrder.objects.prefetch_related('items').get(id=order_id)
        except B2BOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if not my_branch or my_branch.id != order.source_branch_id:
            return Response({"success": False, "message": "Only the source branch can process this order."}, status=403)
        if order.status != 'pending':
            return Response({"success": False, "message": f"Order already {order.status}."}, status=400)

        serializer = B2BProcessOrderSerializer(order, data=request.data, context={"request": request})
        if serializer.is_valid():
            updated = serializer.update(order, serializer.validated_data)
            return Response({
                "success": True, "message": f"Order {order.order_id} processed.",
                "order_status": updated.status,
                "linked_transfer": updated.linked_transfer.transfer_no if updated.linked_transfer else None,
            })
        return Response(serializer.errors, status=400)


class B2BCancelOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, order_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            order = B2BOrder.objects.get(id=order_id)
        except B2BOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)
        if not my_branch or my_branch.id not in [order.requesting_branch_id, order.source_branch_id]:
            return Response({"success": False, "message": "Not allowed."}, status=403)
        if order.status != 'pending':
            return Response({"success": False, "message": "Already processed or cancelled."}, status=400)
        order.status = 'cancelled'
        order.save()
        return Response({"success": True, "message": f"Order {order.order_id} cancelled."})


# ════════════════════════════════════════════════════════════
# Transfers — Incoming (B receives) / Outgoing (A packages)
# ════════════════════════════════════════════════════════════
class B2BIncomingTransferListView(APIView):
    """B side — 'Receive Stock' tab. Transfers where I'm to_branch."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        my_branch = getattr(request.user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "No branch assigned."}, status=400)
        qs = B2BStockTransfer.objects.filter(to_branch=my_branch).prefetch_related('items').order_by('-created_at')
        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response({"success": True, "data": B2BTransferListSerializer(paginated, many=True).data})


class B2BOutgoingTransferListView(APIView):
    """A side — 'Packaging' mode. Transfers where I'm from_branch."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        my_branch = getattr(request.user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "No branch assigned."}, status=400)
        qs = B2BStockTransfer.objects.filter(from_branch=my_branch).prefetch_related('items').order_by('-created_at')
        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response({"success": True, "data": B2BTransferListSerializer(paginated, many=True).data})


class B2BTransferDetailView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, transfer_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            transfer = B2BStockTransfer.objects.prefetch_related('items').get(
                Q(from_branch=my_branch) | Q(to_branch=my_branch), id=transfer_id,
            )
        except B2BStockTransfer.DoesNotExist:
            return Response({"success": False, "message": "Transfer not found"}, status=404)
        return Response({"success": True, "data": B2BTransferDetailSerializer(transfer).data})


class B2BConfirmTransferView(APIView):
    """B confirms — status pending -> confirmed. No stock movement."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, transfer_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            transfer = B2BStockTransfer.objects.get(id=transfer_id, to_branch=my_branch)
        except B2BStockTransfer.DoesNotExist:
            return Response({"success": False, "message": "Transfer not found"}, status=404)
        if transfer.status != 'pending':
            return Response({"success": False, "message": f"Cannot confirm. Current status: {transfer.status}"}, status=400)
        transfer.status = 'confirmed'
        transfer.confirmed_by = request.user
        transfer.save(update_fields=['status', 'confirmed_by', 'updated_at'])
        return Response({"success": True, "message": f"Transfer {transfer.transfer_no} confirmed."})

class B2BPackagingStartView(APIView):
    """A marks packaging started — status confirmed -> packaging_start. NO stock movement yet."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, transfer_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            transfer = B2BStockTransfer.objects.get(id=transfer_id, from_branch=my_branch)
        except B2BStockTransfer.DoesNotExist:
            return Response({"success": False, "message": "Transfer not found"}, status=404)
        if transfer.status != 'confirmed':
            return Response({"success": False, "message": f"Receiving branch must confirm first. Current status: {transfer.status}"}, status=400)
        transfer.status = 'packaging_start'
        transfer.packaging_started_by = request.user
        transfer.save(update_fields=['status', 'packaging_started_by', 'updated_at'])
        return Response({"success": True, "message": f"Transfer {transfer.transfer_no} packaging started."})
    
class B2BReceiveTransferItemView(APIView):
    """B receives ONE item at a time — that item's stock is added immediately.
    Transfer moves to 'partially_received' while items remain, 'received' once all are done."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, transfer_id, item_id):
        my_branch = getattr(request.user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "Branch not found"}, status=404)

        try:
            transfer = B2BStockTransfer.objects.get(id=transfer_id, to_branch=my_branch)
        except B2BStockTransfer.DoesNotExist:
            return Response({"success": False, "message": "Transfer not found"}, status=404)

        if transfer.status not in ['packaging_ready', 'partially_received']:
            return Response({"success": False, "message": f"Not ready to receive. Current status: {transfer.status}"}, status=400)

        try:
            item = transfer.items.get(id=item_id)
        except B2BStockTransferItem.DoesNotExist:
            return Response({"success": False, "message": "Item not found"}, status=404)

        if item.is_received:
            return Response({"success": False, "message": "This item is already received."}, status=400)

        with transaction.atomic():
            dest_variant = item.to_variant
            if not dest_variant:
                # ✅ FIXED — barcode filter ki jagah FK-mapping based resolve
                dest_variant, _created = get_or_create_dest_variant(item.from_variant, my_branch, sync_fields=True)
                item.to_variant = dest_variant

            dest_variant.current_stock = (dest_variant.current_stock or 0) + item.quantity
            dest_variant.purchasePrice = item.from_variant.branchPrice
            dest_variant.save(update_fields=['current_stock', 'purchasePrice'])

            item.is_received = True
            item.save(update_fields=['is_received', 'to_variant'])

            remaining = transfer.items.filter(is_received=False).count()
            if remaining == 0:
                transfer.status = 'received'
                transfer.received_by = request.user
                transfer.save(update_fields=['status', 'received_by', 'updated_at'])
            else:
                transfer.status = 'partially_received'
                transfer.save(update_fields=['status', 'updated_at'])

        return Response({
            "success": True,
            "message": f"{item.from_item_name} received. Stock added.",
            "transfer_status": transfer.status,
            "remaining_items": remaining,
        })    
class B2BPackagingReadyView(APIView):
    ...
    def post(self, request, transfer_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            transfer = B2BStockTransfer.objects.get(id=transfer_id, from_branch=my_branch)
        except B2BStockTransfer.DoesNotExist:
            return Response({"success": False, "message": "Transfer not found"}, status=404)
        if transfer.status != 'packaging_start':
            return Response({"success": False, "message": f"Start packaging first. Current status: {transfer.status}"}, status=400)

        # Optional — agar Sundry Debitor account exist karta hai toh entry post hogi
        debitor_account = Account.objects.filter(branch=my_branch, group='Sundry Debitor(Main)').first()

        with transaction.atomic():
            for item in transfer.items.all():
                variant = item.from_variant
                if variant.current_stock >= item.quantity:
                    variant.current_stock -= item.quantity
                else:
                    remaining = item.quantity - (variant.current_stock or 0)
                    variant.current_stock = 0
                    variant.opStock = (variant.opStock or 0) - remaining
                variant.save(update_fields=['current_stock', 'opStock'])
                item.is_packaged = True
                item.save(update_fields=['is_packaged'])

            transfer.status = 'packaging_ready'
            transfer.packaged_by = request.user
            transfer.save(update_fields=['status', 'packaged_by', 'updated_at'])

            if debitor_account:
                # TODO: ledger entry wiring — same as receive side
                pass

        return Response({"success": True, "message": f"Transfer {transfer.transfer_no} packaging ready. Stock deducted."})

class B2BReceiveTransferView(APIView):
    """B receives ALL remaining items at once — packaging_ready/partially_received -> received."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, transfer_id):
        my_branch = getattr(request.user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "Branch not found"}, status=404)

        if not Account.objects.filter(branch=my_branch, group='Sundry Creditor(Main)').exists():
            return Response({
                "success": False, "error_code": "NO_SUNDRY_CREDITOR_ACCOUNT",
                "message": "Please create a Sundry Creditor(Main) account before receiving stock.",
            }, status=400)

        try:
            transfer = B2BStockTransfer.objects.get(id=transfer_id, to_branch=my_branch)
        except B2BStockTransfer.DoesNotExist:
            return Response({"success": False, "message": "Transfer not found"}, status=404)
        if transfer.status not in ['packaging_ready', 'partially_received']:
            return Response({"success": False, "message": f"Not ready to receive. Current status: {transfer.status}"}, status=400)

        with transaction.atomic():
            for item in transfer.items.filter(is_received=False):
                dest_variant = item.to_variant
                if not dest_variant:
                    # ✅ FIXED
                    dest_variant, _created = get_or_create_dest_variant(item.from_variant, my_branch, sync_fields=True)
                    item.to_variant = dest_variant

                dest_variant.current_stock = (dest_variant.current_stock or 0) + item.quantity
                dest_variant.purchasePrice = item.from_variant.branchPrice
                dest_variant.save(update_fields=['current_stock', 'purchasePrice'])

                item.is_received = True
                item.save(update_fields=['is_received', 'to_variant'])

            transfer.status = 'received'
            transfer.received_by = request.user
            transfer.save(update_fields=['status', 'received_by', 'updated_at'])

        return Response({"success": True, "message": f"Transfer {transfer.transfer_no} received. Stock added."})


class B2BCancelTransferView(APIView):
    """Cancel before stock actually moves (pending, confirmed, or packaging_start only)."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, transfer_id):
        my_branch = getattr(request.user, 'branch', None)
        try:
            transfer = B2BStockTransfer.objects.get(Q(from_branch=my_branch) | Q(to_branch=my_branch), id=transfer_id)
        except B2BStockTransfer.DoesNotExist:
            return Response({"success": False, "message": "Transfer not found"}, status=404)
        if transfer.status not in ['pending', 'confirmed', 'packaging_start']:
            return Response({"success": False, "message": f"Cannot cancel. Status: {transfer.status}"}, status=400)
        transfer.status = 'cancelled'
        transfer.save(update_fields=['status', 'updated_at'])
        return Response({"success": True, "message": f"Transfer {transfer.transfer_no} cancelled."})
    
    
class B2BNextOrderNumberPreviewView(APIView):
    """
    GET /api/pos/b2b-orders/next-number-preview/
    Sirf ek ESTIMATE deta hai (increment nahi karta) — jaisa Stock Return
    ke NextReturnNumberPreviewView mein hota hai. Actual number save() ke
    waqt hi atomically lock ho ke assign hota hai.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        my_branch = getattr(request.user, 'branch', None)
        if not my_branch:
            return Response({"success": False, "message": "No branch assigned."}, status=400)

        fy = get_financial_year()
        branch_code = (my_branch.branch_code or "").strip().upper()

        seq = B2BOrderSequence.objects.filter(financial_year=fy).first()
        next_no = (seq.last_number if seq else 0) + 1
        next_no_str = str(next_no).zfill(4)

        preview = f"B2B/{branch_code}/{fy}/{next_no_str}" if branch_code else f"B2B/{fy}/{next_no_str}"
        return Response({"success": True, "next_order_id": preview})    
    
    
    
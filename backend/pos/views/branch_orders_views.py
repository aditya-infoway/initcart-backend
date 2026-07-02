# pos/views/branch_order_views.py
# NEW FILE

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework import status
from django.db.models import Q

from pos.models.branch_order import BranchOrder, BranchOrderItem
from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as ItemVariants
from pos.serializers.branch_order_serializers import (
    BranchOrderCreateSerializer,
    BranchOrderListSerializer,
    BranchOrderDetailSerializer,
    AdminProcessOrderSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination


# ─────────────────────────────────────────────────────────────
# 1. Normal Branch: Company items list (order karne ke liye)
# ─────────────────────────────────────────────────────────────

# pos/views/branch_order_views.py - CompanyItemsForOrderView

class CompanyItemsForOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
 
    def get(self, request):
        user = request.user
        ALLOWED_BRANCH_ROLES = ['branch', 'vendor', 'branch_customer', 'branch_agent', 'branch_both']
        if user.role not in ALLOWED_BRANCH_ROLES and not user.role.startswith('branch'):
            return Response({"success": False, "message": "Branch users only."}, status=403)
 
        search = request.GET.get('search', '').strip()
        category_filter = request.GET.get('category', '').strip()
 
        from pos.models.branch import Branch
        from django.contrib.auth import get_user_model
        User = get_user_model()
 
        superadmin_user = User.objects.filter(role='superadmin').first()
        if not superadmin_user:
            return Response({"success": False, "message": "Superadmin not found."}, status=404)
 
        try:
            superadmin_branch = Branch.objects.get(user=superadmin_user)
        except Branch.DoesNotExist:
            return Response({"success": False, "message": "Superadmin branch not found."}, status=404)
 
        qs = Items.objects.filter(
            entry_type='company',
            created_by_superadmin=True,
            branch=superadmin_branch,
        ).select_related(
            'c_brand', 'c_category', 'c_subCategory', 'c_subSubCategory', 'unit'
        ).prefetch_related('variants').order_by('itemName')
 
        if search:
            qs = qs.filter(
                Q(itemName__icontains=search) |
                Q(hsnCode__icontains=search) |
                Q(c_brand__brand_name__icontains=search) |
                Q(c_category__name__icontains=search)
            )
 
        if category_filter and category_filter.isdigit():
            qs = qs.filter(c_category_id=int(category_filter))
 
        # ── Paginate at ITEM level (not variant level) ──
        paginator = StandardResultsSetPagination()
        paginated_items = paginator.paginate_queryset(qs, request)
 
        items_list = []
        for item in paginated_items:
            item_data = {
                "item_id": item.id,
                "item_name": item.itemName,
                "category": item.c_category.name if item.c_category else item.category,
                "hsnCode": item.hsnCode,
                "taxSlab": item.taxSlab,
                "main_image": request.build_absolute_uri(item.main_image.url) if item.main_image else None,
                "variants": []
            }
 
            for v in item.variants.all():
                parts = [p for p in [v.color, v.size] if p]
                variant_label = " / ".join(parts) if parts else "Default"
 
                stock = v.current_stock or 0
                if stock <= 0:
                    stock = v.opStock or 0
 
                branch_price = v.branchPrice or v.salesPrice or 0
 
                item_data["variants"].append({
                    "variant_id": v.id,
                    "variant_label": variant_label,
                    "size": v.size,
                    "color": v.color,
                    "barcode": v.barcode,
                    "current_stock": stock,
                    "purchase_price": float(v.purchasePrice or 0),
                    "branch_price": float(branch_price),
                    "sales_price": float(v.salesPrice or 0),
                    "mrp": float(v.mrp or 0),
                    "hsnCode": item.hsnCode,
                    "taxSlab": item.taxSlab,
                    "global_item_code": f"GIC-{v.barcode}" if v.barcode else f"GIC-{item.id}-{v.id}",
                })
 
            item_data["total_stock"] = sum(v['current_stock'] for v in item_data['variants'])
            item_data["variant_count"] = len(item_data['variants'])
            items_list.append(item_data)
 
        return paginator.get_paginated_response({
            "success": True,
            "data": items_list,
        })

# ─────────────────────────────────────────────────────────────
# 2. Normal Branch: Order Create + List
# ─────────────────────────────────────────────────────────────

class BranchOrderListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
            """Branch ke apne orders list — search + status filter support ke saath"""
            user = request.user
            ALLOWED_BRANCH_ROLES = ['branch', 'vendor', 'branch_customer', 'branch_agent', 'branch_both']
            if user.role not in ALLOWED_BRANCH_ROLES and not user.role.startswith('branch'):
                return Response({"success": False, "message": "Branch users only."}, status=403)

            branch = getattr(user, 'branch', None)
            if not branch:
                return Response({"success": False, "message": "No branch assigned."}, status=400)

            search = request.GET.get('search', '').strip()

            qs = BranchOrder.objects.filter(branch=branch).prefetch_related('items').order_by('-created_at')

            if search:
                qs = qs.filter(
                    Q(order_id__icontains=search) |
                    Q(note__icontains=search) |
                    Q(status__icontains=search)
                )

            paginator = StandardResultsSetPagination()
            paginated = paginator.paginate_queryset(qs, request)
            serializer = BranchOrderListSerializer(paginated, many=True)
            return paginator.get_paginated_response({
                "success": True,
                "orders": serializer.data,
            })

    def post(self, request):
        """Branch ek naya order create kare"""
        user = request.user
        ALLOWED_BRANCH_ROLES = ['branch', 'vendor', 'branch_customer', 'branch_agent', 'branch_both']
        if user.role not in ALLOWED_BRANCH_ROLES and not user.role.startswith('branch'):
            return Response({"success": False, "message": "Branch users only."}, status=403)

        serializer = BranchOrderCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        if serializer.is_valid():
            order = serializer.save()
            return Response({
                "success": True,
                "message": f"Order {order.order_id} created successfully!",
                "order_id": order.order_id,
                "id": order.id,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BranchOrderDetailView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, order_id):
        user = request.user

        if user.role == 'superadmin':
            # Superadmin kisi bhi order ka detail dekh sakta hai
            try:
                order = BranchOrder.objects.prefetch_related('items').get(id=order_id)
            except BranchOrder.DoesNotExist:
                return Response({"error": "Order not found"}, status=404)
        else:
            # Branch sirf apne orders dekh sakti hai
            branch = getattr(user, 'branch', None)
            try:
                order = BranchOrder.objects.prefetch_related('items').get(
                    id=order_id, branch=branch
                )
            except BranchOrder.DoesNotExist:
                return Response({"error": "Order not found"}, status=404)

        serializer = BranchOrderDetailSerializer(order, context={"request": request})
        return Response({"success": True, "order": serializer.data})


# ─────────────────────────────────────────────────────────────
# 3. Superadmin: All Orders List (Order Tracking)
# ─────────────────────────────────────────────────────────────

class AdminOrderListView(APIView):
    """
    Superadmin ke liye — saari branches ke orders.
    Stock Transfer page ke Order Tracking tab mein use hoga.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        if user.role != 'superadmin':
            return Response({"success": False, "message": "Superadmin only."}, status=403)

        status_filter = request.GET.get('status', '').strip()
        branch_filter = request.GET.get('branch_id', '').strip()
        search = request.GET.get('search', '').strip()

        qs = BranchOrder.objects.prefetch_related('items').select_related('branch').order_by('-created_at')

        if status_filter:
            qs = qs.filter(status=status_filter)

        if branch_filter and branch_filter.isdigit():
            qs = qs.filter(branch_id=int(branch_filter))

        if search:
            qs = qs.filter(
                Q(order_id__icontains=search) |
                Q(branch__branch_name__icontains=search)
            )

        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(qs, request)
        serializer = BranchOrderListSerializer(paginated, many=True)
        return paginator.get_paginated_response({
            "success": True,
            "orders": serializer.data,
        })


# ─────────────────────────────────────────────────────────────
# 4. Superadmin: Order Process (adjust + transfer)
# ─────────────────────────────────────────────────────────────

class AdminProcessOrderView(APIView):
    """
    Superadmin order items adjust karke stock transfer create karta hai.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, order_id):
        user = request.user
        if user.role != 'superadmin':
            return Response({"success": False, "message": "Superadmin only."}, status=403)

        try:
            order = BranchOrder.objects.prefetch_related('items').get(id=order_id)
        except BranchOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.status in ['sent', 'cancelled']:
            return Response(
                {"success": False, "message": f"Order is already {order.status}."},
                status=400
            )

        serializer = AdminProcessOrderSerializer(
            order,
            data=request.data,
            context={"request": request}
        )
        if serializer.is_valid():
            updated_order = serializer.update(order, serializer.validated_data)
            return Response({
                "success": True,
                "message": f"Order {order.order_id} processed. Transfer created.",
                "order_status": updated_order.status,
                "linked_transfer": updated_order.linked_transfer.transfer_no
                    if updated_order.linked_transfer else None,
            })

        return Response(serializer.errors, status=400)


class AdminCancelOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, order_id):
        user = request.user
        if user.role != 'superadmin':
            return Response({"success": False, "message": "Superadmin only."}, status=403)

        try:
            order = BranchOrder.objects.get(id=order_id)
        except BranchOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.status in ['sent', 'cancelled']:
            return Response({"success": False, "message": "Already processed or cancelled."}, status=400)

        order.status = 'cancelled'
        order.save()

        return Response({"success": True, "message": f"Order {order.order_id} cancelled."})


# ─────────────────────────────────────────────────────────────
# 5. Stock Verification: Global Item Code se match
# ─────────────────────────────────────────────────────────────
# Note: Stock verification ka existing flow use hoga.
# Jab branch verify karti hai, to_variant ka barcode se match hoga.
# Global item code already BranchOrderItem mein stored hai.
# Verification ke baad stock add hoga (existing verify-item API se).
# Koi additional change nahi chahiye verification logic mein.
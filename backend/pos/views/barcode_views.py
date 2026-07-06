# pos/views/barcode_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework import status
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from pos.models.items import items, itemvariants
from pos.utils.barcode_generator import generate_unique_barcode


# ─────────────────────────────────────────────────────────────────
# 1. LIST – variants without a barcode (pending list)
# ─────────────────────────────────────────────────────────────────
class PendingBarcodesListView(APIView):
    """
    GET /api/pos/barcodes/pending/
    Returns all item-variants of the logged-in user's branch
    that have no barcode assigned yet.
    
    Query params:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 15, max: 100)
    - search: Search by item name, size, or color
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        branch = getattr(request.user, "branch", None)
        if not branch:
            return Response(
                {"success": False, "message": "No branch associated with this user"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Base queryset
        variants = (
            itemvariants.objects.filter(item__branch=branch)
            .filter(Q(barcode__isnull=True) | Q(barcode=""))
            .select_related("item", "item__unit")
            .order_by("item__itemName", "id")
        )

        # Apply search filter if provided
        search = request.GET.get("search", "").strip()
        if search:
            variants = variants.filter(
                Q(item__itemName__icontains=search) |
                Q(size__icontains=search) |
                Q(color__icontains=search)
            )

        # Pagination
        page_size = min(int(request.GET.get("page_size", 15)), 100)
        page_number = request.GET.get("page", 1)
        
        paginator = Paginator(variants, page_size)
        
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        # Serialize data
        data = [
            {
                "variant_id":      v.id,
                "item_id":         v.item.id,
                "item_name":       v.item.itemName,
                "hsn_code":        v.item.hsnCode or "",
                "size":            v.size or "",
                "color":           v.color or "",
                "mrp":             float(v.mrp or 0),
                "sales_price":     float(v.salesPrice or 0),
                "purchase_price":  float(v.purchasePrice or 0),
                "current_stock":   v.current_stock or v.opStock or 0,
                "op_stock":        v.opStock or 0,
                "barcode":         v.barcode or "",
                "unit":            v.item.unit.name if v.item.unit else "",
            }
            for v in page_obj
        ]

        return Response(
            {
                "success": True,
                "pending_variants": data,
                "count": paginator.count,
                "total_pages": paginator.num_pages,
                "current_page": page_obj.number,
                "page_size": page_size,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────
# 2. GENERATE – single variant
# ─────────────────────────────────────────────────────────────────
class GenerateSingleBarcodeView(APIView):
    """
    POST /api/pos/barcodes/generate/<variant_id>/
    Body (optional): { "barcode": "MANUAL123" }
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, variant_id):
        branch = getattr(request.user, "branch", None)
        if not branch:
            return Response(
                {"success": False, "message": "No branch associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            variant = itemvariants.objects.get(id=variant_id, item__branch=branch)
        except itemvariants.DoesNotExist:
            return Response(
                {"success": False, "message": "Variant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        manual_barcode = request.data.get("barcode", "").strip()

        if manual_barcode:
            if not manual_barcode.isalnum():
                return Response(
                    {"success": False, "message": "Barcode must be alphanumeric only"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                itemvariants.objects.filter(barcode=manual_barcode)
                .exclude(id=variant_id)
                .exists()
            ):
                return Response(
                    {"success": False, "message": "This barcode is already in use"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            barcode = manual_barcode
        else:
            try:
                barcode = generate_unique_barcode()
            except RuntimeError as e:
                return Response(
                    {"success": False, "message": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        variant.barcode = barcode
        variant.save(update_fields=["barcode"])

        return Response(
            {
                "success":    True,
                "variant_id": variant.id,
                "item_name":  variant.item.itemName,
                "barcode":    barcode,
                "message":    "Barcode generated successfully",
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────
# 3. BULK GENERATE
# ─────────────────────────────────────────────────────────────────
class BulkGenerateBarcodeView(APIView):
    """
    POST /api/pos/barcodes/bulk-generate/
    Body: { "variant_ids": [1, 2, 3] }
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        branch = getattr(request.user, "branch", None)
        if not branch:
            return Response(
                {"success": False, "message": "No branch associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        variant_ids = request.data.get("variant_ids", [])
        if not variant_ids:
            return Response(
                {"success": False, "message": "variant_ids list is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        errors  = []

        for vid in variant_ids:
            try:
                variant = itemvariants.objects.get(id=vid, item__branch=branch)
            except itemvariants.DoesNotExist:
                errors.append({"variant_id": vid, "message": "Not found"})
                continue

            if variant.barcode:
                results.append({
                    "variant_id":          variant.id,
                    "item_name":           variant.item.itemName,
                    "barcode":             variant.barcode,
                    "size":                variant.size or "",
                    "color":               variant.color or "",
                    "mrp":                 float(variant.mrp or 0),
                    "sales_price":         float(variant.salesPrice or 0),
                    "current_stock":       variant.current_stock or 0,
                    "success":             True,
                    "already_had_barcode": True,
                })
                continue

            try:
                barcode = generate_unique_barcode()
            except RuntimeError as e:
                errors.append({"variant_id": vid, "message": str(e)})
                continue

            variant.barcode = barcode
            variant.save(update_fields=["barcode"])

            results.append({
                "variant_id":    variant.id,
                "item_name":     variant.item.itemName,
                "barcode":       barcode,
                "size":          variant.size or "",
                "color":         variant.color or "",
                "mrp":           float(variant.mrp or 0),
                "sales_price":   float(variant.salesPrice or 0),
                "current_stock": variant.current_stock or 0,
                "success":       True,
            })

        return Response(
            {
                "success":         True,
                "results":         results,
                "errors":          errors,
                "generated_count": len([r for r in results if not r.get("already_had_barcode")]),
                "total_processed": len(results) + len(errors),
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────
# 4. UPDATE STOCK
# ─────────────────────────────────────────────────────────────────
class UpdateVariantStockView(APIView):
    """
    PUT /api/pos/barcodes/update-stock/<variant_id>/
    Body: { "stock": 10 }
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def put(self, request, variant_id):
        branch = getattr(request.user, "branch", None)
        if not branch:
            return Response(
                {"success": False, "message": "No branch associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            variant = itemvariants.objects.get(id=variant_id, item__branch=branch)
        except itemvariants.DoesNotExist:
            return Response(
                {"success": False, "message": "Variant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        stock_raw = request.data.get("stock")
        if stock_raw is None:
            return Response(
                {"success": False, "message": "stock field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            stock_val = int(stock_raw)
            if stock_val < 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"success": False, "message": "stock must be a non-negative integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fields_to_update = ["current_stock"]
        variant.current_stock = stock_val

        if not variant.opStock:
            variant.opStock = stock_val
            fields_to_update.append("opStock")

        variant.save(update_fields=fields_to_update)

        return Response(
            {
                "success":       True,
                "variant_id":    variant.id,
                "current_stock": variant.current_stock,
                "op_stock":      variant.opStock,
                "message":       "Stock updated successfully",
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────
# 5. CHECK AVAILABILITY
# ─────────────────────────────────────────────────────────────────
class CheckBarcodeAvailabilityView(APIView):
    """
    GET /api/pos/barcodes/check/?barcode=XXXX&exclude_variant=<id>
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        barcode = request.GET.get("barcode", "").strip()
        exclude_variant = request.GET.get("exclude_variant", None)

        if not barcode:
            return Response({"exists": False, "message": "No barcode provided"})

        qs = itemvariants.objects.filter(barcode=barcode)
        if exclude_variant:
            try:
                qs = qs.exclude(id=int(exclude_variant))
            except (ValueError, TypeError):
                pass

        exists = qs.exists()
        return Response({
            "exists":  exists,
            "barcode": barcode,
            "message": "Barcode already in use" if exists else "Barcode is available",
        })
        
        
class GeneratedBarcodesListView(APIView):
    """
    GET /api/pos/barcodes/generated/
    Returns all item-variants of the logged-in user's branch
    that already HAVE a barcode — with item_name included directly.
    Fixes the 'Item #undefined' bug caused by two-call ID mismatch.
    
    Query params:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 15, max: 100)
    - search: Search by item name, barcode, size, or color
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
 
    def get(self, request):
        branch = getattr(request.user, "branch", None)
        if not branch:
            return Response(
                {"success": False, "message": "No branch associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        variants = (
            itemvariants.objects.filter(item__branch=branch)
            .exclude(barcode__isnull=True)
            .exclude(barcode="")
            .select_related("item", "item__unit")
            .order_by("item__itemName", "id")
        )

        # Apply search filter if provided
        search = request.GET.get("search", "").strip()
        if search:
            variants = variants.filter(
                Q(item__itemName__icontains=search) |
                Q(barcode__icontains=search) |
                Q(size__icontains=search) |
                Q(color__icontains=search)
            )

        # Pagination
        page_size = min(int(request.GET.get("page_size", 15)), 100)
        page_number = request.GET.get("page", 1)
        
        paginator = Paginator(variants, page_size)
        
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
 
        data = [
            {
                "variant_id":    v.id,
                "item_id":       v.item.id,
                "item_name":     v.item.itemName,
                "entry_type":    v.item.entry_type,
                "hsn_code":      v.item.hsnCode or "",
                "size":          v.size or "",
                "color":         v.color or "",
                "mrp":           float(v.mrp or 0),
                "sales_price":   float(v.salesPrice or 0),
                "purchase_price":float(v.purchasePrice or 0),
                "current_stock": v.current_stock or v.opStock or 0,
                "op_stock":      v.opStock or 0,
                "barcode":       v.barcode,
                "unit":          v.item.unit.name if v.item.unit else "",
            }
            for v in page_obj
        ]
 
        return Response(
            {
                "success": True,
                "generated_variants": data,
                "count": paginator.count,
                "total_pages": paginator.num_pages,
                "current_page": page_obj.number,
                "page_size": page_size,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
            },
            status=status.HTTP_200_OK,
        )
        
        
# pos/views/barcode_views.py - Add this new view

class UpdateExistingBarcodeView(APIView):
    """
    PUT /api/pos/barcodes/update/<variant_id>/
    Body: { "barcode": "NEW_BARCODE" }
    
    Permission Rules:
    - Superadmin: Can update ANY item (company or manual) in their branch
    - Normal Branch: Can ONLY update manual items (entry_type='manual')
    - Only ADD/UPDATE operation - no deletion of existing barcode
    
    Returns:
    - 200: Success with updated barcode
    - 400: Validation errors
    - 403: Permission denied
    - 404: Variant not found
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def put(self, request, variant_id):
        user = request.user
        branch = getattr(user, "branch", None)
        
        if not branch:
            return Response(
                {"success": False, "message": "No branch associated with this user"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the variant
        try:
            variant = itemvariants.objects.get(id=variant_id, item__branch=branch)
        except itemvariants.DoesNotExist:
            return Response(
                {"success": False, "message": "Variant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ─── PERMISSION CHECK ──────────────────────────────────────
        is_superadmin = user.role == 'superadmin'
        item = variant.item

        if is_superadmin:
            # Superadmin can update ANY item in their branch
            pass  # Allowed
        else:
            # Normal branch: ONLY manual items
            if item.entry_type != 'manual':
                return Response(
                    {
                        "success": False,
                        "message": (
                            f"Permission denied: Cannot update barcode for '{item.entry_type}' type item. "
                            "Only manual items can be updated by normal branch users."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            
            # Also check that this branch actually created this item
            if item.created_by_superadmin:
                return Response(
                    {
                        "success": False,
                        "message": "Permission denied: This is a superadmin-created item."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # ─── GET NEW BARCODE ──────────────────────────────────────
        new_barcode = request.data.get("barcode", "").strip()
        
        if not new_barcode:
            return Response(
                {"success": False, "message": "barcode field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate barcode format
        if not new_barcode.isalnum():
            return Response(
                {"success": False, "message": "Barcode must be alphanumeric only"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if barcode already exists in this branch (excluding current variant)
        if itemvariants.objects.filter(
            barcode=new_barcode, 
            item__branch=branch
        ).exclude(id=variant_id).exists():
            return Response(
                {
                    "success": False,
                    "message": f"Barcode '{new_barcode}' already in use in this branch"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ─── UPDATE BARCODE ──────────────────────────────────────
        # Store old barcode for response (optional)
        old_barcode = variant.barcode

        # IMPORTANT: Only update if new barcode is different
        if old_barcode == new_barcode:
            return Response(
                {
                    "success": True,
                    "variant_id": variant.id,
                    "barcode": new_barcode,
                    "message": "Barcode unchanged (same value)",
                    "updated": False,
                },
                status=status.HTTP_200_OK,
            )

        # Save new barcode
        variant.barcode = new_barcode
        variant.save(update_fields=["barcode"])

        return Response(
            {
                "success": True,
                "variant_id": variant.id,
                "item_name": variant.item.itemName,
                "entry_type": variant.item.entry_type,
                "old_barcode": old_barcode or None,
                "new_barcode": new_barcode,
                "updated": True,
                "message": "Barcode updated successfully",
            },
            status=status.HTTP_200_OK,
        )
        
        
# pos/views/barcode_views.py - Add this for bulk updates

class BulkUpdateBarcodesView(APIView):
    """
    POST /api/pos/barcodes/bulk-update/
    Body: {
        "updates": [
            {"variant_id": 1, "barcode": "NEW001"},
            {"variant_id": 2, "barcode": "NEW002"}
        ]
    }
    
    Updates multiple barcodes in one request.
    Respects same permission rules as single update.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        user = request.user
        branch = getattr(user, "branch", None)
        
        if not branch:
            return Response(
                {"success": False, "message": "No branch associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updates = request.data.get("updates", [])
        if not updates:
            return Response(
                {"success": False, "message": "updates list is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_superadmin = user.role == 'superadmin'
        results = []
        errors = []

        for update in updates:
            variant_id = update.get("variant_id")
            new_barcode = update.get("barcode", "").strip()

            if not variant_id:
                errors.append({"variant_id": None, "message": "variant_id missing"})
                continue

            if not new_barcode:
                errors.append({"variant_id": variant_id, "message": "barcode missing"})
                continue

            try:
                variant = itemvariants.objects.get(id=variant_id, item__branch=branch)
            except itemvariants.DoesNotExist:
                errors.append({"variant_id": variant_id, "message": "Variant not found"})
                continue

            # Permission check
            item = variant.item
            if not is_superadmin and item.entry_type != 'manual':
                errors.append({
                    "variant_id": variant_id,
                    "message": f"Cannot update {item.entry_type} type item"
                })
                continue

            if not is_superadmin and item.created_by_superadmin:
                errors.append({
                    "variant_id": variant_id,
                    "message": "Cannot update superadmin-created item"
                })
                continue

            # Validate format
            if not new_barcode.isalnum():
                errors.append({
                    "variant_id": variant_id,
                    "message": "Barcode must be alphanumeric"
                })
                continue

            # Check uniqueness
            if itemvariants.objects.filter(
                barcode=new_barcode,
                item__branch=branch
            ).exclude(id=variant_id).exists():
                errors.append({
                    "variant_id": variant_id,
                    "message": f"Barcode '{new_barcode}' already in use"
                })
                continue

            old_barcode = variant.barcode
            if old_barcode != new_barcode:
                variant.barcode = new_barcode
                variant.save(update_fields=["barcode"])
                updated = True
            else:
                updated = False

            results.append({
                "variant_id": variant_id,
                "item_name": variant.item.itemName,
                "old_barcode": old_barcode or None,
                "new_barcode": new_barcode,
                "updated": updated,
                "success": True,
            })

        return Response(
            {
                "success": True,
                "results": results,
                "errors": errors,
                "total_processed": len(results) + len(errors),
                "updated_count": len([r for r in results if r.get("updated")]),
            },
            status=status.HTTP_200_OK,
        )                
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
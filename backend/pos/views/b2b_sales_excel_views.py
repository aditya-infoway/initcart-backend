# pos/views/b2b_sales_excel_views.py
#
# B2B Sales (Superadmin → Franchise) — Excel Template Download + Bulk Import
# ---------------------------------------------------------------------------
# UI CHANGE (business logic same, see note in b2b_sales_serializers.py):
#   - User pehle frontend pe ek Franchise select karta hai, phir "Download
#     Template" click karta hai → GET ?to_branch_id=<id>
#   - Template me TO_BRANCH ab dropdown nahi — selected franchise ka naam
#     fixed text ke roop me har row me pehle se bhara hota hai.
#   - ITEM_VARIANT ab dropdown nahi — from_branch ke SAARE current item
#     variants already rows ke roop me list hote hain (ek row = ek variant).
#   - QTY aur FRANCHISE_PRICE (pehle BRANCH_PRICE) columns sabse aakhir me
#     hain aur editable hain — baaki sab columns locked/reference-only.
#   - Import: sirf un rows se entry banti hai jinme QTY aur FRANCHISE_PRICE
#     DONO bhare ho. Poori file = EK hi B2B Sale (ek hi franchise).
#   - FRANCHISE_PRICE hi GST calculation + item rate ke liye use hota hai
#     (from_variant.branchPrice ki jagah) — B2BSaleCreateSerializer ab
#     per-item `rate` ko honor karta hai.
#
# URLs (unchanged):
#   path('b2b-sales-excel/template/', B2BSalesExcelTemplateView.as_view()),
#   path('b2b-sales-excel/import/',   B2BSalesExcelImportView.as_view()),

import io
from datetime import datetime

import pandas as pd
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Protection
from openpyxl.utils import get_column_letter

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError

from pos.models.branch import Branch
from pos.models.items import itemvariants as ItemVariants
from pos.serializers.stock_transfer_serializers import variant_info_str
from pos.serializers.b2b_sales_serializers import B2BSaleCreateSerializer

# ✅ Same permission model as the rest of the B2B Sales module
from ecommerce.permissions import IsSuperAdminOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS / SHARED HELPERS (template + import both use these — MUST stay
# identical between the two, otherwise a value written by the template
# wouldn't resolve correctly at import time)
# ─────────────────────────────────────────────────────────────────────────────

COLUMNS = [
    "TO_BRANCH", "SALE_DATE", "NOTE",
    "ITEM_VARIANT", "HSN_CODE", "UNIT", "TAX_PERCENT", "AVAILABLE_STOCK",
    "QTY", "FRANCHISE_PRICE",
]
COL_INDEX = {name: i + 1 for i, name in enumerate(COLUMNS)}  # 1-based for openpyxl

# Columns the user is allowed to edit in the template (rest stay locked)
EDITABLE_COLUMNS = {"SALE_DATE", "NOTE", "QTY", "FRANCHISE_PRICE"}


def _unit_symbol(item_obj):
    if item_obj.unit:
        return getattr(item_obj.unit, "symbol", None) or getattr(item_obj.unit, "name", "pc")
    return "pc"


def _franchise_label(branch):
    """Same label format used everywhere this branch's name is shown, so the
    text written into the template and the text matched at import time never
    drift apart."""
    if branch.city:
        return f"{branch.branch_name.strip()} — {branch.city.strip()}"
    return branch.branch_name.strip()


def get_branch_variant_lookup(branch):
    """
    Returns [(label, variant), ...] for every item variant that belongs to
    `branch` (the superadmin's OWN branch — since only your own stock can be
    B2B-sold out). Includes zero-stock items too — the template lists ALL
    current items, not just in-stock ones.

    Labels are deduped/disambiguated deterministically (ordered by item name
    then variant id) so the SAME label always resolves to the SAME variant.
    """
    variants_qs = (
        ItemVariants.objects.filter(item__branch=branch)
        .select_related("item", "item__unit")
        .order_by("item__itemName", "id")
    )

    seen = {}
    rows = []
    for v in variants_qs:
        info = (variant_info_str(v) or "").strip()
        base_label = f"{v.item.itemName} ({info})" if info else v.item.itemName
        key = base_label.strip().lower()
        if key in seen:
            seen[key] += 1
            label = f"{base_label} [#{v.id}]"   # disambiguate true collisions only
        else:
            seen[key] = 1
            label = base_label
        rows.append((label, v))
    return rows


def is_empty(v):
    """None / float NaN / pandas NaT (blank date cell) all count as empty."""
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip() == ""


def clean(v):
    """Numeric-looking text cells come back from pandas as floats
    (12345 -> 12345.0) — strip the trailing '.0'."""
    if is_empty(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_date(v, default=None):
    if is_empty(v):
        return default
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return default


def parse_qty_strict(v):
    """(decimal_value, is_valid). QTY on B2BSaleItem is now a DecimalField —
    fractional quantities (e.g. 2.5) are valid."""
    if is_empty(v):
        return None, True
    try:
        f = float(str(v).strip())
    except (ValueError, TypeError):
        return None, False
    return round(f, 2), True


def parse_price_strict(v):
    """(float_value, is_valid) for FRANCHISE_PRICE."""
    if is_empty(v):
        return None, True
    try:
        f = float(str(v).strip())
    except (ValueError, TypeError):
        return None, False
    return f, True


def _extract_error_message(exc):
    """DRF ValidationError.detail can be a list, dict or string — flatten it
    into one readable line instead of the raw ErrorDetail repr."""
    if isinstance(exc, DRFValidationError):
        detail = exc.detail
        if isinstance(detail, (list, tuple)) and detail:
            return str(detail[0])
        if isinstance(detail, dict):
            first_key = next(iter(detail), None)
            if first_key is not None:
                val = detail[first_key]
                if isinstance(val, (list, tuple)) and val:
                    return f"{first_key}: {val[0]}"
                return f"{first_key}: {val}"
        return str(detail)
    return str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 1) TEMPLATE DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────

class B2BSalesExcelTemplateView(APIView):
    """
    GET /b2b-sales-excel/template/?to_branch_id=<franchise branch id>

    Ek FIXED franchise ke liye template — TO_BRANCH ab text hai (dropdown
    nahi), aur ITEM_VARIANT me from_branch ke saare current items already
    row-wise list hote hain. User sirf QTY aur FRANCHISE_PRICE bharta/badalta
    hai (baaki columns locked hain).
    """

    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/b2bsales"

    def get(self, request):
        from_branch = request.user.get_effective_branch()
        if not from_branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        to_branch_id = request.query_params.get("to_branch_id")
        if not to_branch_id:
            return Response({"error": "to_branch_id is required"}, status=400)

        try:
            to_branch = Branch.objects.get(id=to_branch_id)
        except Branch.DoesNotExist:
            return Response({"error": "Selected franchise branch not found"}, status=404)

        if to_branch.ownership_type != "franchise" or to_branch.status != "active":
            return Response({"error": "Selected branch is not an active franchise branch"}, status=400)

        if to_branch.id == from_branch.id:
            return Response({"error": "Cannot create a B2B sale to your own branch"}, status=400)

        variant_lookup = get_branch_variant_lookup(from_branch)
        if not variant_lookup:
            return Response({"error": "No items found in your branch stock"}, status=400)

        wb = Workbook()
        ws = wb.active
        ws.title = "B2B Sale Data"

        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")   # grey = locked/reference
        editable_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")  # blue = editable
        header_font = Font(color="FFFFFF", bold=True)
        thin = Border(*(Side(style="thin"),) * 4)

        COLUMN_WIDTHS = {"ITEM_VARIANT": 42, "TO_BRANCH": 30, "NOTE": 30, "UNIT": 10}

        # ── Header row ──
        for idx, col_name in enumerate(COLUMNS, 1):
            required = col_name in ("TO_BRANCH", "SALE_DATE", "ITEM_VARIANT")
            label = col_name.replace("_", " ").title() + ("*" if required else "")
            if col_name == "TO_BRANCH":
                label = "Franchise*"
            if col_name == "FRANCHISE_PRICE":
                label = "Franchise Price*"
                
            cell = ws.cell(row=1, column=idx, value=label)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = thin
            ws.column_dimensions[get_column_letter(idx)].width = COLUMN_WIDTHS.get(col_name, 18)

        franchise_label = _franchise_label(to_branch)
        today_str = datetime.now().date()

        # ── Data rows — one row per current item variant, fully pre-filled ──
        for r, (item_label, v) in enumerate(variant_lookup, start=2):
            it = v.item
            available = v.current_stock or 0
            if available <= 0:
                available = v.opStock or 0

            row_values = {
                # ✅ Franchise name only on the FIRST data row — not repeated on every row
                "TO_BRANCH": franchise_label if r == 2 else "",
                "SALE_DATE": today_str,
                "NOTE": "",
                "ITEM_VARIANT": item_label,
                "HSN_CODE": it.hsnCode or "",
                "UNIT": _unit_symbol(it),
                "TAX_PERCENT": (it.taxSlab or "0").replace("%", ""),
                "AVAILABLE_STOCK": available,
                "QTY": None,
                "FRANCHISE_PRICE": float(v.branchPrice or 0),  # starting point, editable
            }

            for col_name, val in row_values.items():
                idx = COL_INDEX[col_name]
                cell = ws.cell(row=r, column=idx, value=val)
                cell.border = thin
                if col_name in EDITABLE_COLUMNS:
                    cell.fill = editable_fill
                    cell.protection = Protection(locked=False)
                else:
                    cell.fill = locked_fill
                    cell.protection = Protection(locked=True)
                    if col_name in ("HSN_CODE", "UNIT", "TAX_PERCENT", "AVAILABLE_STOCK"):
                        cell.font = Font(italic=True, color="808080")

        # ── Sheet protection: locked columns can't be edited, editable ones can ──
        ws.protection.sheet = True
        

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        safe_name = "".join(c for c in to_branch.branch_name if c.isalnum() or c in (" ", "_", "-")).strip()
        response["Content-Disposition"] = f'attachment; filename="b2b_sales_{safe_name}_template.xlsx"'
        return response


# ─────────────────────────────────────────────────────────────────────────────
# 2) IMPORT
# ─────────────────────────────────────────────────────────────────────────────

class B2BSalesExcelImportView(APIView):
    """
    Excel → ONE B2B Sale entry (single franchise, multiple items) — using the
    SAME B2BSaleCreateSerializer the "New B2B Sale" form posts to, so stock
    deduction / destination item creation / GST split stay identical to a
    sale created from the UI. Only difference: rate comes from the sheet's
    FRANCHISE_PRICE column instead of from_variant.branchPrice.

    A row is included ONLY if BOTH QTY and FRANCHISE_PRICE are filled.
    """

    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/b2bsales"

    def post(self, request):
        from_branch = request.user.get_effective_branch()
        if not from_branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        excel_file = request.FILES.get("file")
        if not excel_file:
            return Response({"error": "No file uploaded"}, status=400)

        try:
            df = pd.read_excel(excel_file, sheet_name=0, header=0)
        except Exception as e:
            return Response({"error": f"Could not read Excel file: {e}"}, status=400)

        # ✅ Column ORDER is authoritative here, not the header label text —
        # we control the template generation, and the header label ("Franchise*",
        # "Franchise Price*", etc.) can change independently without breaking
        # this. Just remap by position instead of matching names.
        if len(df.columns) < len(COLUMNS):
            return Response({
                "error": f"Expected {len(COLUMNS)} columns but found {len(df.columns)}. "
                         f"Please use the downloaded template without adding or removing columns."
            }, status=400)
        df = df.iloc[:, :len(COLUMNS)]
        df.columns = COLUMNS

        variant_lookup = {label.strip().lower(): v for label, v in get_branch_variant_lookup(from_branch)}

        errors = []

        # ── Resolve TO_BRANCH — take the first non-empty value in the file ──
        to_branch_raw = None
        for _, row in df.iterrows():
            v = clean(row.get("TO_BRANCH"))
            if v:
                to_branch_raw = v
                break

        if not to_branch_raw:
            return Response({"error": "TO_BRANCH is empty in the file"}, status=400)

        franchise_candidates = [
            b for b in Branch.objects.filter(ownership_type="franchise", status="active")
            if _franchise_label(b).strip().lower() == to_branch_raw.strip().lower()
        ]
        to_branch = None
        if len(franchise_candidates) == 1:
            to_branch = franchise_candidates[0]
        elif len(franchise_candidates) == 0:
            errors.append(f"Franchise branch '{to_branch_raw}' not found or no longer active")
        else:
            errors.append(f"Franchise name '{to_branch_raw}' matches more than one branch — please re-download the template")

        if to_branch and to_branch.id == from_branch.id:
            errors.append("Cannot B2B-sell to your own branch")

        # ── Resolve SALE_DATE — first non-empty value ──
        sale_date_val = None
        for _, row in df.iterrows():
            if not is_empty(row.get("SALE_DATE")):
                sale_date_val = parse_date(row.get("SALE_DATE"))
                break
        if sale_date_val is None:
            errors.append("SALE_DATE is missing or invalid in the file")

        # ── Resolve NOTE — first non-empty value (optional) ──
        note_val = ""
        for _, row in df.iterrows():
            v = clean(row.get("NOTE"))
            if v:
                note_val = v
                break

        # ── Resolve item rows — only where QTY and FRANCHISE_PRICE are BOTH filled ──
        resolved_items = []
        seen_variant_ids = set()

        for idx, row in df.iterrows():
            row_no = idx + 2
            item_raw = clean(row.get("ITEM_VARIANT"))
            qty_raw = row.get("QTY")
            price_raw = row.get("FRANCHISE_PRICE")

            if is_empty(qty_raw):
                continue  # not selected for this import — skip silently

            if not item_raw:
                errors.append(f"Row {row_no}: Qty filled but Item Variant is blank")
                continue

            variant = variant_lookup.get(item_raw.strip().lower())
            if not variant:
                errors.append(f"Row {row_no}: Item/variant '{item_raw}' not found in your branch stock")
                continue

            if variant.id in seen_variant_ids:
                errors.append(f"Row {row_no}: Item '{item_raw}' appears more than once — combine the quantity instead")
                continue

            qty_val, qty_ok = parse_qty_strict(qty_raw)
            if not qty_ok or not qty_val or qty_val <= 0:
                errors.append(f"Row {row_no}: QTY '{qty_raw}' is not a valid number greater than 0")
                continue

            # Franchise Price: use whatever the user left in the sheet; if
            # they cleared it, fall back to the branch's current price.
            if is_empty(price_raw):
                price_val = float(variant.branchPrice or 0)
            else:
                price_val, price_ok = parse_price_strict(price_raw)
                if not price_ok or price_val is None or price_val <= 0:
                    errors.append(f"Row {row_no}: FRANCHISE_PRICE '{price_raw}' is not a valid number greater than 0")
                    continue

            available = variant.current_stock or 0
            if available <= 0:
                available = variant.opStock or 0
            if qty_val > available:
                errors.append(
                    f"Row {row_no}: Insufficient stock for '{item_raw}'. Available: {available}, Requested: {qty_val}"
                )
                continue

            seen_variant_ids.add(variant.id)
            resolved_items.append({"variant": variant, "qty": qty_val, "price": price_val})

        if not resolved_items and not errors:
            errors.append("No item rows had a Qty filled in — nothing to import")

        if errors:
            return Response({"success": False, "errors": errors[:200]}, status=400)

        # ── Create the single B2B sale via B2BSaleCreateSerializer ──
        try:
            payload = {
                "to_branch_id": to_branch.id,
                "sale_date": sale_date_val,
                "note": note_val,
                "items": [
                    {"from_variant_id": it["variant"].id, "quantity": it["qty"], "rate": it["price"]}
                    for it in resolved_items
                ],
            }
            serializer = B2BSaleCreateSerializer(data=payload, context={"request": request})
            serializer.is_valid(raise_exception=True)
            sale = serializer.save()

            totals = sale.items.aggregate(net=Sum("net_amount"), qty=Sum("quantity"))
            created_sale = {
                "sale_no": sale.sale_no,
                "to_branch": sale.to_branch.branch_name,
                "sale_date": str(sale.sale_date),
                "items_count": sale.items.count(),
                "total_quantity": totals["qty"] or 0,
                "total_net": float(totals["net"] or 0),
            }
        except DRFValidationError as e:
            return Response({
                "success": False,
                "errors": [_extract_error_message(e)],
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            print("❌❌❌ B2B SALES IMPORT CRASH ❌❌❌")
            traceback.print_exc()
            return Response({
                "success": False,
                "errors": [f"Import failed while creating the B2B sale: {str(e)}"],
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "message": "B2B sale created successfully",
            "sales": [created_sale],
        }, status=status.HTTP_201_CREATED)
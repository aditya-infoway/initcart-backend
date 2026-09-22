# pos/views/stock_transfer_excel_views.py
#
# Stock Transfer (Superadmin/Employee → Branch) — Excel Template Download + Bulk Import
# ---------------------------------------------------------------------------
# B2B Sales Excel module jaisa hi flow, "New Transfer" (manual) ke liye:
#   - Frontend pe destination Branch select hoti hai (manual form jaisi hi list:
#     active + ownership_type='branch', apni branch nahi) → "Download Template"
#     → GET ?to_branch_id=<id>
#   - Template me TO_BRANCH fixed text hai, aur from_branch ke SAARE current
#     item variants rows ke roop me pre-filled hain (ek row = ek variant).
#   - RATE (branch price) READ-ONLY hai (locked + import me ignore hota hai —
#     hamesha variant ka current branchPrice hi use hota hai, bilkul manual
#     transfer jaisa).
#   - Editable columns: TRANSFER_DATE, NOTE (sirf pehli row), QTY, DISCOUNT_PERCENT.
#   - QTY DECIMAL bhi ho sakti hai (max 2 decimal places, e.g. 2.5 / 0.75) —
#     iske liye StockTransferItem.quantity DecimalField hona chahiye (model +
#     serializer update ke saath).
#   - Import: sirf un rows se entry banti hai jinme QTY bhari ho. Poori file =
#     EK hi Stock Transfer (ek hi destination branch), status 'pending', type 'manual'.
#   - Creation SAME StockTransferCreateSerializer se hoti hai jo manual
#     "New Transfer" form use karta hai → discount + GST (toggle / same-state
#     based) + destination item mapping bilkul manual jaisa.
#   - Permission: IsSuperAdminOrPagePermittedEmployee, page_key="/stockTransfer"
#     (GET = view permission, POST = add permission — same as B2B module).
#
# URLs (pos/urls.py):
#   path('stock-transfer-excel/template/', StockTransferExcelTemplateView.as_view()),
#   path('stock-transfer-excel/import/',   StockTransferExcelImportView.as_view()),
#   path('stock-transfer-excel/branches/', StockTransferBranchListView.as_view()),

import io
import logging
import math
import re
from datetime import datetime, date
from decimal import Decimal

import pandas as pd
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from pos.models.branch import Branch
from pos.models.items import itemvariants as ItemVariants
from pos.serializers.stock_transfer_serializers import (
    StockTransferCreateSerializer,
    variant_info_str,
)

# ✅ Same permission model as the rest of the Stock Transfer / B2B modules
from ecommerce.permissions import IsSuperAdminOrPagePermittedEmployee

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS / SHARED HELPERS (template + import dono yahi use karte hain —
# dono me IDENTICAL rehne chahiye, warna template ki value import me resolve
# nahi hogi)
# ─────────────────────────────────────────────────────────────────────────────

COLUMNS = [
    "TO_BRANCH", "TRANSFER_DATE", "NOTE",
    "ITEM_VARIANT", "HSN_CODE", "UNIT", "TAX_PERCENT", "AVAILABLE_STOCK",
    "RATE", "QTY", "DISCOUNT_PERCENT",
]
COL_INDEX = {name: i + 1 for i, name in enumerate(COLUMNS)}  # 1-based for openpyxl

HEADER_LABELS = {
    "TO_BRANCH":        "Destination Branch*",
    "TRANSFER_DATE":    "Transfer Date*",
    "NOTE":             "Note",
    "ITEM_VARIANT":     "Item Variant*",
    "HSN_CODE":         "HSN Code",
    "UNIT":             "Unit",
    "TAX_PERCENT":      "Tax Percent",
    "AVAILABLE_STOCK":  "Available Stock",
    "RATE":             "Rate (Branch Price)",
    "QTY":              "Qty",
    "DISCOUNT_PERCENT": "Discount %",
}

# Columns jo user edit kar sakta hai. TRANSFER_DATE / NOTE sirf pehli data row
# me editable hain (poore transfer ke liye ek hi value hoti hai).
ROW_EDITABLE_COLUMNS = {"QTY", "DISCOUNT_PERCENT"}
FIRST_ROW_EDITABLE_COLUMNS = {"TRANSFER_DATE", "NOTE"}

MAX_ERRORS_RETURNED = 200


def _norm_header(text):
    """Header compare karne ke liye: lowercase, spaces/underscores/'*' hata do."""
    return re.sub(r"[\s_*]+", "", str(text).lower())


def _unit_symbol(item_obj):
    if item_obj.unit:
        return getattr(item_obj.unit, "symbol", None) or getattr(item_obj.unit, "name", "pc")
    return "pc"


def _branch_label(branch):
    """Branch ka display label. Template me jo text likha jata hai aur import me
    jis text se match kiya jata hai — dono isi function se aate hain."""
    name = (branch.branch_name or "").strip()
    if branch.city and str(branch.city).strip():
        return f"{name} — {str(branch.city).strip()}"
    return name


def _destination_branches_qs():
    """Manual transfer form jaisi hi list: active + ownership_type='branch'."""
    return Branch.objects.filter(ownership_type="branch", status="active")


def _available_stock(variant):
    """Serializer / MyBranchItemsView jaisa hi: current_stock, na ho to opStock."""
    available = variant.current_stock or 0
    if available <= 0:
        available = variant.opStock or 0
    return available


def get_branch_variant_lookup(branch):
    """
    [(label, variant), ...] — `branch` (apni branch) ke SAARE item variants
    (zero-stock bhi). Labels deterministic (item name, phir variant id) tarah se
    disambiguate hote hain taaki same label hamesha same variant se resolve ho.
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
            label = f"{base_label} [#{v.id}]"   # sirf true collision par disambiguate
        else:
            seen[key] = 1
            label = base_label
        rows.append((label, v))
    return rows


def is_empty(v):
    """None / NaN / NaT / blank string — sab empty maane jate hain."""
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip() == ""


def clean(v):
    """Numeric-looking text cells pandas me float ban jate hain (123 -> 123.0)."""
    if is_empty(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_date(v):
    """Excel date cell (datetime/Timestamp) ya common text formats -> date. Invalid = None."""
    if is_empty(v):
        return None
    if isinstance(v, datetime):          # pd.Timestamp bhi datetime ka subclass hai
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:                              # raw Excel serial number
            return pd.to_datetime(v, unit="D", origin="1899-12-30").date()
        except Exception:
            return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_finite_float(v):
    try:
        f = float(str(v).strip())
    except (ValueError, TypeError):
        return None
    if not math.isfinite(f):
        return None
    return f


def parse_qty_strict(v):
    """
    (Decimal_value, is_valid). Qty decimal ho sakti hai — max 2 decimal places
    (model: DecimalField(12, 2)). 3+ decimal places ya non-number invalid.
    """
    if is_empty(v):
        return None, True
    f = _to_finite_float(v)
    if f is None or f >= 10 ** 10:
        return None, False
    scaled = round(f * 100)
    if abs(f * 100 - scaled) > 1e-6:      # 2 se zyada decimal places
        return None, False
    return Decimal(scaled) / Decimal(100), True


def fmt_qty(q):
    """Decimal qty ko readable text me: 2.00 -> '2', 2.50 -> '2.5'."""
    s = f"{Decimal(str(q)):f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def parse_discount_strict(v):
    """(float_value, is_valid). Empty = 0. Valid range 0–100 (serializer jaisa)."""
    if is_empty(v):
        return 0.0, True
    f = _to_finite_float(v)
    if f is None or f < 0 or f > 100:
        return None, False
    return round(f, 2), True


def _first_non_empty(df, col):
    for _, row in df.iterrows():
        if not is_empty(row.get(col)):
            return row.get(col)
    return None


def _extract_error_message(exc):
    """DRF ValidationError.detail list / dict / string ho sakta hai — ek readable line banao."""
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
# 0) DESTINATION BRANCH LIST (frontend dropdown)
# ─────────────────────────────────────────────────────────────────────────────

class StockTransferBranchListView(APIView):
    """
    GET /stock-transfer-excel/branches/
    Manual "New Transfer" ke destination dropdown jaisi list (active, ownership
    'branch', apni branch nahi) — employee ke liye bhi /stockTransfer page
    permission se chalti hai.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/stockTransferExcel"

    def get(self, request):
        my_branch = request.user.get_effective_branch()
        qs = _destination_branches_qs().order_by("branch_name")
        if my_branch:
            qs = qs.exclude(id=my_branch.id)

        data = [{
            "id": b.id,
            "branch_name": b.branch_name,
            "city": b.city,
            "state": b.state,
            "phone": b.phone,
            "email": b.email,
            "address": b.address,
            "pincode": b.pincode,
            "owner_name": b.owner_name,
        } for b in qs]
        return Response({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────────────────
# 1) TEMPLATE DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────

class StockTransferExcelTemplateView(APIView):
    """
    GET /stock-transfer-excel/template/?to_branch_id=<destination branch id>

    Ek FIXED destination branch ke liye template. Apni branch ke saare current
    item variants row-wise pre-filled. User sirf QTY aur DISCOUNT % (aur pehli
    row me date/note) bharta hai — RATE locked hai.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/stockTransferExcel"

    def get(self, request):
        from_branch = request.user.get_effective_branch()
        if not from_branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        to_branch_id = request.query_params.get("to_branch_id")
        if not to_branch_id:
            return Response({"error": "to_branch_id is required"}, status=400)

        try:
            to_branch = Branch.objects.get(id=to_branch_id)
        except (Branch.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Selected branch not found"}, status=404)

        if to_branch.ownership_type != "branch" or to_branch.status != "active":
            return Response({"error": "Selected branch is not an active branch"}, status=400)

        if to_branch.id == from_branch.id:
            return Response({"error": "Cannot create a stock transfer to your own branch"}, status=400)

        variant_lookup = get_branch_variant_lookup(from_branch)
        if not variant_lookup:
            return Response({"error": "No items found in your branch stock"}, status=400)

        wb = Workbook()
        ws = wb.active
        ws.title = "Stock Transfer Data"

        header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
        locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")    # grey = locked/reference
        editable_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")  # blue = editable
        header_font = Font(color="FFFFFF", bold=True)
        side = Side(style="thin")
        thin = Border(left=side, right=side, top=side, bottom=side)

        column_widths = {
            "TO_BRANCH": 30, "TRANSFER_DATE": 16, "NOTE": 30, "ITEM_VARIANT": 42,
            "HSN_CODE": 14, "UNIT": 10, "TAX_PERCENT": 12, "AVAILABLE_STOCK": 16,
            "RATE": 20, "QTY": 10, "DISCOUNT_PERCENT": 14,
        }

        # ── Header row ──
        for idx, col_name in enumerate(COLUMNS, 1):
            cell = ws.cell(row=1, column=idx, value=HEADER_LABELS[col_name])
            cell.fill = header_fill
            cell.font = header_font
            cell.border = thin
            ws.column_dimensions[get_column_letter(idx)].width = column_widths.get(col_name, 16)
        ws.freeze_panes = "A2"

        to_label = _branch_label(to_branch)
        today = timezone.localdate()
        last_row = len(variant_lookup) + 1

        # ── Data rows — ek row = ek current item variant, pre-filled ──
        for r, (item_label, v) in enumerate(variant_lookup, start=2):
            it = v.item
            first_row = (r == 2)

            row_values = {
                # Poore transfer ki single-value fields sirf pehli row me
                "TO_BRANCH": to_label if first_row else None,
                "TRANSFER_DATE": today if first_row else None,
                "NOTE": None,
                "ITEM_VARIANT": item_label,
                "HSN_CODE": it.hsnCode or "",
                "UNIT": _unit_symbol(it),
                "TAX_PERCENT": str(it.taxSlab or "0").replace("%", ""),
                "AVAILABLE_STOCK": _available_stock(v),
                "RATE": float(v.branchPrice or 0),   # read-only, import me ignore hota hai
                "QTY": None,
                "DISCOUNT_PERCENT": None,
            }

            for col_name, val in row_values.items():
                cell = ws.cell(row=r, column=COL_INDEX[col_name], value=val)
                if isinstance(val, str) and val.startswith("="):
                    cell.data_type = "s"   # text ko formula na samjhe
                cell.border = thin

                editable = (
                    col_name in ROW_EDITABLE_COLUMNS
                    or (first_row and col_name in FIRST_ROW_EDITABLE_COLUMNS)
                )
                if editable:
                    cell.fill = editable_fill
                    cell.protection = Protection(locked=False)
                else:
                    cell.fill = locked_fill
                    cell.protection = Protection(locked=True)
                    if col_name in ("HSN_CODE", "UNIT", "TAX_PERCENT", "AVAILABLE_STOCK", "RATE"):
                        cell.font = Font(italic=True, color="808080")

                if col_name == "TRANSFER_DATE":
                    cell.number_format = "DD-MM-YYYY"
                elif col_name == "RATE":
                    cell.number_format = "0.00"

        # ── Input validation (Excel me hi galat entry rok do) ──
        qty_col = get_column_letter(COL_INDEX["QTY"])
        disc_col = get_column_letter(COL_INDEX["DISCOUNT_PERCENT"])

        qty_dv = DataValidation(
            type="decimal", operator="greaterThanOrEqual", formula1="0.01", allow_blank=True,
            showErrorMessage=True, errorTitle="Invalid Qty",
            error="Qty must be a number greater than 0 (decimals allowed, up to 2 places, e.g. 2.5). Leave blank to skip this item.",
        )
        disc_dv = DataValidation(
            type="decimal", operator="between", formula1="0", formula2="100", allow_blank=True,
            showErrorMessage=True, errorTitle="Invalid Discount",
            error="Discount % must be a number between 0 and 100.",
        )
        ws.add_data_validation(qty_dv)
        ws.add_data_validation(disc_dv)
        qty_dv.add(f"{qty_col}2:{qty_col}{last_row}")
        disc_dv.add(f"{disc_col}2:{disc_col}{last_row}")

        # ── Sheet protection: locked columns edit nahi hote, editable hote hain ──
        ws.protection.sheet = True
        ws.protection.formatColumns = False   # column width adjust karne do
        ws.protection.formatRows = False

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        safe_name = "".join(c for c in to_branch.branch_name if c.isalnum() or c in (" ", "_", "-")).strip() or "branch"
        response["Content-Disposition"] = f'attachment; filename="stock_transfer_{safe_name}_template.xlsx"'
        return response


# ─────────────────────────────────────────────────────────────────────────────
# 2) IMPORT
# ─────────────────────────────────────────────────────────────────────────────

class StockTransferExcelImportView(APIView):
    """
    Excel → ONE Stock Transfer (ek destination branch, multiple items) — SAME
    StockTransferCreateSerializer se jo manual "New Transfer" form use karta hai,
    isliye discount / GST / destination-item mapping identical rehta hai.

    - Row tabhi include hoti hai jab QTY bhari ho.
    - RATE column IGNORE hota hai (read-only) — variant ka current branchPrice use hota hai.
    - Stock transfer 'pending' banta hai; stock destination branch ke verify par hi
      move hota hai (manual transfer jaisa).
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/stockTransferExcel"

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

        # ── Template sanity check: columns ki count + header names ──
        if len(df.columns) < len(COLUMNS):
            return Response({
                "error": f"Expected {len(COLUMNS)} columns but found {len(df.columns)}. "
                         f"Please use the downloaded Stock Transfer template without adding or removing columns."
            }, status=400)
        df = df.iloc[:, :len(COLUMNS)]

        actual_headers = [_norm_header(c) for c in df.columns]
        expected_headers = [_norm_header(HEADER_LABELS[c]) for c in COLUMNS]
        if actual_headers != expected_headers:
            return Response({
                "error": "This file doesn't match the Stock Transfer template. "
                         "Please download a fresh template and fill that."
            }, status=400)
        df.columns = COLUMNS

        variant_lookup = {
            label.strip().lower(): v for label, v in get_branch_variant_lookup(from_branch)
        }

        errors = []

        # ── Destination branch — file me pehli non-empty TO_BRANCH value ──
        to_branch_raw = clean(_first_non_empty(df, "TO_BRANCH"))
        if not to_branch_raw:
            return Response({"error": "Destination Branch is empty in the file"}, status=400)

        candidates = [
            b for b in _destination_branches_qs()
            if _branch_label(b).strip().lower() == to_branch_raw.strip().lower()
        ]
        to_branch = None
        if len(candidates) == 1:
            to_branch = candidates[0]
        elif len(candidates) == 0:
            errors.append(f"Destination branch '{to_branch_raw}' not found or no longer active")
        else:
            errors.append(
                f"Branch name '{to_branch_raw}' matches more than one branch — please re-download the template"
            )

        if to_branch and to_branch.id == from_branch.id:
            errors.append("Cannot transfer stock to your own branch")

        # ── Transfer date — pehli non-empty value ──
        raw_date = _first_non_empty(df, "TRANSFER_DATE")
        transfer_date = parse_date(raw_date) if raw_date is not None else None
        if transfer_date is None:
            errors.append("Transfer Date is missing or invalid (use a date like 20-09-2026)")

        # ── Note — pehli non-empty value (optional) ──
        note_val = clean(_first_non_empty(df, "NOTE"))

        # ── Item rows — sirf jahan QTY bhari ho ──
        resolved_items = []
        seen_variant_ids = set()

        for idx, row in df.iterrows():
            row_no = idx + 2  # header row = 1
            qty_raw = row.get("QTY")
            if is_empty(qty_raw):
                continue  # is import ke liye select nahi hui — chup-chaap skip

            item_raw = clean(row.get("ITEM_VARIANT"))
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
                errors.append(
                    f"Row {row_no}: QTY '{qty_raw}' must be a number greater than 0 (up to 2 decimal places)"
                )
                continue

            disc_val, disc_ok = parse_discount_strict(row.get("DISCOUNT_PERCENT"))
            if not disc_ok:
                errors.append(
                    f"Row {row_no}: DISCOUNT % '{clean(row.get('DISCOUNT_PERCENT'))}' must be a number between 0 and 100"
                )
                continue

            # RATE sheet se NAHI liya jata (read-only) — current branch price
            rate_val = float(variant.branchPrice or 0)
            if rate_val <= 0:
                errors.append(
                    f"Row {row_no}: '{item_raw}' has no Branch Price set — set its branch price first, then re-download the template"
                )
                continue

            available = _available_stock(variant)
            # Decimal(str()) — float/Decimal stock ke saath exact compare ke liye
            if qty_val > Decimal(str(available)):
                errors.append(
                    f"Row {row_no}: Insufficient stock for '{item_raw}'. "
                    f"Available: {fmt_qty(available)}, Requested: {fmt_qty(qty_val)}"
                )
                continue

            seen_variant_ids.add(variant.id)
            resolved_items.append({
                "variant": variant,
                "qty": qty_val,
                "rate": rate_val,
                "discount": disc_val or 0.0,
            })

        if not resolved_items and not errors:
            errors.append("No item rows had a Qty filled in — nothing to import")

        if errors:
            return Response({"success": False, "errors": errors[:MAX_ERRORS_RETURNED]}, status=400)

        # ── Ek Stock Transfer banao — manual form wale serializer se ──
        try:
            payload = {
                "to_branch_id": to_branch.id,
                "transfer_date": transfer_date.isoformat(),
                "note": note_val,
                "transfer_type": "manual",
                "items": [
                    {
                        "from_variant_id": it["variant"].id,
                        "quantity": it["qty"],
                        "rate": it["rate"],
                        "discount_percent": it["discount"],
                    }
                    for it in resolved_items
                ],
            }
            with transaction.atomic():
                serializer = StockTransferCreateSerializer(data=payload, context={"request": request})
                serializer.is_valid(raise_exception=True)
                transfer = serializer.save()

            totals = transfer.items.aggregate(net=Sum("net_amount"), qty=Sum("quantity"))
            created_transfer = {
                "transfer_no": transfer.transfer_no,
                "to_branch": transfer.to_branch.branch_name,
                "transfer_date": str(transfer.transfer_date),
                "items_count": transfer.items.count(),
                "total_quantity": float(totals["qty"] or 0),
                "total_net": float(totals["net"] or 0),
            }
        except DRFValidationError as e:
            return Response({
                "success": False,
                "errors": [_extract_error_message(e)],
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Stock transfer Excel import crashed")
            return Response({
                "success": False,
                "errors": [f"Import failed while creating the stock transfer: {str(e)}"],
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "message": "Stock transfer created successfully",
            "transfers": [created_transfer],
        }, status=status.HTTP_201_CREATED)
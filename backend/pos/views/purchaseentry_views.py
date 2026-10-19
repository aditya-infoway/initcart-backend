from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

from django.db import transaction
from django.db.models import Q, Sum, Prefetch
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from pos.models.bankreceipt import BankReceipt
from pos.models.cashreceipt import CashReceipt
from pos.models.branch import Branch
from pos.models.settings import setting
from pos.models.account import Account
from pos.models.items import items, itemvariants  # noqa: F401
from pos.models.purchaseentry import PurchaseItem, PurchaseMaster
from pos.models.purchasereturn import PurchaseReturnMaster
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.serializers.account_serializer import AccountSerializer
from pos.serializers.settings_serializers import SettingSerializers
from pos.serializers.purchaseentry_serializers import (  # noqa: F401
    ItemSerializer,
    PurchaseSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination
from pos.utils.item_cache import get_branch_variant_data, search_variants, find_by_barcode
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee
from pos.utils.default_tax_accounts import post_tax_to_accounts


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def to_decimal(value, default=Decimal("0.00")):
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value).replace("%", "").strip())
    except (InvalidOperation, ValueError):
        return default


def round2(value, default=0):
    """Har tarah ka decimal input (string/float/int/None) ko safe 2-decimal float me convert karta hai."""
    try:
        if value is None or value == "":
            return default
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return default


def sanitize_purchase_payload(data):
    """Request data me jitne bhi decimal fields hain sabko 2 decimal places tak round karta hai — model/serializer tak pahunchne se pehle."""
    master_fields = [
        "frightcharge", "otherexpnse", "roundamount",
        "grand_total", "total_basic", "total_tax", "total_net",
    ]
    for f in master_fields:
        if f in data:
            data[f] = round2(data[f])

    item_fields = [
        "quantity", "altQuantity", "price", "discountPercent",
        "basicAmount", "discountAmount", "taxAmount", "netValue",
        "cgst", "sgst", "igst",
    ]
    if "items" in data:
        for item in data["items"]:
            for f in item_fields:
                if f in item:
                    item[f] = round2(item[f])
    return data


def _next_voucher_no(model, branch, setting_attr, default_prefix):
    """Voucher number: PREFIX/FY/0001 (financial year April se)"""
    settings_obj = setting.objects.filter(branch=branch).first()
    prefix = getattr(settings_obj, setting_attr, default_prefix) if settings_obj else default_prefix

    last_voucher = model.objects.filter(branch=branch).order_by("-id").first()

    last_no = 0
    if last_voucher and last_voucher.voucher_no:
        try:
            parts = last_voucher.voucher_no.split("/")
            if len(parts) >= 3:
                last_no = int(parts[-1])
        except (ValueError, IndexError):
            last_no = 0

    now = datetime.now()
    if now.month >= 4:
        fy_start, fy_end = now.year, now.year + 1
    else:
        fy_start, fy_end = now.year - 1, now.year

    fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
    return f"{prefix}/{fy}/{str(last_no + 1).zfill(4)}"


def generate_bank_payment_voucher(branch):
    """Bank Payments (BP and PBP share same sequence)"""
    return _next_voucher_no(BankPayment, branch, "BP", "BP")


def generate_cash_payment_voucher(branch):
    """Cash Payments (CP and PCP share same sequence)"""
    return _next_voucher_no(CashPayment, branch, "CP", "CP")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class PurchaseCreateView(APIView):
    """Create a new purchase entry"""
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"

    def post(self, request):
        data = sanitize_purchase_payload(request.data.copy())
        serializer = PurchaseSerializer(data=data, context={"request": request})

        with transaction.atomic():
            serializer.is_valid(raise_exception=True)
            purchase = serializer.save()

            post_tax_to_accounts(purchase.branch, "purchase", purchase.items.all())

            terms = purchase.terms.strip().lower() if purchase.terms else ""

            # CREDIT PURCHASE - Supplier ka Cr balance badhao
            if terms == "credit":
                if purchase.partyName:
                    purchase.update_balance(purchase.partyName, purchase.grand_total, "Cr")

            # CASH PURCHASE - PCP banao (Supplier balance nahi badlega)
            elif terms == "cash":
                cash_account = purchase.case_account

                if cash_account and purchase.partyName:
                    branch = request.user.get_effective_branch()

                    CashPayment.objects.create(
                        date=purchase.date,
                        voucher_no=generate_cash_payment_voucher(branch),
                        cash_account=cash_account,
                        op_account=purchase.partyName,
                        branch=branch,
                        amount=purchase.grand_total,
                        mode="Cash",
                        narration=f"Auto payment against Purchase {purchase.billNo}",
                        type="PCP",
                        purchase=purchase,
                        created_by=request.user,
                    )

            # BANK PURCHASE - PBP banao
            elif terms == "bank":
                bank_account = purchase.bank_account

                if bank_account and purchase.partyName:
                    branch = request.user.get_effective_branch()

                    BankPayment.objects.create(
                        date=purchase.date,
                        voucher_no=generate_bank_payment_voucher(branch),
                        bank_account=bank_account,
                        op_account=purchase.partyName,
                        branch=branch,
                        amount=purchase.grand_total,
                        mode="Auto",
                        narration=f"Auto payment against Purchase {purchase.billNo}",
                        type="PBP",
                        purchase=purchase,
                        created_by=request.user,
                    )

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PurchaseItemListAPIView(APIView):
    """List purchase entries — server-side search/filter/pagination (N+1 fixed)

    Query params (sab optional):
      page, page_size    -> pagination
      search             -> billNo / purchasebill_no / party name (icontains)
      terms              -> Credit / Cash / Bank
      date_from, date_to -> YYYY-MM-DD
    Response me extra key: overall_total (filter ke baad ke saare records ka grand_total)
    """
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        branch = user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)

        branch_id_param = request.GET.get('branch_id')
        if branch_id_param and (is_superadmin or is_employee):
            try:
                branch = Branch.objects.get(id=branch_id_param)
            except Branch.DoesNotExist:
                return Response({'error': 'Branch not found'}, status=404)

        qs = PurchaseMaster.objects.filter(branch=branch)

        search = request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(billNo__icontains=search) |
                Q(purchasebill_no__icontains=search) |
                Q(partyName__account_name__icontains=search)
            )

        terms = request.GET.get('terms', '').strip()
        if terms:
            qs = qs.filter(terms__iexact=terms)

        date_from = request.GET.get('date_from', '').strip()
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = request.GET.get('date_to', '').strip()
        if date_to:
            qs = qs.filter(date__lte=date_to)

        overall_total = qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

        qs = (
            qs.select_related("partyName", "created_by")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=PurchaseItem.objects.select_related("itemName", "variant"),
                )
            )
            .order_by('-date', '-id')
        )

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)

        serializer = PurchaseSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data['overall_total'] = float(overall_total)
        return response
class PurchaseentryUpdate(APIView):
    """Update a purchase entry"""
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"

    def put(self, request, id):
        try:
            entry = PurchaseMaster.objects.get(id=id)
        except PurchaseMaster.DoesNotExist:
            return Response({"error": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

        data = sanitize_purchase_payload(request.data.copy())
        serializer = PurchaseSerializer(entry, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, id):
        try:
            entry = PurchaseMaster.objects.get(id=id)
        except PurchaseMaster.DoesNotExist:
            return Response({"error": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

        data = sanitize_purchase_payload(request.data.copy())
        serializer = PurchaseSerializer(entry, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PurchaseItemDelete(APIView):
    """Delete a purchase item"""
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"

    def delete(self, request, id, *args, **kwargs):
        try:
            item = PurchaseItem.objects.get(id=id)
            item.delete()
            return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)
        except PurchaseItem.DoesNotExist:
            return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER / LOOKUP APIS — only IsAuthenticated
# ─────────────────────────────────────────────────────────────────────────────

class AccountCheckView(APIView):
    """Check account balance before purchase"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if not pk:
            return Response({"show_alert": False, "alert_message": ""})

        try:
            account = Account.objects.get(pk=pk)
        except Account.DoesNotExist:
            return Response({"detail": "Account not found"}, status=status.HTTP_404_NOT_FOUND)

        data = AccountSerializer(account).data

        show_alert = False
        alert_message = ""
        required_amount = to_decimal(request.GET.get("required_amount"))

        if account.group in ["Bank Account", "Case In Hand"]:
            if account.current_balance == 0:
                show_alert = True
                alert_message = f"Current balance in {account.account_name} is 0. Purchase not allowed."
            elif required_amount > 0:
                available = account.current_balance if account.current_drcr == "Dr" else Decimal("0.00")
                if available < required_amount:
                    show_alert = True
                    alert_message = (
                        f"Insufficient balance in {account.account_name}. "
                        f"Available: Rs {available}, Required: Rs {required_amount}. "
                        f"Purchase not allowed."
                    )

        data["show_alert"] = show_alert
        data["alert_message"] = alert_message
        return Response(data)


class PurchaseItemListAllAPIView(APIView):
    """All variants for dropdown/modal — Redis cached"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_branch = request.user.get_effective_branch()
        if not user_branch:
            return Response({"error": "User branch not found"}, status=400)

        data = get_branch_variant_data(user_branch)
        return Response(data["rows"])


class BranchItemsAPIView(APIView):
    """Get all items for a branch (dropdown)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_branch = request.user.get_effective_branch()
        if not user_branch:
            return Response({"detail": "User branch not found"}, status=404)

        items_list = items.objects.filter(branch=user_branch).select_related("unit")

        result = []
        for item in items_list:
            unit_name = "-"
            if item.unit:
                unit_name = item.unit.name if hasattr(item.unit, 'name') else str(item.unit)

            result.append({
                "id": item.id,
                "itemName": item.itemName,
                "hsnCode": item.hsnCode or "",
                "unit": unit_name,
                "taxSlab": item.taxSlab or "0",
                "brand": item.brand or "",
                "category": item.category or "",
                "subCategory": item.subCategory or "",
                "subSubCategory": item.subSubCategory or "",
            })

        return Response(result)


class PurchaseItemTaxAPIView(APIView):
    """Calculate GST for purchase item"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_id = request.data.get("item_id")
        party_id = request.data.get("party_id")
        price = to_decimal(request.data.get("price"))
        qty = to_decimal(request.data.get("qty"), Decimal('1'))
        discount_percent = to_decimal(request.data.get("discount_percent"), Decimal('0'))

        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        settings_obj = setting.objects.filter(branch=branch).first()
        gst_toggle = getattr(settings_obj, 'gst_toggle', True)

        if not item_id:
            return Response({"error": "item_id is required"}, status=400)
        if not party_id:
            return Response({"error": "party_id is required"}, status=400)

        try:
            item = items.objects.select_related("branch").get(id=item_id)
        except items.DoesNotExist:
            return Response({"error": "Item not found"}, status=404)

        try:
            party = Account.objects.get(id=party_id)
        except Account.DoesNotExist:
            return Response({"error": "Party not found"}, status=404)

        tax_percent = to_decimal(item.taxSlab)

        total_price = (price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        discount_amount = (total_price * discount_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        amount_after_discount = (total_price - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        cgst = sgst = igst = total_tax = Decimal('0.00')
        basic_amount = Decimal('0.00')
        net_amount = Decimal('0.00')

        branch_state = (item.branch.state or "").strip().lower()
        party_state = (party.state or "").strip().lower()

        if tax_percent > 0:
            if gst_toggle:
                total_tax = (amount_after_discount * tax_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                basic_amount = amount_after_discount
                net_amount = (basic_amount + total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                total_tax = (amount_after_discount * tax_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                net_amount = amount_after_discount
                basic_amount = (net_amount - total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            if branch_state == party_state:
                half_tax = (total_tax / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                cgst = half_tax
                sgst = half_tax
                if cgst + sgst != total_tax:
                    if total_tax - (cgst + sgst) > 0:
                        cgst += (total_tax - (cgst + sgst))
            else:
                igst = total_tax
        else:
            basic_amount = amount_after_discount
            net_amount = amount_after_discount

        return Response({
            "item_id": item.id,
            "item_name": item.itemName,
            "party_id": party.id,
            "branch_state": branch_state,
            "party_state": party_state,
            "tax_percent": float(tax_percent),
            "gst_toggle": gst_toggle,
            "basic_amount": float(basic_amount),
            "total_price": float(total_price),
            "discount_percent": float(discount_percent),
            "discount_amount": float(discount_amount),
            "amount_after_discount": float(amount_after_discount),
            "cgst": float(cgst),
            "sgst": float(sgst),
            "igst": float(igst),
            "total_tax": float(total_tax),
            "net_amount": float(net_amount),
        }, status=status.HTTP_200_OK)


class GstToggleAPIView(APIView):
    """Get/Update GST toggle setting"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        settings_obj = setting.objects.filter(branch=branch).first()
        return Response(SettingSerializers(settings_obj).data)

    def post(self, request):
        gst_toggle = request.data.get("gst_toggle")

        if gst_toggle is None:
            return Response({"error": "gst_toggle is required"}, status=400)

        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        setting_obj = setting.objects.filter(branch=branch).order_by("-id").first()

        if not setting_obj:
            setting.objects.create(branch=branch, gst_toggle=gst_toggle)
        else:
            setting_obj.gst_toggle = gst_toggle
            setting_obj.save()

        return Response({"gst_toggle": gst_toggle}, status=200)


class PurchaseItemSearchAPIView(APIView):
    """Search variants — process-memory/Redis cached, DB hit nahi.
    ?query=...&limit=50   -> text search
    ?barcode=XXXX         -> exact barcode lookup (scanner), [row] ya []
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_branch = request.user.get_effective_branch()
        if not user_branch:
            return Response({"error": "User branch not found"}, status=400)

        barcode = request.GET.get("barcode", "").strip()
        if barcode:
            row = find_by_barcode(user_branch, barcode)
            return Response([row] if row else [])

        search = request.GET.get("query", "").strip()

        try:
            limit = int(request.GET.get("limit", 50))   # ?limit=0 = sab results
        except (TypeError, ValueError):
            limit = 50

        return Response(search_variants(user_branch, search, limit))


class PurchaseCreditBillsAPIView(APIView):
    """Purchase credit bills with pending amount — fixed ~7 queries (pehle har bill pe 4-5)"""
    permission_classes = [IsAuthenticated]

    def get(self, request): 
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        search = request.GET.get('query', '').strip()

        bills_qs = PurchaseMaster.objects.filter(
            branch=branch, terms__iexact='credit'
        ).select_related("partyName")

        if search:
            bills_qs = bills_qs.filter(
                Q(billNo__icontains=search) |
                Q(partyName__account_name__icontains=search)
            )

        bills = list(bills_qs)
        if not bills:
            return Response({'type': 'purchase', 'bills': []})

        bill_ids = [b.id for b in bills]
        bill_nos = [b.billNo for b in bills]
        ZERO = Decimal('0')

        # 1) Payments (cash + bank) — bill-wise total, 2 queries
        paid = defaultdict(lambda: ZERO)
        for Model in (CashPayment, BankPayment):
            rows = (
                Model.objects.filter(purchase_id__in=bill_ids)
                .values("purchase")
                .annotate(t=Sum("amount"))
                .order_by()
            )
            for r in rows:
                paid[r["purchase"]] += r["t"] or ZERO

        # 2) Returns — 1 query
        returns_by_bill = defaultdict(list)
        for pr in PurchaseReturnMaster.objects.filter(branch=branch, original_bill_no__in=bill_nos):
            returns_by_bill[pr.original_bill_no].append(pr)

        # 3) Credit returns ki receipts — 2 queries
        credit_return_ids = [
            pr.id for lst in returns_by_bill.values() for pr in lst
            if (pr.payment_terms or "").lower() == "credit"
        ]
        received = defaultdict(lambda: ZERO)
        if credit_return_ids:
            for Model in (CashReceipt, BankReceipt):
                rows = (
                    Model.objects.filter(purchase_return_id__in=credit_return_ids)
                    .values("purchase_return")
                    .annotate(t=Sum("amount"))
                    .order_by()
                )
                for r in rows:
                    received[r["purchase_return"]] += r["t"] or ZERO

        bills_data = []
        for bill in bills:
            total_paid = paid[bill.id]
            bill_returns = returns_by_bill.get(bill.billNo, [])
            total_all_returned = sum((pr.grand_total for pr in bill_returns), ZERO)

            credit_returns_unsettled = ZERO
            for pr in bill_returns:
                if (pr.payment_terms or "").lower() != "credit":
                    continue
                got = received[pr.id]
                if got < pr.grand_total:
                    credit_returns_unsettled += pr.grand_total - got

            pending_amount = bill.grand_total - total_paid - credit_returns_unsettled

            if pending_amount > Decimal('0.005'):
                bills_data.append({
                    'id': bill.id,
                    'billNo': bill.billNo,
                    'originalBillNo': bill.billNo,
                    'partyName__account_name': bill.partyName.account_name if bill.partyName else "",
                    'party_id': bill.partyName.id if bill.partyName else None,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'grand_total': float(bill.grand_total),
                    'paid_amount': float(total_paid),
                    'returned_amount': float(total_all_returned),
                    'pending_amount': float(pending_amount),
                })

        return Response({
            'type': 'purchase',
            'bills': bills_data
        })


class PayPurchaseCreditBillCashAPIView(APIView):
    """Pay a purchase credit bill via cash payment (creates PCP)"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data
        purchase_bill_id = data.get('purchase_bill_id')
        cash_account_id = data.get('cash_account')
        amount = Decimal(str(data.get('amount', 0)))

        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        try:
            purchase_bill = PurchaseMaster.objects.get(
                id=purchase_bill_id,
                branch=branch
            )

            if purchase_bill.terms.lower() != 'credit':
                return Response({'error': 'This bill is not a credit bill'}, status=400)

            cash_payment = CashPayment.objects.create(
                date=data['date'],
                voucher_no=generate_cash_payment_voucher(branch),
                cash_account_id=cash_account_id,
                op_account_id=purchase_bill.partyName.id,
                branch=branch,
                amount=amount,
                mode="Cash",
                narration=f"Payment against purchase credit bill {purchase_bill.billNo}",
                type="PCP",
                purchase=purchase_bill,
                created_by=request.user,
            )

            return Response({
                'success': True,
                'message': 'Purchase credit bill paid successfully',
                'payment': {
                    'id': cash_payment.id,
                    'voucher_no': cash_payment.voucher_no,
                    'amount': float(cash_payment.amount),
                    'type': cash_payment.type
                }
            }, status=status.HTTP_201_CREATED)

        except PurchaseMaster.DoesNotExist:
            return Response({'error': 'Purchase bill not found'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class PayPurchaseCreditBillBankAPIView(APIView):
    """Pay a purchase credit bill via bank payment (creates PBP)"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data
        purchase_bill_id = data.get('purchase_bill_id')
        bank_account_id = data.get('bank_account')
        amount = Decimal(str(data.get('amount', 0)))
        mode = data.get('mode', 'UPI')

        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        try:
            purchase_bill = PurchaseMaster.objects.get(
                id=purchase_bill_id,
                branch=branch
            )

            if purchase_bill.terms.lower() != 'credit':
                return Response({'error': 'This bill is not a credit bill'}, status=400)

            bank_payment = BankPayment.objects.create(
                date=data['date'],
                voucher_no=generate_bank_payment_voucher(branch),
                bank_account_id=bank_account_id,
                op_account_id=purchase_bill.partyName.id,
                branch=branch,
                amount=amount,
                mode=mode,
                cheque_no=data.get('cheque_no'),
                cheque_date=data.get('cheque_date'),
                cheque_clear_date=data.get('cheque_clear_date'),
                narration=f"Payment against purchase credit bill {purchase_bill.billNo}",
                type="PBP",
                purchase=purchase_bill,
                created_by=request.user,
            )

            return Response({
                'success': True,
                'message': 'Purchase credit bill paid successfully',
                'payment': {
                    'id': bank_payment.id,
                    'voucher_no': bank_payment.voucher_no,
                    'amount': float(bank_payment.amount),
                    'type': bank_payment.type
                }
            }, status=status.HTTP_201_CREATED)

        except PurchaseMaster.DoesNotExist:
            return Response({'error': 'Purchase bill not found'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
from django.db import transaction
from pos.models.bankreceipt import BankReceipt
from pos.models.cashreceipt import CashReceipt
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django.db.models import Q, Sum
from pos.models.branch import Branch
from pos.models.settings import setting
from pos.models.account import Account
from pos.models.items import items, itemvariants
from pos.models.purchaseentry import PurchaseItem, PurchaseMaster
from pos.serializers.account_serializer import AccountSerializer
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pos.serializers.settings_serializers import SettingSerializers
from pos.serializers.purchaseentry_serializers import (
    ItemSerializer,
    PurchaseSerializer,
)
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


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


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class PurchaseCreateView(APIView):
    """Create a new purchase entry"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"  # ✅ ADD: Frontend route

    def generate_bank_payment_voucher(self, branch):
        """Generate voucher number for Bank Payments (BP and PBP share same sequence)"""
        from datetime import datetime
        from pos.models.settings import setting
        from pos.models.bankpayment import BankPayment
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BP", "BP") if settings_obj else "BP"
            
        last_voucher = BankPayment.objects.filter(
            branch=branch
        ).order_by("-id").first()
        
        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                parts = last_voucher.voucher_no.split("/")
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0
        
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year
        
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{prefix}/{fy}/{next_no}"
        
        return voucher_no

    def generate_cash_payment_voucher(self, branch):
        """Generate voucher number for Cash Payments (CP and PCP share same sequence)"""
        from datetime import datetime
        from pos.models.settings import setting
        from pos.models.cashpayment import CashPayment
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CP", "CP") if settings_obj else "CP"
        
        last_voucher = CashPayment.objects.filter(
            branch=branch
        ).order_by("-id").first()
        
        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                parts = last_voucher.voucher_no.split("/")
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0
        
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year
        
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{prefix}/{fy}/{next_no}"
        
        return voucher_no

    def post(self, request):
        data = sanitize_purchase_payload(request.data.copy())
        serializer = PurchaseSerializer(data=data, context={"request": request})

        with transaction.atomic():
            serializer.is_valid(raise_exception=True)
            purchase = serializer.save()

            terms = purchase.terms.strip().lower() if purchase.terms else ""

            # ✅ CREDIT PURCHASE - Supplier का Cr balance बढ़ाएं
            if terms == "credit":
                if purchase.partyName:
                    purchase.update_balance(purchase.partyName, purchase.grand_total, "Cr")
                else:
                    print(f"   ⚠️ No party assigned to this purchase")

            # 💵 CASH PURCHASE - PCP बनाएं (Supplier balance नहीं बदलेगा)
            elif terms == "cash":
                print("💵 CASH PURCHASE - Creating PCP (Supplier balance unchanged)")

                cash_account = purchase.case_account

                if cash_account and purchase.partyName:
                    # ✅ CHANGE: request.user.branch → get_effective_branch()
                    branch = request.user.get_effective_branch()
                    pcp_voucher = self.generate_cash_payment_voucher(branch)

                    cash = CashPayment.objects.create(
                        date=purchase.date,
                        voucher_no=pcp_voucher,
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
                else:
                    pass

            elif terms == "bank":
                bank_account = purchase.bank_account

                if bank_account and purchase.partyName:
                    # ✅ CHANGE: request.user.branch → get_effective_branch()
                    branch = request.user.get_effective_branch()
                    pbp_voucher = self.generate_bank_payment_voucher(branch)

                    bank = BankPayment.objects.create(
                        date=purchase.date,
                        voucher_no=pbp_voucher,
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
    """List all purchase items with pagination"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"  # ✅ ADD: Frontend route

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        # ✅ CHANGE: Branch selection logic → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ FIX: Employee ko bhi branch_id override allow karo
        # Employee = Mini Superadmin (superadmin branch ke under kaam kar raha hai)
        branch_id_param = request.GET.get('branch_id')
        if branch_id_param:
            # Superadmin hamesha allow
            if is_superadmin or is_employee:
                from pos.models.branch import Branch
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)

        purchases = PurchaseMaster.objects.prefetch_related("items", "partyName").filter(
            branch=branch
        ).order_by('-date', '-id')

        paginator = StandardResultsSetPagination()
        paginated_purchases = paginator.paginate_queryset(purchases, request)

        serializer = PurchaseSerializer(paginated_purchases, many=True)

        return paginator.get_paginated_response(serializer.data)


class PurchaseentryUpdate(APIView):
    """Update a purchase entry"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"  # ✅ ADD: Frontend route

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
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"  # ✅ ADD: Frontend route

    def delete(self, request, id, *args, **kwargs):
        try:
            item = PurchaseItem.objects.get(id=id)
            item.delete()
            return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)
        except PurchaseItem.DoesNotExist:
            return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER/Lookup APIS — NO PERMISSION GATE (only IsAuthenticated)
# ─────────────────────────────────────────────────────────────────────────────

class AccountCheckView(APIView):
    """Check account balance before purchase"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        if not pk:
            return Response({
                "show_alert": False,
                "alert_message": ""
            })

        try:
            account = Account.objects.get(pk=pk)
        except Account.DoesNotExist:
            return Response({"detail": "Account not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = AccountSerializer(account)
        data = serializer.data

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
    """Get all purchase items for dropdown"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        user_branch = request.user.get_effective_branch()
        if not user_branch:
            return Response({"error": "User branch not found"}, status=400)

        variants = itemvariants.objects.filter(
            item__branch=user_branch
        ).select_related("item", "item__unit")

        result = []
        for variant in variants:
            item = variant.item

            unit_name = "-"
            unit_symbol = "pc"
            unit_supports_fractional = False
            if item.unit:
                unit_name = item.unit.name if hasattr(item.unit, 'name') else str(item.unit)
                unit_symbol = item.unit.symbol if hasattr(item.unit, 'symbol') else item.unit.name
                unit_supports_fractional = getattr(item.unit, 'supports_fractional', False)

            purchase_price = variant.purchasePrice or 0

            per_unit_price = purchase_price
            if unit_supports_fractional and variant.opStock and variant.opStock > 0:
                per_unit_price = purchase_price / variant.opStock

            result.append({
                "id": variant.id,
                "itemId": item.id,
                "itemName": item.itemName,
                "hsnCode": item.hsnCode or "",
                "purchasePrice": float(purchase_price),
                "per_unit_price": float(per_unit_price),
                "barcode": variant.barcode or "",
                "size": variant.size or "-",
                "color": variant.color or "-",
                "srno": variant.srno or "-",
                "warrantydate": variant.warrantydate or "-",
                "unit": unit_symbol,
                "unit_name": unit_name,
                "unit_supports_fractional": unit_supports_fractional,
                "taxSlab": item.taxSlab or "0",
                "opStock": float(variant.opStock or 0),
            })

        return Response(result)


class BranchItemsAPIView(APIView):
    """Get all items for a branch (dropdown)"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        user_branch = request.user.get_effective_branch()
        if not user_branch:
            return Response({"detail": "User branch not found"}, status=404)

        items_list = items.objects.filter(
            branch=user_branch
        ).select_related("unit")

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
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_id = request.data.get("item_id")
        party_id = request.data.get("party_id")
        price = to_decimal(request.data.get("price"))
        qty = to_decimal(request.data.get("qty"), Decimal('1'))
        discount_percent = to_decimal(request.data.get("discount_percent"), Decimal('0'))

        # ✅ CHANGE: request.user.branch → get_effective_branch()
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
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        settings_obj = setting.objects.filter(branch=branch).first()
        serializer = SettingSerializers(settings_obj)
        return Response(serializer.data)

    def post(self, request):
        gst_toggle = request.data.get("gst_toggle")

        if gst_toggle is None:
            return Response(
                {"error": "gst_toggle is required"},
                status=400
            )

        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        setting_obj = (
            setting.objects
            .filter(branch=branch)
            .order_by("-id")
            .first()
        )

        if not setting_obj:
            setting_obj = setting.objects.create(
                branch=branch,
                gst_toggle=gst_toggle
            )
        else:
            setting_obj.gst_toggle = gst_toggle
            setting_obj.save()

        return Response({
            "gst_toggle": gst_toggle
        }, status=200)


class PurchaseItemSearchAPIView(APIView):
    """Search purchase items"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        search = request.GET.get("query", "").strip()
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        user_branch = request.user.get_effective_branch()
        if not user_branch:
            return Response({"error": "User branch not found"}, status=400)

        variants_qs = itemvariants.objects.filter(
            item__branch=user_branch
        ).select_related("item", "item__unit").distinct()

        if search:
            variants_qs = variants_qs.filter(
                Q(item__itemName__icontains=search) |
                Q(item__hsnCode__icontains=search) |
                Q(purchasePrice__icontains=search) |
                Q(size__icontains=search) |
                Q(color__icontains=search) |
                Q(barcode__icontains=search) |
                Q(srno__icontains=search)
            ).distinct()

        result = []
        for variant in variants_qs:
            item = variant.item

            unit_name = "-"
            unit_symbol = "pc"
            unit_supports_fractional = False
            if item.unit:
                unit_name = item.unit.name if hasattr(item.unit, 'name') else str(item.unit)
                unit_symbol = item.unit.symbol if hasattr(item.unit, 'symbol') else item.unit.name
                unit_supports_fractional = getattr(item.unit, 'supports_fractional', False)

            purchase_price = variant.purchasePrice or 0

            per_unit_price = purchase_price
            if unit_supports_fractional and variant.opStock and variant.opStock > 0:
                per_unit_price = purchase_price / variant.opStock

            result.append({
                "id": variant.id,
                "itemId": item.id,
                "itemName": item.itemName,
                "hsnCode": item.hsnCode or "",
                "purchasePrice": float(purchase_price),
                "per_unit_price": float(per_unit_price),
                "barcode": variant.barcode or "",
                "size": variant.size or "-",
                "color": variant.color or "-",
                "srno": variant.srno or "-",
                "warrantydate": variant.warrantydate or "-",
                "unit": unit_symbol,
                "unit_name": unit_name,
                "unit_supports_fractional": unit_supports_fractional,
                "taxSlab": item.taxSlab or "0",
                "opStock": float(variant.opStock or 0),
            })

        return Response(result)


class PurchaseCreditBillsAPIView(APIView):
    """Get purchase credit bills with pending amount"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Q, Sum
        from decimal import Decimal
        from pos.models.purchasereturn import PurchaseReturnMaster

        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"error": "No branch linked to this user"}, status=400)

        search = request.GET.get('query', '').strip()

        bills = PurchaseMaster.objects.filter(
            branch=branch,
            terms__iexact='credit'
        )

        if search:
            bills = bills.filter(
                Q(billNo__icontains=search) |
                Q(partyName__account_name__icontains=search)
            )

        bills_data = []

        for bill in bills:
            total_paid = CashPayment.objects.filter(
                purchase=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            total_paid += BankPayment.objects.filter(
                purchase=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            all_returns = PurchaseReturnMaster.objects.filter(
                branch=branch,
                original_bill_no=bill.billNo,
            )
            total_all_returned = all_returns.aggregate(
                total=Sum('grand_total')
            )['total'] or Decimal('0')

            credit_returns_unsettled = Decimal('0')

            for pr in all_returns.filter(payment_terms__iexact='credit'):
                pr_receipts = CashReceipt.objects.filter(
                    purchase_return=pr
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                pr_receipts += BankReceipt.objects.filter(
                    purchase_return=pr
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                if pr_receipts >= pr.grand_total:
                    print(f"  PR {pr.return_no}: Fully received ₹{pr_receipts} → Won't reduce pending")
                else:
                    unsettled = pr.grand_total - pr_receipts
                    credit_returns_unsettled += unsettled
                    print(f"  PR {pr.return_no}: Unsettled ₹{unsettled} (Grand: ₹{pr.grand_total}, Received: ₹{pr_receipts})")

            pending_amount = bill.grand_total - total_paid - credit_returns_unsettled

            print(f"📋 PI {bill.billNo}: Grand={bill.grand_total}, Paid={total_paid}, UnsettledCreditReturns={credit_returns_unsettled}, Pending={pending_amount}")

            if pending_amount > Decimal('0.005'):
                bills_data.append({
                    'id': bill.id,
                    'billNo': bill.billNo,
                    'originalBillNo': bill.billNo,
                    'partyName__account_name': bill.partyName.account_name,
                    'party_id': bill.partyName.id,
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
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data
        purchase_bill_id = data.get('purchase_bill_id')
        cash_account_id = data.get('cash_account')
        amount = Decimal(str(data.get('amount', 0)))

        # ✅ CHANGE: request.user.branch → get_effective_branch()
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

            pcp_voucher = self.generate_cash_payment_voucher(branch)

            cash_payment = CashPayment.objects.create(
                date=data['date'],
                voucher_no=pcp_voucher,
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

            print(f"✅ PCP CREATED: {cash_payment.id} - Voucher: {pcp_voucher}")

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

    def generate_cash_payment_voucher(self, branch):
        from datetime import datetime
        from pos.models.settings import setting

        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CP", "CP") if settings_obj else "CP"

        last_voucher = CashPayment.objects.filter(branch=branch).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                parts = last_voucher.voucher_no.split("/")
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0

        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year

        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{prefix}/{fy}/{next_no}"

        return voucher_no


class PayPurchaseCreditBillBankAPIView(APIView):
    """Pay a purchase credit bill via bank payment (creates PBP)"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data
        purchase_bill_id = data.get('purchase_bill_id')
        bank_account_id = data.get('bank_account')
        amount = Decimal(str(data.get('amount', 0)))
        mode = data.get('mode', 'UPI')

        # ✅ CHANGE: request.user.branch → get_effective_branch()
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

            pbp_voucher = self.generate_bank_payment_voucher(branch)

            bank_payment = BankPayment.objects.create(
                date=data['date'],
                voucher_no=pbp_voucher,
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

            print(f" PBP CREATED: {bank_payment.id} - Voucher: {pbp_voucher} - Type: {bank_payment.type}")

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

    def generate_cash_payment_voucher(self, branch):
        """Generate voucher number for Cash Payments (CP and PCP share same sequence)"""
        from datetime import datetime
        from pos.models.settings import setting
        from pos.models.cashpayment import CashPayment
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CP", "CP") if settings_obj else "CP"
        
        last_voucher = CashPayment.objects.filter(
            branch=branch
        ).order_by("-id").first()
        
        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                parts = last_voucher.voucher_no.split("/")
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0
        
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year
        
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{prefix}/{fy}/{next_no}"
        
        return voucher_no
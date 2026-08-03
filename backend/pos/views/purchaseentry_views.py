#pos/views/purchaseentry_views.py
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
from pos.models.items import items,itemvariants
from pos.models.purchaseentry import PurchaseItem, PurchaseMaster
from pos.serializers.account_serializer import AccountSerializer
from decimal import Decimal, InvalidOperation   
from pos.serializers.settings_serializers import SettingSerializers
from pos.serializers.purchaseentry_serializers import (
    ItemSerializer,
    PurchaseSerializer,
)   
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment 
from pos.utils.pagination import StandardResultsSetPagination

#  ADD THIS FUNCTION
def to_decimal(value, default=Decimal("0.00")):
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value).replace("%", "").strip())
    except (InvalidOperation, ValueError):
        return default
class PurchaseCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def generate_bank_payment_voucher(self, branch):
        """
        Generate voucher number for Bank Payments (BP and PBP share same sequence)
        Uses BP prefix from settings
        """
        from datetime import datetime
        from pos.models.settings import setting
        from pos.models.bankpayment import BankPayment
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BP", "BP") if settings_obj else "BP"
        
        # Get the last voucher number from ALL bank payments (both BP and PBP)
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
        """
        Generate voucher number for Cash Payments (CP and PCP share same sequence)
        Uses CP prefix from settings
        """
        from datetime import datetime
        from pos.models.settings import setting
        from pos.models.cashpayment import CashPayment
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CP", "CP") if settings_obj else "CP"
        
        # Get the last voucher number from ALL cash payments (both CP and PCP)
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
        serializer = PurchaseSerializer(data=request.data, context={"request": request})

        with transaction.atomic():
            serializer.is_valid(raise_exception=True)
            purchase = serializer.save()

            terms = purchase.terms.strip().lower() if purchase.terms else ""

            
            # ✅ CREDIT PURCHASE - Supplier का Cr balance बढ़ाएं
            if terms == "credit":

                
                if purchase.partyName:
                    # Supplier का Cr balance बढ़ता है (हमें Supplier को पैसा देना है)
                    purchase.update_balance(purchase.partyName, purchase.grand_total, "Cr")

                else:
                    print(f"   ⚠️ No party assigned to this purchase")

            # 💵 CASH PURCHASE - PCP बनाएं (Supplier balance नहीं बदलेगा)
            elif terms == "cash":
                print("💵 CASH PURCHASE - Creating PCP (Supplier balance unchanged)")

                cash_account = purchase.case_account

                if cash_account and purchase.partyName:
                    pcp_voucher = self.generate_cash_payment_voucher(request.user.branch)

                    cash = CashPayment.objects.create(
                        date=purchase.date,
                        voucher_no=pcp_voucher,
                        cash_account=cash_account,
                        op_account=purchase.partyName,
                        branch=request.user.branch,
                        amount=purchase.grand_total,
                        mode="Cash",
                        narration=f"Auto payment against Purchase {purchase.billNo}",
                        type="PCP",
                        purchase=purchase  # ✅ IMPORTANT: Link to purchase
                    )

                else:
                 pass

            # 🏦 BANK PURCHASE - PBP बनाएं (Supplier balance नहीं बदलेगा)
            elif terms == "bank":
              

                bank_account = purchase.bank_account

                if bank_account and purchase.partyName:
                    pbp_voucher = self.generate_bank_payment_voucher(request.user.branch)

                    bank = BankPayment.objects.create(
                        date=purchase.date,
                        voucher_no=pbp_voucher,
                        bank_account=bank_account,
                        op_account=purchase.partyName,
                        branch=request.user.branch,
                        amount=purchase.grand_total,
                        mode="Auto",
                        narration=f"Auto payment against Purchase {purchase.billNo}",
                        type="PBP",
                        purchase=purchase  # ✅ IMPORTANT: Link to purchase
                    )

        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
class AccountCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk=None):
        """
        If pk is provided, check that account.
        If pk is None (no account selected, e.g., credit terms), only return bank/cash alerts.
        """
        # If no PK given, just return empty alert (for credit with no account)
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

        # ✅ SIRF BANK ACCOUNT AUR CASE IN HAND KE LIYE BALANCE CHECK
        if account.group in ["Bank Account", "Case In Hand"] and account.current_balance == 0:
            show_alert = True
            alert_message = "⚠ Current balance is 0. Purchase not allowed."

        #  PARTY ACCOUNT KA CHECK HATANA HAI - ISLIYE YEH PURA BLOCK DELETE KARO
        # elif account.group == "Party" and "transaction_type" in request.GET:
        #     trx_type = request.GET.get("transaction_type")
        #     dr_amount = float(request.GET.get("dr_amount", 0))
        #
        #     if trx_type == "DR" and dr_amount > account.current_balance:
        #         show_alert = True
        #         alert_message = " DR amount exceeds party balance."

        data["show_alert"] = show_alert
        data["alert_message"] = alert_message

        return Response(data)

class PurchaseItemListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        # ✅ Branch selection logic
        if is_superadmin:
            branch_id_param = request.GET.get('branch_id')
            if branch_id_param:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
            else:
                try:
                    branch = Branch.objects.get(user=user)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=400)
        else:
            branch = getattr(user, 'branch', None)
            if not branch:
                return Response({"detail": "User does not have a branch assigned."}, status=400)

        # ✅ ORDER BY add kiya for consistent ordering
        purchases = PurchaseMaster.objects.prefetch_related("items", "partyName").filter(
            branch=branch
        ).order_by('-date', '-id')  # Latest first
        
        # ✅ PAGINATION ADD KARO
        paginator = StandardResultsSetPagination()
        paginated_purchases = paginator.paginate_queryset(purchases, request)
        
        serializer = PurchaseSerializer(paginated_purchases, many=True)
        
        # ✅ Paginated response return karo
        return paginator.get_paginated_response(serializer.data)

class PurchaseItemDelete(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, id, *args, **kwargs):  # <-- accept id here
        try:
            item = PurchaseItem.objects.get(id=id)
            item.delete()
            return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)
        except PurchaseItem.DoesNotExist:
            return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)


class PurchaseItemListAllAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_branch = request.user.branch
        
        if not user_branch:
            return Response({"error": "User branch not found"}, status=400)

        variants = itemvariants.objects.filter(
            item__branch=user_branch
        ).select_related("item", "item__unit")

        result = []
        for variant in variants:
            item = variant.item
            
            # ✅ Get unit with fractional support
            unit_name = "-"
            unit_symbol = "pc"
            unit_supports_fractional = False
            if item.unit:
                unit_name = item.unit.name if hasattr(item.unit, 'name') else str(item.unit)
                unit_symbol = item.unit.symbol if hasattr(item.unit, 'symbol') else item.unit.name
                unit_supports_fractional = getattr(item.unit, 'supports_fractional', False)
            
            purchase_price = variant.purchasePrice or 0
            
            # ✅ Calculate per-unit price
            per_unit_price = purchase_price
            if unit_supports_fractional and variant.opStock and variant.opStock > 0:
                per_unit_price = purchase_price / variant.opStock
            
            result.append({
                "id": variant.id,
                "itemId": item.id,
                "itemName": item.itemName,
                "hsnCode": item.hsnCode or "",
                "purchasePrice": float(purchase_price),
                "per_unit_price": float(per_unit_price),  # ✅ ADD
                "barcode": variant.barcode or "",
                "size": variant.size or "-",
                "color": variant.color or "-",
                "srno": variant.srno or "-",
                "warrantydate": variant.warrantydate or "-",
                "unit": unit_symbol,
                "unit_name": unit_name,
                "unit_supports_fractional": unit_supports_fractional,  # ✅ ADD
                "taxSlab": item.taxSlab or "0",
                "opStock": float(variant.opStock or 0),
            })

        return Response(result)
class PurchaseentryUpdate(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, id):
        try:
            entry = PurchaseMaster.objects.get(id=id)
        except PurchaseMaster.DoesNotExist:
            return Response({"error": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PurchaseSerializer(entry, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, id):
        try:
            entry = PurchaseMaster.objects.get(id=id)
        except PurchaseMaster.DoesNotExist:
            return Response({"error": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PurchaseSerializer(entry, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class BranchItemsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        
        user_branch = request.user.branch
        
        if not user_branch:
            return Response({"detail": "User branch not found"}, status=404)
        
        items_list = items.objects.filter(
            branch=user_branch  # <-- Single branch only
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

# pos/views/purchaseentry_views.py - Corrected PurchaseItemTaxAPIView

from decimal import Decimal, ROUND_HALF_UP

class PurchaseItemTaxAPIView(APIView):  
    """
    GST calculation with discount support:
    
    ON MODE (gst_toggle = True):
        - Price is BASIC price
        - GST = (Basic × Tax%) / 100
        - Net = Basic + GST
    
    OFF MODE (gst_toggle = False):
        - Price is NET price (includes GST)
        - GST = (Net × Tax%) / 100
        - Basic = Net - GST
    """

    def post(self, request):
        item_id = request.data.get("item_id")
        party_id = request.data.get("party_id")
        price = to_decimal(request.data.get("price"))
        qty = to_decimal(request.data.get("qty"), Decimal('1'))
        discount_percent = to_decimal(request.data.get("discount_percent"), Decimal('0'))
        
        # Get GST toggle from settings
        settings_obj = setting.objects.filter(branch=request.user.branch).first()
        gst_toggle = getattr(settings_obj, 'gst_toggle', True)

        if not item_id:
            return Response({"error": "item_id is required"}, status=400)
        if not party_id:
            return Response({"error": "party_id is required"}, status=400)

        # Fetch item and party
        try:
            item = items.objects.select_related("branch").get(id=item_id)
        except items.DoesNotExist:
            return Response({"error": "Item not found"}, status=404)

        try:
            party = Account.objects.get(id=party_id)
        except Account.DoesNotExist:
            return Response({"error": "Party not found"}, status=404)

        tax_percent = to_decimal(item.taxSlab)
        
        # Step 1: Calculate total price (price × qty)
        total_price = (price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Step 2: Apply discount on total_price
        discount_amount = (total_price * discount_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        amount_after_discount = (total_price - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Step 3: Calculate GST based on toggle
        cgst = sgst = igst = total_tax = Decimal('0.00')
        basic_amount = Decimal('0.00')
        net_amount = Decimal('0.00')
        
        branch_state = item.branch.state or ""
        party_state = party.state or ""

        if tax_percent > 0:
            if gst_toggle:
                # 🔥 ON MODE: Price is BASIC, Add GST on top
                # Formula: GST = (Basic × Tax%) / 100
                total_tax = (amount_after_discount * tax_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                basic_amount = amount_after_discount
                net_amount = (basic_amount + total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                # 🔥 OFF MODE: Price is NET (includes GST)
                # Formula: GST = (Net × Tax%) / 100
                # Basic = Net - GST
                total_tax = (amount_after_discount * tax_percent / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                net_amount = amount_after_discount
                basic_amount = (net_amount - total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # GST Split based on state
            if branch_state == party_state:
                half_tax = (total_tax / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                cgst = half_tax
                sgst = half_tax
                # Adjust for rounding difference
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
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        settings = setting.objects.first()  # your singleton settings
        serializer = SettingSerializers(settings)
        return Response(serializer.data)

    def post(self, request):
        gst_toggle = request.data.get("gst_toggle")

        if gst_toggle is None:
            return Response(
                {"error": "gst_toggle is required"},
                status=400
            )

        setting_obj = (
            setting.objects
            .filter(branch=request.user.branch)
            .order_by("-id")
            .first()
        )

        if not setting_obj:
            setting_obj = setting.objects.create(
                branch=request.user.branch,
                gst_toggle=gst_toggle
            )
        else:
            setting_obj.gst_toggle = gst_toggle
            setting_obj.save()

        return Response({
            "gst_toggle": gst_toggle
        }, status=200)


# pos/views/purchaseentry_views.py - Update PurchaseItemSearchAPIView

# pos/views/purchaseentry_views.py

class PurchaseItemSearchAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        search = request.GET.get("query", "").strip()
        user_branch = request.user.branch
        
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
            
            # ✅ Get unit with fractional support
            unit_name = "-"
            unit_symbol = "pc"
            unit_supports_fractional = False
            if item.unit:
                unit_name = item.unit.name if hasattr(item.unit, 'name') else str(item.unit)
                unit_symbol = item.unit.symbol if hasattr(item.unit, 'symbol') else item.unit.name
                unit_supports_fractional = getattr(item.unit, 'supports_fractional', False)
            
            purchase_price = variant.purchasePrice or 0
            
            # ✅ Calculate per-unit price for fractional units
            per_unit_price = purchase_price
            if unit_supports_fractional and variant.opStock and variant.opStock > 0:
                per_unit_price = purchase_price / variant.opStock
            
            result.append({
                "id": variant.id,
                "itemId": item.id,
                "itemName": item.itemName,
                "hsnCode": item.hsnCode or "",
                "purchasePrice": float(purchase_price),
                "per_unit_price": float(per_unit_price),  # ✅ ADD THIS
                "barcode": variant.barcode or "",
                "size": variant.size or "-",
                "color": variant.color or "-",
                "srno": variant.srno or "-",
                "warrantydate": variant.warrantydate or "-",
                "unit": unit_symbol,
                "unit_name": unit_name,
                "unit_supports_fractional": unit_supports_fractional,  # ✅ ADD THIS
                "taxSlab": item.taxSlab or "0",
                "opStock": float(variant.opStock or 0),  # ✅ ADD THIS
            })
            
        return Response(result)
    
class PurchaseCreditBillsAPIView(APIView):
    """Get purchase credit bills with pending amount.
    
    🔥 LOGIC:
    - PCP/PBP payments reduce pending
    - Credit Returns jinka PRCR/PRBR receipt liya gaya → DON'T reduce pending
    - Credit Returns jinka koi receipt nahi liya → REDUCE pending (auto-adjusted)
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        from django.db.models import Q, Sum
        from decimal import Decimal
        from pos.models.purchasereturn import PurchaseReturnMaster
 
        search = request.GET.get('query', '').strip()
 
        bills = PurchaseMaster.objects.filter(
            branch=request.user.branch,
            terms__iexact='credit'
        )
 
        if search:
            bills = bills.filter(
                Q(billNo__icontains=search) |
                Q(partyName__account_name__icontains=search)
            )
 
        bills_data = []
 
        for bill in bills:
            # Payments already made (PCP/PBP)
            total_paid = CashPayment.objects.filter(
                purchase=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
 
            total_paid += BankPayment.objects.filter(
                purchase=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
 
            # ALL returns for display
            all_returns = PurchaseReturnMaster.objects.filter(
                branch=request.user.branch,
                original_bill_no=bill.billNo,
            )
            total_all_returned = all_returns.aggregate(
                total=Sum('grand_total')
            )['total'] or Decimal('0')
            
            # 🔥 Credit Returns jo ABHI TAK settled nahi hue
            # Settled = jinka PRCR/PRBR receipt liya ja chuka hai
            credit_returns_unsettled = Decimal('0')
            
            for pr in all_returns.filter(payment_terms__iexact='credit'):
                # Check PRCR/PRBR receipts against this return
                pr_receipts = CashReceipt.objects.filter(
                    purchase_return=pr
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                
                pr_receipts += BankReceipt.objects.filter(
                    purchase_return=pr
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                
                if pr_receipts >= pr.grand_total:
                    # Fully received → Settled, DON'T reduce pending
                    print(f"  PR {pr.return_no}: Fully received ₹{pr_receipts} → Won't reduce pending")
                else:
                    # Not received or partially received → Pending return
                    unsettled = pr.grand_total - pr_receipts
                    credit_returns_unsettled += unsettled
                    print(f"  PR {pr.return_no}: Unsettled ₹{unsettled} (Grand: ₹{pr.grand_total}, Received: ₹{pr_receipts})")
            
            # 🔥 Pending = Grand - Paid - Unsettled Credit Returns
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
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        data = request.data
        purchase_bill_id = data.get('purchase_bill_id')
        cash_account_id = data.get('cash_account')
        amount = Decimal(str(data.get('amount', 0)))
        
        try:
            # Get the purchase bill
            purchase_bill = PurchaseMaster.objects.get(
                id=purchase_bill_id,
                branch=request.user.branch
            )
            
            # Check if it's a credit bill
            if purchase_bill.terms.lower() != 'credit':
                return Response({'error': 'This bill is not a credit bill'}, status=400)
            
            # Create cash payment against this bill
            pcp_voucher = self.generate_cash_payment_voucher(request.user.branch)
            
            cash_payment = CashPayment.objects.create(
                date=data['date'],
                voucher_no=pcp_voucher,
                cash_account_id=cash_account_id,
                op_account_id=purchase_bill.partyName.id,
                branch=request.user.branch,
                amount=amount,
                mode="Cash",
                narration=f"Payment against purchase credit bill {purchase_bill.billNo}",
                type="PCP",
                purchase=purchase_bill
            )
            
            print(f" PCP CREATED: {cash_payment.id} - Voucher: {pcp_voucher}")
            
             
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
        """Generate voucher number for PCP"""
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
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        data = request.data
        purchase_bill_id = data.get('purchase_bill_id')
        bank_account_id = data.get('bank_account')
        amount = Decimal(str(data.get('amount', 0)))
        mode = data.get('mode', 'UPI')
        
        try:
            # Get the purchase bill
            purchase_bill = PurchaseMaster.objects.get(
                id=purchase_bill_id,
                branch=request.user.branch
            )
            
            # Check if it's a credit bill
            if purchase_bill.terms.lower() != 'credit':
                return Response({'error': 'This bill is not a credit bill'}, status=400)
            
            # Create bank payment against this bill
            pbp_voucher = self.generate_bank_payment_voucher(request.user.branch)
            
            # ✅ Ensure type is set to "PBP"
            bank_payment = BankPayment.objects.create(
                date=data['date'],
                voucher_no=pbp_voucher,
                bank_account_id=bank_account_id,
                op_account_id=purchase_bill.partyName.id,
                branch=request.user.branch,
                amount=amount,
                mode=mode,
                cheque_no=data.get('cheque_no'),
                cheque_date=data.get('cheque_date'),
                cheque_clear_date=data.get('cheque_clear_date'),
                narration=f"Payment against purchase credit bill {purchase_bill.billNo}",
                type="PBP",  # ✅ Explicitly set to PBP
                purchase=purchase_bill
            )
            
            print(f"✅ PBP CREATED: {bank_payment.id} - Voucher: {pbp_voucher} - Type: {bank_payment.type}")
            
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
    
    def generate_bank_payment_voucher(self, branch):
        """Generate voucher number for PBP"""
        from datetime import datetime
        from pos.models.settings import setting
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BP", "BP") if settings_obj else "BP"
        
        # ✅ Get the last voucher number from ALL bank payments (BP, PBP, SRBP share same sequence)
        last_voucher = BankPayment.objects.filter(branch=branch).order_by("-id").first()
        
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
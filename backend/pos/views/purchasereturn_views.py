# pos/views/purchasereturn_views.py

from pos.models.bankpayment import BankPayment
from pos.models.cashpayment import CashPayment
from pos.utils.pagination import StandardResultsSetPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from decimal import Decimal
from urllib.parse import unquote

from pos.models.purchasereturn import PurchaseReturnMaster, PurchaseReturnItem
from pos.models.purchaseentry import PurchaseMaster, PurchaseItem
from pos.models.items import items, itemvariants
from pos.serializers.purchasereturn_serializers import PurchaseReturnMasterSerializer
from pos.models.cashreceipt import CashReceipt
from pos.models.bankreceipt import BankReceipt
from pos.models.settings import setting

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class PurchaseReturnCreateAPIView(APIView):
    """Create Purchase Return with stock update (decreases stock) and payment receipt"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/purchaseReturnList"  # ✅ ADD: Frontend route
    
    def generate_cash_receipt_voucher(self, branch):
        from datetime import datetime
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CR", "CR") if settings_obj else "CR"

        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"

        last_voucher = CashReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        while CashReceipt.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        print(f"🎫 PRCR Voucher: {voucher_no} - Branch: {branch.branch_name}")
        return voucher_no

    def generate_bank_receipt_voucher(self, branch):
        from datetime import datetime
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BR", "BR") if settings_obj else "BR"

        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"

        last_voucher = BankReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        while BankReceipt.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        print(f"🎫 PRBR Voucher: {voucher_no} - Branch: {branch.branch_name}")
        return voucher_no

    @transaction.atomic
    def post(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        data = request.data
        items_data = data.get('items', [])
        payment_terms = data.get('payment_terms', 'Credit').lower()

        if not items_data:
            return Response({"error": "At least one item is required"}, status=400)

        try:
            purchase_return = PurchaseReturnMaster.objects.create(
                branch=branch,
                date=data['date'],
                original_bill_no=data['original_bill_no'],
                party_id=data['party'],
                reason_for_return=data['reason_for_return'],
                approved_by=data['approved_by'],
                return_type=data['return_type'],
                return_status=data.get('return_status', 'Pending'),
                payment_terms=payment_terms,
                cash_account_id=data.get('cash_account') if payment_terms == 'cash' else None,
                bank_account_id=data.get('bank_account') if payment_terms == 'bank' else None,
                total_basic=Decimal(str(data.get('total_basic', 0))),
                total_tax=Decimal(str(data.get('total_tax', 0))),
                grand_total=Decimal(str(data.get('grand_total', 0))),
                narration=data.get('narration', ''),
                created_by=request.user, 
            )
            print(f" Purchase Return created: {purchase_return.return_no}")

        except IntegrityError as e:
            print(f"❌ IntegrityError creating purchase return: {e}")
            return Response(
                {"error": "Return number conflict. Please try again."},
                status=status.HTTP_409_CONFLICT
            )

        # CREDIT RETURN: Supplier balance update
        if payment_terms == 'credit':
            from pos.models.account import Account
            from pos.models.salesentry import SalesMaster

            supplier = Account.objects.select_for_update().get(pk=purchase_return.party.pk)

            print(f" Credit PR - Supplier: {supplier.account_name} | "
                f"Balance: {supplier.current_balance} {supplier.current_drcr} | "
                f"Return: ₹{purchase_return.grand_total}")

            SalesMaster.update_balance(supplier, purchase_return.grand_total, "Dr")

            print(f" After PR - Supplier: {supplier.current_balance} {supplier.current_drcr}")

        alert_messages = []
        
        # Process items and update stock
        for it in items_data:
            qty = Decimal(str(it.get('return_quantity', 0)))
            variant_raw = it.get('variant_id')
            purchase_item_id = it.get('purchase_item_id')
            
            if purchase_item_id:
                try:
                    purchase_item = PurchaseItem.objects.get(id=purchase_item_id)
                    already_returned = PurchaseReturnItem.objects.filter(
                        purchase_item=purchase_item
                    ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')
                    max_returnable = purchase_item.quantity - already_returned
                    
                    if qty > max_returnable:
                        alert_messages.append(
                            f"⚠ {purchase_item.itemName.itemName} - "
                            f"Can only return {max_returnable} (already returned {already_returned})"
                        )
                        continue
                except PurchaseItem.DoesNotExist:
                    pass
            
            # Update stock - Purchase Return DECREASES stock
            if variant_raw not in [None, "", "null"]:
                try:
                    variant = itemvariants.objects.select_for_update().get(id=int(variant_raw))
                    if variant.current_stock < qty:
                        alert_messages.append(f"⚠ {variant.item.itemName} - Insufficient stock! Available: {variant.current_stock}, Returning: {qty}")
                    variant.current_stock -= qty
                    variant.save()
                except itemvariants.DoesNotExist:
                    pass
            else:
                try:
                    item_obj = items.objects.select_for_update().get(id=it['item_id'])
                    if item_obj.current_stock < qty:
                        alert_messages.append(f"⚠ {item_obj.itemName} - Insufficient stock! Available: {item_obj.current_stock}, Returning: {qty}")
                    item_obj.current_stock -= qty
                    item_obj.save()
                except items.DoesNotExist:
                    pass
            
            # Create Purchase Return Item
            PurchaseReturnItem.objects.create(
                purchase_return=purchase_return,
                purchase_item_id=purchase_item_id,
                item_id=it['item_id'],
                variant_id=int(variant_raw) if variant_raw not in [None, "", "null"] else None,
                hsn_code=it.get('hsn_code', ''),
                batch_no=it.get('batch_no', ''),
                return_quantity=qty,
                price=Decimal(str(it.get('price', 0))),
                discount_percent=Decimal(str(it.get('discount_percent', 0))),
                tax_percent=Decimal(str(it.get('tax_percent', 0))),
                basic_amount=Decimal(str(it.get('basic_amount', 0))),
                discount_amount=Decimal(str(it.get('discount_amount', 0))),
                tax_amount=Decimal(str(it.get('tax_amount', 0))),
                net_amount=Decimal(str(it.get('net_amount', 0))),
                cgst=Decimal(str(it.get('cgst', 0))),
                sgst=Decimal(str(it.get('sgst', 0))),
                igst=Decimal(str(it.get('igst', 0))),
            )
        
        # Create Receipt for Cash or Bank payments
        if payment_terms == "cash":
            cash_account = data.get('cash_account')
            if cash_account and data.get('party'):
                prcr_voucher = self.generate_cash_receipt_voucher(branch)
                
                cash_receipt = CashReceipt.objects.create(
                    date=data['date'],
                    voucher_no=prcr_voucher,
                    cash_account_id=cash_account,
                    op_account_id=data['party'],
                    branch=branch,
                    amount=purchase_return.grand_total,
                    narration=f"Auto receipt against Purchase Return {purchase_return.return_no}",
                    type="PRCR",
                    purchase_return=purchase_return,
                    created_by=request.user, 
                )
                print(f" PRCR CREATED: {cash_receipt.id} - Voucher: {prcr_voucher}")
        
        elif payment_terms == "bank":
            bank_account = data.get('bank_account')
            if bank_account and data.get('party'):
                prbr_voucher = self.generate_bank_receipt_voucher(branch)
                
                bank_receipt = BankReceipt.objects.create(
                    date=data['date'],
                    voucher_no=prbr_voucher,
                    bank_account_id=bank_account,
                    op_account_id=data['party'],
                    branch=branch,
                    amount=purchase_return.grand_total,
                    mode="Auto",
                    narration=f"Auto receipt against Purchase Return {purchase_return.return_no}",
                    type="PRBR",
                    purchase_return=purchase_return,
                    created_by=request.user,
                )
                print(f"✅ PRBR CREATED: {bank_receipt.id} - Voucher: {prbr_voucher}")
        
        response = {
            "message": "Purchase Return Created Successfully",
            "id": purchase_return.id,
            "return_no": purchase_return.return_no,
        }
        
        if alert_messages:
            response["stock_alerts"] = alert_messages
        
        return Response(response, status=201)


class PurchaseReturnListAPIView(APIView):
    """List all purchase returns"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/purchaseReturnList"  # ✅ ADD: Frontend route
    
    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        # ✅ CHANGE: Branch selection logic → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
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

        queryset = PurchaseReturnMaster.objects.filter(
            branch=branch
        ).order_by('-date', '-created_at')

        paginator = StandardResultsSetPagination()
        paginated_qs = paginator.paginate_queryset(queryset, request)

        serializer = PurchaseReturnMasterSerializer(paginated_qs, many=True)
        return paginator.get_paginated_response(serializer.data)
    

class PurchaseReturnDetailAPIView(APIView):
    """Get single purchase return details"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/purchaseReturnList"  # ✅ ADD: Frontend route
    
    def get(self, request, return_id):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            purchase_return = PurchaseReturnMaster.objects.get(
                id=return_id,
                branch=branch
            )
            serializer = PurchaseReturnMasterSerializer(purchase_return)
            return Response(serializer.data)
        except PurchaseReturnMaster.DoesNotExist:
            return Response({"error": "Purchase Return not found"}, status=404)


class PurchaseReturnDeleteAPIView(APIView):
    """Delete a purchase return"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/purchaseReturnList"  # ✅ ADD: Frontend route
    
    @transaction.atomic
    def delete(self, request, return_id):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            purchase_return = PurchaseReturnMaster.objects.get(
                id=return_id,
                branch=branch
            )
            
            # Reverse stock updates (add stock back)
            for item in purchase_return.items.all():
                qty = item.return_quantity
                if item.variant:
                    variant = item.variant
                    variant.current_stock += qty
                    variant.save()
                else:
                    item_obj = item.item
                    item_obj.current_stock += qty
                    item_obj.save()
            
            # Delete associated receipts
            CashReceipt.objects.filter(purchase_return=purchase_return).delete()
            BankReceipt.objects.filter(purchase_return=purchase_return).delete()
            
            purchase_return.delete()
            return Response({"message": "Purchase Return deleted successfully"}, status=204)
        except PurchaseReturnMaster.DoesNotExist:
            return Response({"error": "Purchase Return not found"}, status=404)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER APIS — No permission gate (only IsAuthenticated)
# ─────────────────────────────────────────────────────────────────────────────

class PurchaseBillDetailsAPIView(APIView):
    """Get purchase bill details with all items"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request, bill_no):
        from urllib.parse import unquote
        from django.db.models import Sum
        from decimal import Decimal
        from pos.models.purchasereturn import PurchaseReturnMaster
        from pos.models.cashpayment import CashPayment
        from pos.models.bankpayment import BankPayment

        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        bill_no_decoded = unquote(bill_no)
        return_type = request.GET.get('return_type', 'Partial')

        try:
            purchases = PurchaseMaster.objects.filter(
                billNo=bill_no_decoded,
                branch=branch
            )

            if not purchases.exists():
                return Response(
                    {'error': f'Purchase bill not found: {bill_no_decoded}'},
                    status=status.HTTP_404_NOT_FOUND
                )

            purchase = purchases.order_by('-id').first()

            purchase_items = PurchaseItem.objects.filter(
                purchase=purchase
            ).select_related('itemName', 'variant')

            items_data = []

            for p_item in purchase_items:
                already_returned = PurchaseReturnItem.objects.filter(
                    purchase_item=p_item
                ).aggregate(total_returned=Sum('return_quantity'))['total_returned'] or Decimal('0')

                available_quantity = float(p_item.quantity) - float(already_returned)

                if available_quantity <= 0:
                    continue

                tax_slab = p_item.itemName.taxSlab or "0"
                try:
                    tax_percent = float(str(tax_slab).replace('%', '').strip())
                except ValueError:
                    tax_percent = 0.0

                default_return_qty = available_quantity if return_type == 'Full' else 0

                items_data.append({
                    'id': p_item.id,
                    'item_id': p_item.itemName.id,
                    'purchase_item_id': p_item.id,
                    'item_name': p_item.itemName.itemName,
                    'variant_id': p_item.variant.id if p_item.variant else None,
                    'hsn_code': p_item.hsnCode or '',
                    'quantity': float(p_item.quantity),
                    'already_returned': float(already_returned),
                    'available_quantity': available_quantity,
                    'default_return_quantity': default_return_qty,
                    'price': float(p_item.price),
                    'unit': p_item.per or 'Pcs',
                    'tax_percent': tax_percent,
                    'basic_amount': float(p_item.basicAmount or 0),
                    'tax_amount': float(p_item.taxAmount or 0),
                    'net_amount': float(p_item.netValue or 0),
                })

            if not items_data:
                return Response(
                    {'error': 'All items from this bill have already been returned',
                     'fully_returned': True},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Payment History
            payment_history = []
            total_paid = Decimal('0')
            total_returned = Decimal('0')

            # Purchase Entry
            payment_history.append({
                'entry_type': 'Purchase',
                'type': 'BILL',
                'voucher_no': purchase.billNo,
                'date': purchase.date.strftime('%Y-%m-%d'),
                'amount': float(purchase.grand_total),
                'mode': purchase.terms or 'Credit',
                'narration': f'Purchase Bill - {purchase.partyName.account_name}',
            })

            # Cash Payments
            for cp in CashPayment.objects.filter(purchase=purchase).order_by('date'):
                payment_history.append({
                    'entry_type': 'Payment',
                    'type': cp.type,
                    'voucher_no': cp.voucher_no,
                    'date': cp.date.strftime('%Y-%m-%d'),
                    'amount': float(cp.amount),
                    'mode': 'Cash',
                    'narration': cp.narration or '',
                })
                total_paid += cp.amount

            # Bank Payments
            for bp in BankPayment.objects.filter(purchase=purchase).order_by('date'):
                payment_history.append({
                    'entry_type': 'Payment',
                    'type': bp.type,
                    'voucher_no': bp.voucher_no,
                    'date': bp.date.strftime('%Y-%m-%d'),
                    'amount': float(bp.amount),
                    'mode': bp.mode or 'Bank',
                    'narration': bp.narration or '',
                })
                total_paid += bp.amount

            # Purchase Returns
            for pr in PurchaseReturnMaster.objects.filter(
                original_bill_no=purchase.billNo,
                branch=branch
            ).order_by('date'):
                payment_history.append({
                    'entry_type': 'Return',
                    'type': 'PR',
                    'voucher_no': pr.return_no,
                    'date': pr.date.strftime('%Y-%m-%d'),
                    'amount': float(pr.grand_total),
                    'mode': pr.payment_terms or 'Credit',
                    'narration': pr.narration or '',
                })
                total_returned += pr.grand_total

            payment_history.sort(key=lambda x: x['date'])

            pending_amount = float(purchase.grand_total) - float(total_paid) - float(total_returned)

            return Response({
                'id': purchase.id,
                'bill_no': purchase.billNo,
                'date': purchase.date.strftime('%Y-%m-%d'),
                'party_id': purchase.partyName.id,
                'party_name': purchase.partyName.account_name,
                'party_mobile': getattr(purchase.partyName, 'mobile', ''),
                'party_state': getattr(purchase.partyName, 'state', ''),
                'payment_terms': purchase.terms or 'Credit',
                'grand_total': float(purchase.grand_total),
                'has_available_items': True,
                'fully_returned': False,
                'items': items_data,
                'total_paid': float(total_paid),
                'total_returned': float(total_returned),
                'pending_amount': pending_amount,
                'payment_history': payment_history,
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GeneratePurchaseReturnVoucherAPIView(APIView):
    """Generate next Purchase Return voucher number"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        from datetime import datetime
        from pos.models.settings import setting
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "PR", "PR") if settings_obj else "PR"
        
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year
        
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"
        
        last_return = PurchaseReturnMaster.objects.filter(
            branch=branch,
            return_no__startswith=pattern
        ).order_by("-id").first()
        
        last_no = 0
        if last_return and last_return.return_no:
            try:
                parts = last_return.return_no.split("/")
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except:
                last_no = 0
        
        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"
        
        print(f" Branch: {branch.branch_name} - Next PR Voucher: {voucher_no} (last: {last_no})")
        
        return Response({
            "voucher_no": voucher_no,
            "prefix": prefix,
            "financial_year": fy,
            "last_number": last_no,
            "next_number": next_no,
            "branch": branch.branch_name,
        })


class OriginalBillSearchAPIView(APIView):
    """Search original purchase bills"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        bill_type = request.GET.get('type')
        search = request.GET.get('query', '').strip()
        
        if bill_type == 'purchase':
            bills = PurchaseMaster.objects.filter(
                branch=branch
            )
            
            if search:
                bills = bills.filter(
                    Q(billNo__icontains=search) |
                    Q(partyName__account_name__icontains=search)
                )
            
            valid_bills = []
            for bill in bills:
                purchase_items = PurchaseItem.objects.filter(purchase=bill)
                has_available_items = False
                
                for p_item in purchase_items:
                    already_returned = PurchaseReturnItem.objects.filter(
                        purchase_item=p_item
                    ).aggregate(total_returned=Sum('return_quantity'))['total_returned'] or Decimal('0')
                    
                    available_quantity = p_item.quantity - already_returned
                    if available_quantity > Decimal('0'):
                        has_available_items = True
                        break
                
                if has_available_items:
                    valid_bills.append(bill)
            
            bills_data = []
            for bill in valid_bills[:100]:
                bills_data.append({
                    'id': bill.id,
                    'billNo': bill.billNo,
                    'partyName__account_name': bill.partyName.account_name,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'grand_total': float(bill.grand_total)
                })
            
            return Response({
                'type': 'purchase',
                'bills': bills_data
            })
        
        return Response({"error": "Invalid bill type"}, status=400)


class ReceivePurchaseReturnCreditBillCashAPIView(APIView):
    """Receive payment for purchase return credit bill via cash"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        data = request.data
        purchase_return_bill_id = data.get('purchase_return_bill_id')
        cash_account_id = data.get('cash_account')
        amount = Decimal(str(data.get('amount', 0)))

        try:
            purchase_return_bill = PurchaseReturnMaster.objects.get(
                id=purchase_return_bill_id,
                branch=branch,
                payment_terms__iexact='credit'
            )

            prcr_voucher = self.generate_cash_receipt_voucher(branch)

            cash_receipt = CashReceipt.objects.create(
                date=data['date'],
                voucher_no=prcr_voucher,
                cash_account_id=cash_account_id,
                op_account_id=purchase_return_bill.party.id,
                branch=branch,
                amount=amount,
                narration=f"Payment received against purchase return credit bill {purchase_return_bill.return_no}",
                type="PRCR",
                purchase_return=purchase_return_bill,
                created_by=request.user,
            )

            from pos.models.account import Account
            from pos.models.salesentry import SalesMaster
            supplier = Account.objects.select_for_update().get(pk=purchase_return_bill.party.pk)
            print(f" Settling PRCR - Supplier: {supplier.account_name} | "
                f"Balance: {supplier.current_balance} {supplier.current_drcr} | Amount: ₹{amount}")
            SalesMaster.update_balance(supplier, amount, "Cr")
            print(f" After settle - Supplier: {supplier.current_balance} {supplier.current_drcr}")

            return Response({
                'success': True,
                'message': 'Purchase return credit bill payment received successfully',
                'receipt': {
                    'id': cash_receipt.id,
                    'voucher_no': cash_receipt.voucher_no,
                    'amount': float(cash_receipt.amount),
                    'type': cash_receipt.type
                }
            }, status=status.HTTP_201_CREATED)

        except PurchaseReturnMaster.DoesNotExist:
            return Response({'error': 'Purchase return bill not found'}, status=404)
    
    def generate_cash_receipt_voucher(self, branch):
        from datetime import datetime
        from pos.models.settings import setting

        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CR", "CR") if settings_obj else "CR"

        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year

        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"

        last_voucher = CashReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        return voucher_no


class PurchaseReturnCreditBillsAPIView(APIView):
    """Get Purchase Return credit bills with pending receipt"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        from django.db.models import Q, Sum
        from decimal import Decimal
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        search = request.GET.get('query', '').strip()
        
        bills = PurchaseReturnMaster.objects.filter(
            branch=branch,
            payment_terms__iexact='credit'
        )
        
        if search:
            bills = bills.filter(
                Q(return_no__icontains=search) |
                Q(party__account_name__icontains=search) |
                Q(original_bill_no__icontains=search)
            )
        
        bills_data = []
        for bill in bills:
            original_bill_terms = "unknown"
            original_bill_paid = Decimal('0')
            try:
                original_bill = PurchaseMaster.objects.get(
                    billNo=bill.original_bill_no,
                    branch=branch
                )
                original_bill_terms = original_bill.terms.lower()
                
                if original_bill_terms == "credit":
                    pcp_paid = CashPayment.objects.filter(
                        purchase=original_bill
                    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                    
                    pbp_paid = BankPayment.objects.filter(
                        purchase=original_bill
                    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                    
                    original_bill_paid = pcp_paid + pbp_paid
            except PurchaseMaster.DoesNotExist:
                pass
            
            total_received = CashReceipt.objects.filter(
                purchase_return=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            total_received += BankReceipt.objects.filter(
                purchase_return=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            pending_amount = bill.grand_total - total_received
            
            show_bill = False
            
            if original_bill_terms in ["cash", "bank"]:
                show_bill = True
                print(f"  ✅ SHOW PR {bill.return_no}: Original {original_bill_terms}")
                
            elif original_bill_terms == "credit":
                if original_bill_paid > 0:
                    show_bill = True
                    print(f"  ✅ SHOW PR {bill.return_no}: Original Credit + PCP/PBP paid ₹{original_bill_paid}")
                elif total_received > 0:
                    show_bill = True
                    print(f"  ✅ SHOW PR {bill.return_no}: Original Credit + PRCR/PRBR ₹{total_received}")
                else:
                    show_bill = False
                    print(f"  ⏭️ SKIP PR {bill.return_no}: Original Credit + No payment/receipt (auto-adjusted)")
            
            print(f"  PR {bill.return_no}: Grand={bill.grand_total}, Received={total_received}, Pending={pending_amount}, OriginalTerms={original_bill_terms}, OriginalPaid={original_bill_paid}, Show={show_bill}")
            
            if show_bill and pending_amount > 0:
                bills_data.append({
                    'id': bill.id,
                    'billNo': bill.return_no,
                    'originalBillNo': bill.original_bill_no,
                    'partyName__account_name': bill.party.account_name,
                    'party_id': bill.party.id,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'grand_total': float(bill.grand_total),
                    'paid_amount': float(total_received),
                    'pending_amount': float(pending_amount),
                })
        
        return Response({
            'type': 'purchaseReturn',
            'bills': bills_data
        })


class ReceivePurchaseReturnCreditBillBankAPIView(APIView):
    """Receive payment for purchase return credit bill via bank"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        data = request.data
        purchase_return_bill_id = data.get('purchase_return_bill_id')
        bank_account_id = data.get('bank_account')
        amount = Decimal(str(data.get('amount', 0)))
        mode = data.get('mode', 'UPI')

        try:
            purchase_return_bill = PurchaseReturnMaster.objects.get(
                id=purchase_return_bill_id,
                branch=branch,
                payment_terms__iexact='credit'
            )

            prbr_voucher = self.generate_bank_receipt_voucher(branch)

            bank_receipt = BankReceipt.objects.create(
                date=data['date'],
                voucher_no=prbr_voucher,
                bank_account_id=bank_account_id,
                op_account_id=purchase_return_bill.party.id,
                branch=branch,
                amount=amount,
                mode=mode,
                cheque_no=data.get('cheque_no'),
                cheque_date=data.get('cheque_date'),
                cheque_clear_date=data.get('cheque_clear_date'),
                narration=f"Payment received against purchase return credit bill {purchase_return_bill.return_no}",
                type="PRBR",
                purchase_return=purchase_return_bill,
                created_by=request.user,
            )

            from pos.models.account import Account
            from pos.models.salesentry import SalesMaster
            supplier = Account.objects.select_for_update().get(pk=purchase_return_bill.party.pk)
            print(f" Settling PRBR - Supplier: {supplier.account_name} | "
                f"Balance: {supplier.current_balance} {supplier.current_drcr} | Amount: ₹{amount}")
            SalesMaster.update_balance(supplier, amount, "Cr")
            print(f" After settle - Supplier: {supplier.current_balance} {supplier.current_drcr}")

            return Response({
                'success': True,
                'message': 'Purchase return credit bill payment received successfully',
                'receipt': {
                    'id': bank_receipt.id,
                    'voucher_no': bank_receipt.voucher_no,
                    'amount': float(bank_receipt.amount),
                    'type': bank_receipt.type
                }
            }, status=status.HTTP_201_CREATED)

        except PurchaseReturnMaster.DoesNotExist:
            return Response({'error': 'Purchase return bill not found'}, status=404)
    
    def generate_bank_receipt_voucher(self, branch):
        from datetime import datetime
        from pos.models.settings import setting

        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BR", "BR") if settings_obj else "BR"

        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year

        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"

        last_voucher = BankReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{pattern}{next_no}"

        return voucher_no
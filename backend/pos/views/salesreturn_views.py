# pos/views/salesreturn_views.py

from pos.models.bankreceipt import BankReceipt
from pos.models.cashreceipt import CashReceipt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Q, Sum
from decimal import Decimal
from urllib.parse import unquote

from pos.models.salesreturn import SalesReturnMaster, SalesReturnItem
from pos.models.items import items, itemvariants
from pos.serializers.salesreturn_serializers import SalesReturnMasterSerializer
from pos.models.salesentry import SalesItem, SalesMaster
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.models.settings import setting
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class SalesReturnCreateAPIView(APIView):
    """Create a new sales return"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/salesReturnList"  # ✅ ADD: Frontend route
    
    def generate_cash_payment_voucher(self, branch):
        """Generate voucher number for Sales Return Cash Payment (SRCP)"""
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

    def generate_bank_payment_voucher(self, branch):
        """Generate voucher number for Sales Return Bank Payment (SRBP)"""
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

        # Sales Return Master create karo
        sales_return = SalesReturnMaster.objects.create(
            branch=branch,
            date=data['date'],
            original_bill_no=data['original_bill_no'],
            customer_id=data['customer'],
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

        #  CREDIT RETURN: Customer balance SIRF YAHAN update karo — ek hi baar
        if payment_terms == 'credit':
            from pos.models.account import Account
            from pos.models.salesentry import SalesMaster as SM

            customer = Account.objects.select_for_update().get(pk=sales_return.customer.pk)
            SM.update_balance(customer, sales_return.grand_total, "Cr")

        alert_messages = []
        
        # Process items and update stock (SALES RETURN = INCREASE STOCK)
        for it in items_data:
            qty = Decimal(str(it.get('return_quantity', 0)))
            variant_raw = it.get('variant_id')
            sales_item_id = it.get('sales_item_id')
            
            if sales_item_id:
                try:
                    sales_item = SalesItem.objects.get(id=sales_item_id)
                    already_returned = SalesReturnItem.objects.filter(
                        sales_item=sales_item
                    ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')
                    max_returnable = sales_item.qty - already_returned
                    
                    if qty > max_returnable:
                        alert_messages.append(
                            f"{sales_item.item_name.itemName} - "
                            f"Can only return {max_returnable} (already returned {already_returned})"
                        )
                        continue
                except SalesItem.DoesNotExist:
                    pass
            
            # Update stock - Sales Return INCREASES stock
            if variant_raw not in [None, "", "null"]:
                try:
                    variant = itemvariants.objects.select_for_update().get(id=int(variant_raw))
                    variant.current_stock += qty
                    variant.save()
                except itemvariants.DoesNotExist:
                    pass
            else:
                try:
                    item_obj = items.objects.select_for_update().get(id=it['item_id'])
                    item_obj.current_stock += qty
                    item_obj.save()
                except items.DoesNotExist:
                    pass
            
            # Create Sales Return Item
            SalesReturnItem.objects.create(
                sales_return=sales_return,
                sales_item_id=sales_item_id,
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
        
        # ✅ Create Payment for Cash or Bank (Money going OUT to customer)
        payment_error = None
        
        if payment_terms == "cash":
            cash_account_id = data.get('cash_account')
            if cash_account_id and data.get('customer'):
                try:
                    from pos.models.account import Account
                    cash_account = Account.objects.get(id=cash_account_id, branch=branch)
                    
                    if cash_account.current_balance < sales_return.grand_total:
                        payment_error = f"Insufficient balance in {cash_account.account_name}. Available: ₹{cash_account.current_balance}, Required: ₹{sales_return.grand_total}"
                    else:
                        srcp_voucher = self.generate_cash_payment_voucher(branch)
                        
                        cash_payment = CashPayment.objects.create(
                            date=data['date'],
                            voucher_no=srcp_voucher,
                            cash_account_id=cash_account_id,
                            op_account_id=data['customer'],
                            branch=branch,
                            amount=sales_return.grand_total,
                            mode="Cash",
                            narration=f"Auto payment against Sales Return {sales_return.return_no}",
                            type="SRCP",
                            sales_return=sales_return
                        )
                        
                except Account.DoesNotExist:
                    payment_error = "Selected cash account not found"
                except Exception as e:
                    payment_error = f"Payment failed: {str(e)}"
        
        elif payment_terms == "bank":
            bank_account_id = data.get('bank_account')
            if bank_account_id and data.get('customer'):
                try:
                    from pos.models.account import Account
                    bank_account = Account.objects.get(id=bank_account_id, branch=branch)
                    
                    if bank_account.current_balance < sales_return.grand_total:
                        payment_error = f"Insufficient balance in {bank_account.account_name}. Available: ₹{bank_account.current_balance}, Required: ₹{sales_return.grand_total}"
                    else:
                        srbp_voucher = self.generate_bank_payment_voucher(branch)
                        
                        bank_payment = BankPayment.objects.create(
                            date=data['date'],
                            voucher_no=srbp_voucher,
                            bank_account_id=bank_account_id,
                            op_account_id=data['customer'],
                            branch=branch,
                            amount=sales_return.grand_total,
                            mode="Auto",
                            narration=f"Auto payment against Sales Return {sales_return.return_no}",
                            type="SRBP",
                            sales_return=sales_return
                        )
                        
                except Account.DoesNotExist:
                    payment_error = "Selected bank account not found"
                except Exception as e:
                    payment_error = f"Payment failed: {str(e)}"
        
        response = {
            "message": "Sales Return Created Successfully",
            "id": sales_return.id,
            "return_no": sales_return.return_no,
        }
        
        if alert_messages:
            response["stock_alerts"] = alert_messages
        
        if payment_error:
            transaction.set_rollback(True)
            return Response(
                {"error": payment_error},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(response, status=201)


class SalesReturnListAPIView(APIView):
    """List all sales returns"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/salesReturnList"  # ✅ ADD: Frontend route

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

        queryset = SalesReturnMaster.objects.filter(
            branch=branch
        ).order_by('-date', '-created_at', '-id')
        
        paginator = StandardResultsSetPagination()
        paginated_salesreturn = paginator.paginate_queryset(queryset, request)

        serializer = SalesReturnMasterSerializer(paginated_salesreturn, many=True)
        return paginator.get_paginated_response(serializer.data)
    
class SalesReturnDetailAPIView(APIView):
    """Get single sales return details"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/salesReturnList"  # ✅ ADD: Frontend route
    
    def get(self, request, return_id):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            sales_return = SalesReturnMaster.objects.get(
                id=return_id,
                branch=branch
            )
            serializer = SalesReturnMasterSerializer(sales_return)
            return Response(serializer.data)
        except SalesReturnMaster.DoesNotExist:
            return Response({"error": "Sales Return not found"}, status=404)


class SalesReturnDeleteAPIView(APIView):
    """Delete a sales return"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/salesReturnList"  # ✅ ADD: Frontend route
    
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
            sales_return = SalesReturnMaster.objects.get(
                id=return_id,
                branch=branch
            )
            
            # Reverse stock updates (decrease stock back)
            for item in sales_return.items.all():
                qty = item.return_quantity
                if item.variant:
                    variant = item.variant
                    variant.current_stock -= qty
                    variant.save()
                else:
                    item_obj = item.item
                    item_obj.current_stock -= qty
                    item_obj.save()
            
            # Delete associated payments
            CashPayment.objects.filter(sales_return=sales_return).delete()
            BankPayment.objects.filter(sales_return=sales_return).delete()
            
            sales_return.delete()
            return Response({"message": "Sales Return deleted successfully"}, status=204)
        except SalesReturnMaster.DoesNotExist:
            return Response({"error": "Sales Return not found"}, status=404)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER/Lookup APIS — No permission gate (only IsAuthenticated)
# ─────────────────────────────────────────────────────────────────────────────

class OriginalBillSearchAPIView(APIView):
    """Search original sales bills that have remaining items to return"""
    
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
        
        if bill_type == 'sales':
            bills = SalesMaster.objects.filter(branch=branch)
            
            if search:
                bills = bills.filter(
                    Q(bill_no__icontains=search) |
                    Q(customer__account_name__icontains=search)
                )
            
            valid_bills = []
            for bill in bills:
                sales_items = SalesItem.objects.filter(sales=bill)
                has_available_items = False
                
                for s_item in sales_items:
                    already_returned = SalesReturnItem.objects.filter(
                        sales_item=s_item
                    ).aggregate(total_returned=Sum('return_quantity'))['total_returned'] or Decimal('0')
                    
                    available_quantity = s_item.qty - already_returned
                    if available_quantity > Decimal('0'):
                        has_available_items = True
                        break
                
                if has_available_items:
                    valid_bills.append(bill)
            
            bills_data = []
            for bill in valid_bills[:100]:
                bills_data.append({
                    'id': bill.id,
                    'billNo': bill.bill_no,
                    'partyName__account_name': bill.customer.account_name,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'grand_total': float(bill.grand_total)
                })
            
            return Response({'type': 'sales', 'bills': bills_data})
        
        return Response({"error": "Invalid bill type. Use type=sales"}, status=400)


class SalesBillDetailsAPIView(APIView):
    """Get sales bill details with items, already-returned quantities,
    and a full payment / return history."""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]
 
    def get(self, request, bill_no):
        from decimal import Decimal
        from urllib.parse import unquote
        from django.db.models import Sum
        from pos.models.salesreturn import SalesReturnMaster
        from pos.models.cashreceipt import CashReceipt
        from pos.models.bankreceipt import BankReceipt
 
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
            sales = SalesMaster.objects.get(
                bill_no=bill_no_decoded,
                branch=branch
            )
 
            sales_items = SalesItem.objects.filter(
                sales=sales
            ).select_related('item_name', 'variant')
 
            items_data = []
            for s_item in sales_items:
                already_returned = SalesReturnItem.objects.filter(
                    sales_item=s_item
                ).aggregate(total_returned=Sum('return_quantity'))['total_returned'] or Decimal('0')
 
                available_quantity = float(s_item.qty) - float(already_returned)
                if available_quantity <= 0:
                    continue
 
                default_return_qty = available_quantity if return_type == 'Full' else 0
 
                items_data.append({
                    'id': s_item.id,
                    'item_id': s_item.item_name.id,
                    'sales_item_id': s_item.id,
                    'item_name': s_item.item_name.itemName,
                    'variant_id': s_item.variant.id if s_item.variant else None,
                    'hsn_code': s_item.hsn_code,
                    'quantity': float(s_item.qty),
                    'already_returned': float(already_returned),
                    'available_quantity': available_quantity,
                    'default_return_quantity': default_return_qty,
                    'price': float(s_item.price),
                    'unit': s_item.unit,
                    'tax_percent': float(s_item.tax_percent),
                    'basic_amount': float(s_item.basic_amount),
                    'tax_amount': float(s_item.tax_amount),
                    'net_amount': float(s_item.net_amount),
                })
 
            if not items_data:
                return Response(
                    {'error': 'All items from this bill have already been returned',
                     'fully_returned': True},
                    status=status.HTTP_404_NOT_FOUND
                )
 
            # PAYMENT HISTORY
            payment_history = []
            total_paid = Decimal('0')
            total_returned = Decimal('0')
 
            # 1️⃣ SALES ENTRY
            payment_history.append({
                'entry_type': 'Sale',
                'type': 'BILL',
                'voucher_no': sales.bill_no,
                'date': sales.date.strftime('%Y-%m-%d'),
                'amount': float(sales.grand_total),
                'mode': sales.payment_terms or 'Credit',
                'narration': f'Sales Bill - {sales.customer.account_name}',
            })
 
            # 2️⃣ Cash receipts
            for cr in CashReceipt.objects.filter(sales_entry=sales).order_by('date'):
                payment_history.append({
                    'entry_type': 'Receipt',
                    'type': cr.type,
                    'voucher_no': cr.voucher_no,
                    'date': cr.date.strftime('%Y-%m-%d'),
                    'amount': float(cr.amount),
                    'mode': 'Cash',
                    'narration': cr.narration or '',
                })
                total_paid += cr.amount
 
            # 3️⃣ Bank receipts
            for br in BankReceipt.objects.filter(sales_entry=sales).order_by('date'):
                payment_history.append({
                    'entry_type': 'Receipt',
                    'type': br.type,
                    'voucher_no': br.voucher_no,
                    'date': br.date.strftime('%Y-%m-%d'),
                    'amount': float(br.amount),
                    'mode': br.mode or 'Bank',
                    'narration': br.narration or '',
                })
                total_paid += br.amount
 
            # 4️⃣ Sales returns
            for sr in SalesReturnMaster.objects.filter(
                original_bill_no=sales.bill_no,
                branch=branch
            ).order_by('date'):
                payment_history.append({
                    'entry_type': 'Return',
                    'type': 'SR',
                    'voucher_no': sr.return_no,
                    'date': sr.date.strftime('%Y-%m-%d'),
                    'amount': float(sr.grand_total),
                    'mode': sr.payment_terms or 'Credit',
                    'narration': sr.narration or '',
                })
                total_returned += sr.grand_total
 
            payment_history.sort(key=lambda x: x['date'])
            pending_amount = float(sales.grand_total) - float(total_paid) - float(total_returned)
 
            return Response({
                'id': sales.id,
                'bill_no': sales.bill_no,
                'date': sales.date.strftime('%Y-%m-%d'),
                'customer_id': sales.customer.id,
                'customer_name': sales.customer.account_name,
                'customer_mobile': getattr(sales.customer, 'mobile', ''),
                'customer_state': getattr(sales.customer, 'state', ''),
                'payment_terms': sales.payment_terms,
                'grand_total': float(sales.grand_total),
                'items': items_data,
                'total_paid': float(total_paid),
                'total_returned': float(total_returned),
                'pending_amount': pending_amount,
                'payment_history': payment_history,
            })
 
        except SalesMaster.DoesNotExist:
            return Response(
                {'error': f'Sales bill not found: {bill_no_decoded}'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GenerateSalesReturnVoucherAPIView(APIView):
    """Generate next Sales Return voucher number"""
    
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
        prefix = getattr(settings_obj, "SR", "SR") if settings_obj else "SR"
        
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year
        
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        
        last_return = SalesReturnMaster.objects.filter(
            branch=branch,
            return_no__startswith=f"{prefix}/{fy}/"
        ).order_by("-id").first()
        
        last_no = 0
        if last_return and last_return.return_no:
            try:
                last_no = int(last_return.return_no.split("/")[-1])
            except:
                last_no = 0
        
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{prefix}/{fy}/{next_no}"
        
        return Response({
            "voucher_no": voucher_no,
            "prefix": prefix,
            "financial_year": fy,
            "last_number": last_no,
            "next_number": last_no + 1
        })
        

class SalesReturnCreditBillsAPIView(APIView):
    """Get Sales Return credit bills with pending payment."""
    
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

        bills = SalesReturnMaster.objects.filter(
            branch=branch,
            payment_terms__iexact='credit'
        )

        if search:
            bills = bills.filter(
                Q(return_no__icontains=search) |
                Q(customer__account_name__icontains=search) |
                Q(original_bill_no__icontains=search)
            )

        bills_data = []
        for bill in bills:
            original_bill_terms = "unknown"
            original_bill_received = Decimal('0')
            try:
                original_bill = SalesMaster.objects.get(
                    bill_no=bill.original_bill_no,
                    branch=branch
                )
                original_bill_terms = original_bill.payment_terms.lower()
                
                if original_bill_terms == "credit":
                    scr_received = CashReceipt.objects.filter(
                        sales_entry=original_bill
                    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                    
                    sbr_received = BankReceipt.objects.filter(
                        sales_entry=original_bill
                    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                    
                    original_bill_received = scr_received + sbr_received
            except SalesMaster.DoesNotExist:
                pass
            
            total_paid = CashPayment.objects.filter(
                sales_return=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            total_paid += BankPayment.objects.filter(
                sales_return=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            pending_amount = bill.grand_total - total_paid
            
            show_bill = False
            
            if original_bill_terms in ["cash", "bank"]:
                show_bill = True
                
            elif original_bill_terms == "credit":
                if original_bill_received > 0:
                    show_bill = True
                elif total_paid > 0:
                    show_bill = True
                else:
                    show_bill = False
            
            if show_bill and pending_amount > 0:
                bills_data.append({
                    'id': bill.id,
                    'billNo': bill.return_no,
                    'originalBillNo': bill.original_bill_no,
                    'partyName__account_name': bill.customer.account_name,
                    'party_id': bill.customer.id,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'grand_total': float(bill.grand_total),
                    'paid_amount': float(total_paid),
                    'pending_amount': float(pending_amount),
                })

        return Response({'type': 'salesReturn', 'bills': bills_data})


class SettleCreditBillAPIView(APIView):
    """Settle a credit sales return bill via cash payment"""
    
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
        bill_id = data.get('bill_id')
        cash_account_id = data.get('cash_account')
        amount = Decimal(str(data.get('amount', 0)))
        
        try:
            credit_bill = SalesReturnMaster.objects.get(
                id=bill_id,
                branch=branch,
                payment_terms='credit'
            )
            
            srcp_voucher = self.generate_cash_payment_voucher(branch)
            
            cash_payment = CashPayment.objects.create(
                date=data['date'],
                voucher_no=srcp_voucher,
                cash_account_id=cash_account_id,
                op_account_id=credit_bill.customer.id,
                branch=branch,
                amount=amount,
                mode="Cash",
                narration=f"Payment against credit bill {credit_bill.return_no}",
                type="SRCP",
                sales_return=credit_bill,
                created_by=request.user,
            )
            
            return Response({
                'success': True,
                'message': 'Credit bill settled successfully',
                'payment': {
                    'id': cash_payment.id,
                    'voucher_no': cash_payment.voucher_no,
                    'amount': float(cash_payment.amount),
                    'type': cash_payment.type
                }
            }, status=status.HTTP_201_CREATED)
            
        except SalesReturnMaster.DoesNotExist:
            return Response({'error': 'Credit bill not found'}, status=404)
    
    def generate_cash_payment_voucher(self, branch):
        from datetime import datetime
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CP", "CP") if settings_obj else "CP"

        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"

        last_voucher = CashPayment.objects.filter(
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

        while CashPayment.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        return voucher_no


class SettleCreditBillBankAPIView(APIView):
    """Settle a credit sales return bill via bank payment"""
    
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
        bill_id = data.get('bill_id')
        bank_account_id = data.get('bank_account')
        amount = Decimal(str(data.get('amount', 0)))
        mode = data.get('mode', 'UPI')
        
        try:
            credit_bill = SalesReturnMaster.objects.get(
                id=bill_id,
                branch=branch,
                payment_terms='credit'
            )
            
            srbp_voucher = self.generate_bank_payment_voucher(branch)
            
            bank_payment = BankPayment.objects.create(
                date=data['date'],
                voucher_no=srbp_voucher,
                bank_account_id=bank_account_id,
                op_account_id=credit_bill.customer.id,
                branch=branch,
                amount=amount,
                mode=mode,
                cheque_no=data.get('cheque_no'),
                cheque_date=data.get('cheque_date'),
                cheque_clear_date=data.get('cheque_clear_date'),
                narration=f"Payment against credit bill {credit_bill.return_no}",
                type="SRBP",
                sales_return=credit_bill,
                created_by=request.user,
            )
            
            return Response({
                'success': True,
                'message': 'Credit bill settled successfully',
                'payment': {
                    'id': bank_payment.id,
                    'voucher_no': bank_payment.voucher_no,
                    'amount': float(bank_payment.amount),
                    'type': bank_payment.type
                }
            }, status=status.HTTP_201_CREATED)
            
        except SalesReturnMaster.DoesNotExist:
            return Response({'error': 'Credit bill not found'}, status=404)
    
    def generate_bank_payment_voucher(self, branch):
        from datetime import datetime
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BP", "BP") if settings_obj else "BP"

        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"

        last_voucher = BankPayment.objects.filter(
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

        while BankPayment.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        return voucher_no
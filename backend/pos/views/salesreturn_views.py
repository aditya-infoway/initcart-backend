# pos/views/salesreturn_views.py

import logging  # noqa: F401
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import unquote

from pos.models.bankreceipt import BankReceipt
from pos.models.cashreceipt import CashReceipt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Q, Sum, F, Prefetch, Exists, OuterRef, DecimalField
from django.db.models.functions import Coalesce

from pos.models.salesreturn import SalesReturnMaster, SalesReturnItem
from pos.models.items import items, itemvariants
from pos.models.account import Account
from pos.models.branch import Branch
from pos.serializers.salesreturn_serializers import SalesReturnMasterSerializer
from pos.models.salesentry import SalesItem, SalesMaster
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.models.settings import setting
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# SMALL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date_param(value):
    """'YYYY-MM-DD' validate karta hai; galat ho to None (filter ignore)."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _next_voucher_no(model, branch, setting_attr, default_prefix, field="voucher_no"):
    """
    PREFIX/FY/0001 (FY April se). Duplicate se bachne ke liye exists() loop ke saath.
    Settle cash/bank payment ke liye (pehle dono jagah same copy-paste tha).
    """
    settings_obj = setting.objects.filter(branch=branch).first()
    prefix = getattr(settings_obj, setting_attr, default_prefix) if settings_obj else default_prefix

    now = datetime.now()
    fy_start = now.year if now.month >= 4 else now.year - 1
    fy_end = fy_start + 1
    fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
    pattern = f"{prefix}/{fy}/"

    last = model.objects.filter(
        branch=branch, **{f"{field}__startswith": pattern}
    ).order_by("-id").first()

    last_no = 0
    last_value = getattr(last, field, None) if last else None
    if last_value:
        try:
            last_no = int(last_value.split("/")[-1])
        except (ValueError, IndexError):
            last_no = 0

    next_no = last_no + 1
    voucher_no = f"{pattern}{str(next_no).zfill(4)}"
    while model.objects.filter(branch=branch, **{field: voucher_no}).exists():
        next_no += 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"
    return voucher_no


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class SalesReturnCreateAPIView(APIView):
    """Create a new sales return"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/salesReturnList"  # ✅ ADD: Frontend route
    
    # NOTE: ye dono generators jaan-bujh kar jaise the waise rakhe hain.
    # Inka numbering logic (branch ka last voucher, FY filter ke bina) Settle wale
    # generators se alag hai, merge karne se voucher numbers badal jaate.
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
            customer = Account.objects.select_for_update().get(pk=sales_return.customer_id)
            SalesMaster.update_balance(customer, sales_return.grand_total, "Cr")

        alert_messages = []

        # ── BULK PRELOAD (pehle har item par 3 queries chalti thi) ──
        sales_item_ids, variant_ids = [], []
        for it in items_data:
            sid = _to_int(it.get('sales_item_id'))
            if sid:
                sales_item_ids.append(sid)
            vraw = it.get('variant_id')
            if vraw not in [None, "", "null"]:
                vid = _to_int(vraw)
                if vid is not None:
                    variant_ids.append(vid)

        sales_item_map = {}
        already_map = defaultdict(lambda: Decimal('0'))
        if sales_item_ids:
            sales_item_map = {
                s.id: s for s in SalesItem.objects
                .select_related('item_name').filter(id__in=sales_item_ids)
            }
            for row in (SalesReturnItem.objects.filter(sales_item_id__in=sales_item_ids)
                        .values('sales_item_id').annotate(t=Sum('return_quantity')).order_by()):
                already_map[row['sales_item_id']] += row['t'] or Decimal('0')

        variant_map = {}
        if variant_ids:
            variant_map = {
                v.id: v for v in itemvariants.objects
                .select_for_update().filter(id__in=variant_ids).order_by('id')
            }

        # Process items and update stock (SALES RETURN = INCREASE STOCK)
        for it in items_data:
            qty = Decimal(str(it.get('return_quantity', 0)))
            variant_raw = it.get('variant_id')
            sales_item_id = it.get('sales_item_id')
            sales_item = None
            
            if sales_item_id:
                sales_item = sales_item_map.get(_to_int(sales_item_id))
                if sales_item is not None:
                    already_returned = already_map[sales_item.id]
                    max_returnable = sales_item.qty - already_returned
                    
                    if qty > max_returnable:
                        alert_messages.append(
                            f"{sales_item.item_name.itemName} - "
                            f"Can only return {max_returnable} (already returned {already_returned})"
                        )
                        continue
            
            # Update stock - Sales Return INCREASES stock
            if variant_raw not in [None, "", "null"]:
                variant = variant_map.get(_to_int(variant_raw))
                if variant is not None:
                    variant.current_stock += qty
                    variant.save()
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

            # Same request me wahi sales item dobara aaye to "already returned" sahi rahe
            if sales_item is not None:
                already_map[sales_item.id] += qty.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # ✅ Create Payment for Cash or Bank (Money going OUT to customer)
        payment_error = None
        
        if payment_terms == "cash":
            cash_account_id = data.get('cash_account')
            if cash_account_id and data.get('customer'):
                try:
                    cash_account = Account.objects.get(id=cash_account_id, branch=branch)
                    
                    if cash_account.current_balance < sales_return.grand_total:
                        payment_error = f"Insufficient balance in {cash_account.account_name}. Available: ₹{cash_account.current_balance}, Required: ₹{sales_return.grand_total}"
                    else:
                        srcp_voucher = self.generate_cash_payment_voucher(branch)
                        
                        CashPayment.objects.create(
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
                    bank_account = Account.objects.get(id=bank_account_id, branch=branch)
                    
                    if bank_account.current_balance < sales_return.grand_total:
                        payment_error = f"Insufficient balance in {bank_account.account_name}. Available: ₹{bank_account.current_balance}, Required: ₹{sales_return.grand_total}"
                    else:
                        srbp_voucher = self.generate_bank_payment_voucher(branch)
                        
                        BankPayment.objects.create(
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
    """List sales returns — server-side search / filter / pagination.

    Query params (sab optional): page, page_size, search, return_type (Full/Partial),
    date_from, date_to (YYYY-MM-DD).
    Response me extra key: overall_total
    """
    
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
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)

        queryset = SalesReturnMaster.objects.filter(branch=branch)

        # ── Server-side search / filters (pehle browser me hote the) ──
        search = request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(return_no__icontains=search)
                | Q(customer__account_name__icontains=search)
                | Q(reason_for_return__icontains=search)
            )

        return_type = request.GET.get('return_type', '').strip()
        if return_type:
            queryset = queryset.filter(return_type__iexact=return_type)

        date_from = _parse_date_param(request.GET.get('date_from'))
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        date_to = _parse_date_param(request.GET.get('date_to'))
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        # Grand total (saare filtered records), pagination se PEHLE
        overall_total = queryset.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

        queryset = (
            queryset
            .select_related('customer', 'created_by')
            .prefetch_related(Prefetch(
                'items',
                queryset=SalesReturnItem.objects.select_related('item', 'variant'),
            ))
            .order_by('-date', '-created_at', '-id')
        )
        
        paginator = StandardResultsSetPagination()
        paginated_salesreturn = paginator.paginate_queryset(queryset, request)

        serializer = SalesReturnMasterSerializer(paginated_salesreturn, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data['overall_total'] = float(overall_total)
        return response
    
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
            sales_return = (
                SalesReturnMaster.objects
                .select_related('customer', 'created_by')
                .prefetch_related(Prefetch(
                    'items',
                    queryset=SalesReturnItem.objects.select_related('item', 'variant'),
                ))
                .get(id=return_id, branch=branch)
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
            for item in sales_return.items.select_related('variant', 'item'):
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

            # Bill valid tab hai jab uska koi bhi item abhi return hone ko bacha ho
            # (qty - already_returned > 0). Pehle ye bills × items queries se hota tha;
            # ab ek hi query (Exists subquery).
            returnable_items = (
                SalesItem.objects.filter(sales=OuterRef('pk'))
                .annotate(returned=Coalesce(
                    Sum('returns__return_quantity'), Decimal('0'),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ))
                .filter(qty__gt=F('returned'))
                .order_by()
            )
            valid_bills = (
                bills.annotate(has_available=Exists(returnable_items))
                .filter(has_available=True)
                .select_related('customer')
                .order_by('-date', '-id')[:100]
            )
            
            bills_data = []
            for bill in valid_bills:
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
            sales = SalesMaster.objects.select_related('customer').get(
                bill_no=bill_no_decoded,
                branch=branch
            )
 
            sales_items = list(
                SalesItem.objects.filter(sales=sales).select_related('item_name', 'variant')
            )

            # Har item ka already-returned ek hi grouped query me
            returned_map = {
                r['sales_item_id']: r['t']
                for r in SalesReturnItem.objects.filter(
                    sales_item_id__in=[s.id for s in sales_items]
                ).values('sales_item_id').annotate(t=Sum('return_quantity')).order_by()
            }
 
            items_data = []
            for s_item in sales_items:
                already_returned = returned_map.get(s_item.id) or Decimal('0')
 
                available_quantity = float(s_item.qty) - float(already_returned)
                if available_quantity <= 0:
                    continue
 
                default_return_qty = available_quantity if return_type == 'Full' else 0
 
                items_data.append({
                    'id': s_item.id,
                    'item_id': s_item.item_name.id,
                    'sales_item_id': s_item.id,
                    'item_name': s_item.item_name.itemName,
                    'variant_id': s_item.variant_id,
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
    """Get Sales Return credit bills with pending payment. (money data -> never cached)"""
    
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

        search = request.GET.get('query', '').strip()

        qs = SalesReturnMaster.objects.filter(
            branch=branch,
            payment_terms__iexact='credit'
        )

        if search:
            qs = qs.filter(
                Q(return_no__icontains=search) |
                Q(customer__account_name__icontains=search) |
                Q(original_bill_no__icontains=search)
            )

        bills = list(qs.select_related('customer').order_by('id'))
        if not bills:
            return Response({'type': 'salesReturn', 'bills': []})

        zero = Decimal('0')

        # ── 1) Original bills ek hi query me (pehle har bill par 1 get) ──
        originals = {
            o.bill_no: o for o in SalesMaster.objects.filter(
                branch=branch,
                bill_no__in={b.original_bill_no for b in bills},
            )
        }

        # ── 2) Original CREDIT bills par mile receipts (Cash + Bank) ──
        credit_original_ids = [
            o.id for o in originals.values()
            if (o.payment_terms or '').lower() == 'credit'
        ]
        received_map = defaultdict(lambda: Decimal('0'))
        if credit_original_ids:
            for row in (CashReceipt.objects.filter(sales_entry_id__in=credit_original_ids)
                        .values('sales_entry_id').annotate(t=Sum('amount')).order_by()):
                received_map[row['sales_entry_id']] += row['t'] or zero
            for row in (BankReceipt.objects.filter(sales_entry_id__in=credit_original_ids)
                        .values('sales_entry_id').annotate(t=Sum('amount')).order_by()):
                received_map[row['sales_entry_id']] += row['t'] or zero

        # ── 3) Return par diye gaye payments (Cash + Bank) ──
        bill_ids = [b.id for b in bills]
        paid_map = defaultdict(lambda: Decimal('0'))
        for row in (CashPayment.objects.filter(sales_return_id__in=bill_ids)
                    .values('sales_return_id').annotate(t=Sum('amount')).order_by()):
            paid_map[row['sales_return_id']] += row['t'] or zero
        for row in (BankPayment.objects.filter(sales_return_id__in=bill_ids)
                    .values('sales_return_id').annotate(t=Sum('amount')).order_by()):
            paid_map[row['sales_return_id']] += row['t'] or zero

        bills_data = []
        for bill in bills:
            original_bill_terms = "unknown"
            original_bill_received = zero
            original_bill = originals.get(bill.original_bill_no)
            if original_bill is not None:
                original_bill_terms = original_bill.payment_terms.lower()
                if original_bill_terms == "credit":
                    original_bill_received = received_map.get(original_bill.id, zero)

            total_paid = paid_map.get(bill.id, zero)
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
                op_account_id=credit_bill.customer_id,
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
        return _next_voucher_no(CashPayment, branch, "CP", "CP")


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
                op_account_id=credit_bill.customer_id,
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
        return _next_voucher_no(BankPayment, branch, "BP", "BP")
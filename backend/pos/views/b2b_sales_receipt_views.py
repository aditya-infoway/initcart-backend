# pos/views/b2b_sales_receipt_views.py
# B2B Sale credit bill listing + Cash/Bank receipt receiving
# EXACT SAME PATTERN as stock_transfer_receipt_views.py

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from pos.models.branch import Branch
from pos.models.account import Account
from pos.models.b2b_sales import B2BSale
from pos.models.cashreceipt import CashReceipt
from pos.models.bankreceipt import BankReceipt
from pos.views.stock_transfer_views import IsSuperAdminRole
# ✅ Reuse the SAME helper that finds a branch's linked Sundry Debitor/Creditor account
from pos.views.stock_transfer_receipt_views import get_branch_linked_account


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
def get_b2b_sale_total(sale):
    """
    Total bill amount for a B2B Sale.
    Fallback chain same as get_transfer_total() in stock_transfer_receipt_views.py:
      1. item.net_amount (GST-inclusive, set at creation)
      2. item.rate * item.quantity
      3. from_variant.branchPrice (live) * quantity
      4. from_variant.purchasePrice (live) * quantity — last resort
    """
    total = Decimal("0")
    items = sale.items.select_related('from_variant').all()
    for item in items:
        qty = Decimal(str(item.quantity or 0))
        net = Decimal(str(item.net_amount or 0))
        if net and net > 0:
            total += net
            continue

        rate = Decimal(str(item.rate or 0))
        if rate and rate > 0:
            total += rate * qty
            continue

        variant = item.from_variant
        if variant:
            branch_price = Decimal(str(getattr(variant, 'branchPrice', None) or 0))
            if branch_price and branch_price > 0:
                total += branch_price * qty
                continue
            purchase_price = Decimal(str(getattr(variant, 'purchasePrice', None) or 0))
            total += purchase_price * qty

    return total


def get_b2b_sale_paid(sale):
    """Total already received (cash + bank) against this B2B Sale."""
    cash_paid = CashReceipt.objects.filter(b2b_sale=sale).aggregate(
        total=Sum('amount'))['total'] or 0
    bank_paid = BankReceipt.objects.filter(b2b_sale=sale).aggregate(
        total=Sum('amount'))['total'] or 0
    return cash_paid + bank_paid


# ════════════════════════════════════════════════════════════
# LIST — B2B Sale bills with pending amount > 0
# ════════════════════════════════════════════════════════════
class B2BSaleCreditBillsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def get(self, request):
        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        query = request.GET.get('query', '').strip()

        sales = B2BSale.objects.filter(
            from_branch=my_branch,
            status__in=['pending', 'completed'],   # cancelled excluded
        ).select_related('to_branch').prefetch_related('items')

        if query:
            sales = sales.filter(
                Q(sale_no__icontains=query) |
                Q(to_branch__branch_name__icontains=query)
            )

        bills = []
        for s in sales:
            total_amount = get_b2b_sale_total(s)
            paid_amount = get_b2b_sale_paid(s)
            pending_amount = total_amount - paid_amount

            if pending_amount <= 0:
                continue

            linked_account, linked_type = get_branch_linked_account(s.to_branch)

            bills.append({
                'id': s.id,
                'billNo': s.sale_no,
                'sale_no': s.sale_no,
                'to_branch_id': s.to_branch_id,
                'to_branch_name': s.to_branch.branch_name,
                'partyName__account_name': s.to_branch.branch_name,
                'linked_account_id': linked_account.id if linked_account else None,
                'linked_account_name': linked_account.account_name if linked_account else None,
                'linked_account_type': linked_type,
                'date': str(s.sale_date),
                'grand_total': float(total_amount),
                'paid_amount': float(paid_amount),
                'pending_amount': float(pending_amount),
            })

        return Response({'success': True, 'bills': bills})


# ════════════════════════════════════════════════════════════
# RECEIVE — Cash against a B2B Sale bill
# ════════════════════════════════════════════════════════════
class ReceiveB2BSaleBillCashView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def post(self, request):
        sale_id = request.data.get('b2b_sale_bill_id')
        cash_account_id = request.data.get('cash_account')
        amount = request.data.get('amount')
        date = request.data.get('date')

        if not sale_id or not cash_account_id or not amount or not date:
            return Response({'detail': 'b2b_sale_bill_id, cash_account, amount and date are required.'}, status=400)

        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'detail': 'Branch not found.'}, status=404)

        try:
            sale = B2BSale.objects.get(id=sale_id, from_branch=my_branch)
        except B2BSale.DoesNotExist:
            return Response({'detail': 'B2B Sale not found.'}, status=404)

        try:
            cash_account = Account.objects.get(id=cash_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Cash account not found.'}, status=404)

        total_amount = get_b2b_sale_total(sale)
        paid_amount = get_b2b_sale_paid(sale)
        pending_amount = total_amount - paid_amount

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid amount.'}, status=400)

        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)

        if amount > float(pending_amount):
            return Response({'detail': f'Amount exceeds pending balance. Pending: ₹{pending_amount}'}, status=400)

        party_account, _ = get_branch_linked_account(sale.to_branch)
        if not party_account:
            return Response({
                'detail': f'{sale.to_branch.branch_name} — No Sundry Debitor/Creditor account linked in "Branch Master". Link it first.'
            }, status=400)

        # Voucher number — B2BCR prefix, same FY-based sequence pattern
        now = datetime.now()
        fy_start = now.year if now.month >= 4 else now.year - 1
        fy = f"{str(fy_start)[2:]}-{str(fy_start + 1)[2:]}"
        pattern = f"B2BCR/{fy}/"
        last = CashReceipt.objects.filter(branch=my_branch, voucher_no__startswith=pattern).order_by('-id').first()
        last_no = 0
        if last and last.voucher_no:
            try:
                last_no = int(last.voucher_no.split('/')[-1])
            except (ValueError, IndexError):
                last_no = 0
        voucher_no = f"{pattern}{str(last_no + 1).zfill(4)}"
        while CashReceipt.objects.filter(branch=my_branch, voucher_no=voucher_no).exists():
            last_no += 1
            voucher_no = f"{pattern}{str(last_no + 1).zfill(4)}"

        with transaction.atomic():
            receipt = CashReceipt.objects.create(
                branch=my_branch,
                cash_account=cash_account,
                op_account=party_account,
                voucher_no=voucher_no,
                date=date,
                amount=amount,
                narration=f"B2B Sale {sale.sale_no} payment received",
                type='B2BCR',
                b2b_sale=sale,
            )

        remaining = float(pending_amount) - amount
        return Response({
            'success': True,
            'message': f'₹{amount} received against {sale.sale_no}. Remaining: ₹{remaining}',
            'voucher_no': receipt.voucher_no,
            'remaining_pending': remaining,
        }, status=201)


# ════════════════════════════════════════════════════════════
# RECEIVE — Bank against a B2B Sale bill
# ════════════════════════════════════════════════════════════
class ReceiveB2BSaleBillBankView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def post(self, request):
        sale_id = request.data.get('b2b_sale_bill_id')
        bank_account_id = request.data.get('bank_account')
        amount = request.data.get('amount')
        date = request.data.get('date')
        mode = request.data.get('mode', 'UPI')
        cheque_no = request.data.get('cheque_no')
        cheque_date = request.data.get('cheque_date')
        cheque_clear_date = request.data.get('cheque_clear_date')

        if not sale_id or not bank_account_id or not amount or not date:
            return Response({'detail': 'b2b_sale_bill_id, bank_account, amount and date are required.'}, status=400)

        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'detail': 'Branch not found.'}, status=404)

        try:
            sale = B2BSale.objects.get(id=sale_id, from_branch=my_branch)
        except B2BSale.DoesNotExist:
            return Response({'detail': 'B2B Sale not found.'}, status=404)

        try:
            bank_account = Account.objects.get(id=bank_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Bank account not found.'}, status=404)

        total_amount = get_b2b_sale_total(sale)
        paid_amount = get_b2b_sale_paid(sale)
        pending_amount = total_amount - paid_amount

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid amount.'}, status=400)

        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)

        if amount > float(pending_amount):
            return Response({'detail': f'Amount exceeds pending balance. Pending: ₹{pending_amount}'}, status=400)

        if mode == 'CHEQUE' and not cheque_no:
            return Response({'detail': 'Cheque No is required for CHEQUE mode.'}, status=400)

        party_account, _ = get_branch_linked_account(sale.to_branch)
        if not party_account:
            return Response({
                'detail': f'{sale.to_branch.branch_name} — No Sundry Debitor/Creditor account linked in "Branch Master". Link it first.'
            }, status=400)

        now = datetime.now()
        fy_start = now.year if now.month >= 4 else now.year - 1
        fy = f"{str(fy_start)[2:]}-{str(fy_start + 1)[2:]}"
        pattern = f"B2BBR/{fy}/"
        last = BankReceipt.objects.filter(branch=my_branch, voucher_no__startswith=pattern).order_by('-id').first()
        last_no = 0
        if last and last.voucher_no:
            try:
                last_no = int(last.voucher_no.split('/')[-1])
            except (ValueError, IndexError):
                last_no = 0
        voucher_no = f"{pattern}{str(last_no + 1).zfill(4)}"
        while BankReceipt.objects.filter(branch=my_branch, voucher_no=voucher_no).exists():
            last_no += 1
            voucher_no = f"{pattern}{str(last_no + 1).zfill(4)}"

        with transaction.atomic():
            receipt = BankReceipt.objects.create(
                branch=my_branch,
                bank_account=bank_account,
                op_account=party_account,
                voucher_no=voucher_no,
                date=date,
                amount=amount,
                mode=mode,
                cheque_no=cheque_no if mode == 'CHEQUE' else None,
                cheque_date=cheque_date if mode == 'CHEQUE' else None,
                cheque_clear_date=cheque_clear_date if mode == 'CHEQUE' else None,
                narration=f"B2B Sale {sale.sale_no} payment received",
                type='B2BBR',
                b2b_sale=sale,
            )

        remaining = float(pending_amount) - amount
        return Response({
            'success': True,
            'message': f'₹{amount} received against {sale.sale_no}. Remaining: ₹{remaining}',
            'voucher_no': receipt.voucher_no,
            'remaining_pending': remaining,
        }, status=201)
        
        
        
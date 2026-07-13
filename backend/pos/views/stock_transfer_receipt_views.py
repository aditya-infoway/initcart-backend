# pos/views/stock_transfer_receipt_views.py
# ✅ NEW FILE — Stock Transfer credit bill listing + Cash/Bank receipt receiving
# Sirf SUPERADMIN role use kar sakta hai (jaisa stock_transfer_views.py mein
# IsSuperAdminRole already defined hai — same class yahan reuse ho rahi hai)

from datetime import datetime

from django.db import transaction
from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from decimal import Decimal

from pos.models.branch import Branch
from pos.models.account import Account
from pos.models.stock_transfer import StockTransfer
from pos.models.cashreceipt import CashReceipt
from pos.models.bankreceipt import BankReceipt
from pos.views.stock_transfer_views import IsSuperAdminRole 


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
from decimal import Decimal

def get_transfer_total(transfer):
    """
    Total bill amount for a stock transfer.
    Fallback chain (some transfers — especially 'order' type auto-created
    from BranchOrder — never had rate/net_amount populated at all):
      1. item.net_amount (GST-inclusive, set by manual transfer flow)
      2. item.rate * item.quantity (rate = branch_price snapshot)
      3. from_variant.branchPrice (live current price) * item.quantity
      4. from_variant.purchasePrice (live) * item.quantity — last resort
    """
    total = Decimal("0")
    items = transfer.items.select_related('from_variant').all()
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


def get_transfer_paid(transfer):
    """Total already received (cash + bank) against this stock transfer."""
    cash_paid = CashReceipt.objects.filter(stock_transfer=transfer).aggregate(
        total=Sum('amount'))['total'] or 0
    bank_paid = BankReceipt.objects.filter(stock_transfer=transfer).aggregate(
        total=Sum('amount'))['total'] or 0
    return cash_paid + bank_paid


def get_branch_linked_account(to_branch):
    """
    Party account for stock-transfer settlement = the Sundry Debitor/Creditor
    account linked to `to_branch` via Branch Master (Branch.sundry_debitor_account /
    sundry_creditor_account). No auto-create — branch must be linked first.
    Returns (account, type_label) or (None, None) if nothing linked.
    """
    if to_branch.sundry_debitor_account_id:
        return to_branch.sundry_debitor_account, "Sundry Debitor"
    if to_branch.sundry_creditor_account_id:
        return to_branch.sundry_creditor_account, "Sundry Creditor"
    return None, None


# ════════════════════════════════════════════════════════════
# LIST — Stock Transfer bills with pending amount > 0
# ════════════════════════════════════════════════════════════
class StockTransferCreditBillsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def get(self, request):
        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        query = request.GET.get('query', '').strip()

        transfers = StockTransfer.objects.filter(
            from_branch=my_branch,
            status__in=['pending', 'completed'],   # ✅ cancelled excluded
        ).select_related('to_branch').prefetch_related('items')

        if query:
            transfers = transfers.filter(
                Q(transfer_no__icontains=query) |
                Q(to_branch__branch_name__icontains=query)
            )

        bills = []
        for t in transfers:
            total_amount = get_transfer_total(t)
            paid_amount = get_transfer_paid(t)
            pending_amount = total_amount - paid_amount

            if pending_amount <= 0:
                continue

            linked_account, linked_type = get_branch_linked_account(t.to_branch)  # ✅ NEW

            bills.append({
                'id': t.id,
                'billNo': t.transfer_no,
                'transfer_no': t.transfer_no,
                'to_branch_id': t.to_branch_id,
                'to_branch_name': t.to_branch.branch_name,
                'partyName__account_name': t.to_branch.branch_name,
                'linked_account_id': linked_account.id if linked_account else None,      # ✅ NEW
                'linked_account_name': linked_account.account_name if linked_account else None,  # ✅ NEW
                'linked_account_type': linked_type,                                       # ✅ NEW
                'date': str(t.transfer_date),
                'grand_total': float(total_amount),
                'paid_amount': float(paid_amount),
                'pending_amount': float(pending_amount),
            })

        return Response({'success': True, 'bills': bills})


# ════════════════════════════════════════════════════════════
# RECEIVE — Cash against a Stock Transfer bill
# ════════════════════════════════════════════════════════════
class ReceiveStockTransferBillCashView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def post(self, request):
        transfer_id = request.data.get('stock_transfer_bill_id')
        cash_account_id = request.data.get('cash_account')
        amount = request.data.get('amount')
        date = request.data.get('date')

        if not transfer_id or not cash_account_id or not amount or not date:
            return Response({'detail': 'stock_transfer_bill_id, cash_account, amount and date are required.'}, status=400)

        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'detail': 'Branch not found.'}, status=404)

        try:
            transfer = StockTransfer.objects.get(id=transfer_id, from_branch=my_branch)
        except StockTransfer.DoesNotExist:
            return Response({'detail': 'Stock transfer not found.'}, status=404)

        try:
            cash_account = Account.objects.get(id=cash_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Cash account not found.'}, status=404)

        total_amount = get_transfer_total(transfer)
        paid_amount = get_transfer_paid(transfer)
        pending_amount = total_amount - paid_amount

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid amount.'}, status=400)

        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)

        if amount > float(pending_amount):
            return Response({
                'detail': f'Amount exceeds pending balance. Pending: ₹{pending_amount}'
            }, status=400)

        party_account, _ = get_branch_linked_account(transfer.to_branch)   # ✅ CHANGED
        if not party_account:
            return Response({
                'detail': f'{transfer.to_branch.branch_name}No Sundry Debitor/Creditor account linked in "Branch Master". link it first.'
            }, status=400)

        # Voucher number — reuse CR prefix/sequence style
        from pos.models.settings import setting
        settings_obj = setting.objects.filter(branch=my_branch).first()
        prefix = getattr(settings_obj, 'CR', 'CR') if settings_obj else 'CR'
        now = datetime.now()
        fy_start = now.year if now.month >= 4 else now.year - 1
        fy = f"{str(fy_start)[2:]}-{str(fy_start + 1)[2:]}"
        pattern = f"{prefix}/{fy}/"
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
                narration=f"Stock Transfer {transfer.transfer_no} payment received",
                type='STCR',
                stock_transfer=transfer,
            )

        remaining = float(pending_amount) - amount
        return Response({
            'success': True,
            'message': f'₹{amount} received against {transfer.transfer_no}. Remaining: ₹{remaining}',
            'voucher_no': receipt.voucher_no,
            'remaining_pending': remaining,
        }, status=201)


# ════════════════════════════════════════════════════════════
# RECEIVE — Bank against a Stock Transfer bill
# ════════════════════════════════════════════════════════════
class ReceiveStockTransferBillBankView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def post(self, request):
        transfer_id = request.data.get('stock_transfer_bill_id')
        bank_account_id = request.data.get('bank_account')
        amount = request.data.get('amount')
        date = request.data.get('date')
        mode = request.data.get('mode', 'UPI')
        cheque_no = request.data.get('cheque_no')
        cheque_date = request.data.get('cheque_date')
        cheque_clear_date = request.data.get('cheque_clear_date')

        if not transfer_id or not bank_account_id or not amount or not date:
            return Response({'detail': 'stock_transfer_bill_id, bank_account, amount and date are required.'}, status=400)

        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'detail': 'Branch not found.'}, status=404)

        try:
            transfer = StockTransfer.objects.get(id=transfer_id, from_branch=my_branch)
        except StockTransfer.DoesNotExist:
            return Response({'detail': 'Stock transfer not found.'}, status=404)

        try:
            bank_account = Account.objects.get(id=bank_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Bank account not found.'}, status=404)

        total_amount = get_transfer_total(transfer)
        paid_amount = get_transfer_paid(transfer)
        pending_amount = total_amount - paid_amount

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid amount.'}, status=400)

        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)

        if amount > float(pending_amount):
            return Response({
                'detail': f'Amount exceeds pending balance. Pending: ₹{pending_amount}'
            }, status=400)

        if mode == 'CHEQUE' and not cheque_no:
            return Response({'detail': 'Cheque No is required for CHEQUE mode.'}, status=400)

        party_account, _ = get_branch_linked_account(transfer.to_branch) 
        if not party_account:
            return Response({
                'detail': f'{transfer.to_branch.branch_name}No Sundry Debitor/Creditor account linked in "Branch Master". link it first.'
            }, status=400)

        from pos.models.settings import setting
        settings_obj = setting.objects.filter(branch=my_branch).first()
        prefix = getattr(settings_obj, 'BR', 'BR') if settings_obj else 'BR'
        now = datetime.now()
        fy_start = now.year if now.month >= 4 else now.year - 1
        fy = f"{str(fy_start)[2:]}-{str(fy_start + 1)[2:]}"
        pattern = f"{prefix}/{fy}/"
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
                narration=f"Stock Transfer {transfer.transfer_no} payment received",
                type='STBR',
                stock_transfer=transfer,
            )

        remaining = float(pending_amount) - amount
        return Response({
            'success': True,
            'message': f'₹{amount} received against {transfer.transfer_no}. Remaining: ₹{remaining}',
            'voucher_no': receipt.voucher_no,
            'remaining_pending': remaining,
        }, status=201)
# pos/views/stock_return_receipt_views.py
# Branch receives cash/bank payment FROM company against a Stock Return
# (mirror of stock_transfer_receipt_views.py — direction reversed)

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from pos.models.branch import Branch
from pos.models.account import Account
from pos.models.stock_return import StockReturn
from pos.models.cashreceipt import CashReceipt
from pos.models.bankreceipt import BankReceipt
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee 


def get_return_total(stock_return):
    """Sum of net_amount across all items of a return — already GST-computed at creation."""    
    total = Decimal("0")
    for item in stock_return.items.all():
        total += Decimal(str(item.net_amount or 0))
    return total


def get_return_paid(stock_return):
    """Total already received (cash + bank) against this stock return."""
    cash_paid = CashReceipt.objects.filter(stock_return=stock_return).aggregate(
        total=Sum('amount'))['total'] or 0
    bank_paid = BankReceipt.objects.filter(stock_return=stock_return).aggregate(
        total=Sum('amount'))['total'] or 0
    return Decimal(str(cash_paid)) + Decimal(str(bank_paid))


def get_own_sundry_creditor_main(branch):
    """Branch's own 'Sundry Creditor(Main)' account — must already be created."""
    return Account.objects.filter(branch=branch, group='Sundry Creditor(Main)').first()


# ════════════════════════════════════════════════════════════
# LIST — Stock Return bills with pending amount > 0 (branch's own)
# ════════════════════════════════════════════════════════════
class StockReturnCreditBillsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee ]

    def get(self, request):
        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        query = request.GET.get('query', '').strip()

        returns = StockReturn.objects.filter(
            branch=my_branch,
        ).exclude(status__in=['cancelled', 'rejected']).select_related('to_branch').prefetch_related('items')

        if query:
            returns = returns.filter(
                Q(return_no__icontains=query) | Q(to_branch__branch_name__icontains=query)
            )

        party_account = get_own_sundry_creditor_main(my_branch)

        bills = []
        for r in returns:
            total_amount = get_return_total(r)
            paid_amount = get_return_paid(r)
            pending_amount = total_amount - paid_amount

            if pending_amount <= 0:
                continue

            bills.append({
                'id': r.id,
                'return_no': r.return_no,
                'billNo': r.return_no,
                'to_branch_name': r.to_branch.branch_name,
                'partyName__account_name': r.to_branch.branch_name,
                'linked_account_id': party_account.id if party_account else None,
                'linked_account_name': party_account.account_name if party_account else None,
                'date': str(r.return_date),
                'grand_total': float(total_amount),
                'paid_amount': float(paid_amount),
                'pending_amount': float(pending_amount),
            })

        return Response({'success': True, 'bills': bills})


# ════════════════════════════════════════════════════════════
# RECEIVE — Cash against a Stock Return
# ════════════════════════════════════════════════════════════
class ReceiveStockReturnBillCashView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee ]

    def post(self, request):
        return_id = request.data.get('stock_return_bill_id')
        cash_account_id = request.data.get('cash_account')
        amount = request.data.get('amount')
        date = request.data.get('date')

        if not return_id or not cash_account_id or not amount or not date:
            return Response({'detail': 'stock_return_bill_id, cash_account, amount and date are required.'}, status=400)

        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'detail': 'Branch not found.'}, status=404)

        try:
            stock_return = StockReturn.objects.get(id=return_id, branch=my_branch)
        except StockReturn.DoesNotExist:
            return Response({'detail': 'Stock return not found.'}, status=404)

        try:
            cash_account = Account.objects.get(id=cash_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Cash account not found.'}, status=404)

        party_account = get_own_sundry_creditor_main(my_branch)
        if not party_account:
            return Response({
                'detail': 'Please create a Sundry Creditor(Main) account for this branch first.'
            }, status=400)

        total_amount = get_return_total(stock_return)
        paid_amount = get_return_paid(stock_return)
        pending_amount = total_amount - paid_amount

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid amount.'}, status=400)

        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)
        if amount > float(pending_amount):
            return Response({'detail': f'Amount exceeds pending balance. Pending: ₹{pending_amount}'}, status=400)

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
                narration=f"Stock Return {stock_return.return_no} payment received",
                type='STRCR',
                stock_return=stock_return,
            )

        remaining = float(pending_amount) - amount
        return Response({
            'success': True,
            'message': f'₹{amount} received against {stock_return.return_no}. Remaining: ₹{remaining}',
            'voucher_no': receipt.voucher_no,
            'remaining_pending': remaining,
        }, status=201)


# ════════════════════════════════════════════════════════════
# RECEIVE — Bank against a Stock Return
# ════════════════════════════════════════════════════════════
class ReceiveStockReturnBillBankView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee ]

    def post(self, request):
        return_id = request.data.get('stock_return_bill_id')
        bank_account_id = request.data.get('bank_account')
        amount = request.data.get('amount')
        date = request.data.get('date')
        mode = request.data.get('mode', 'UPI')
        cheque_no = request.data.get('cheque_no')
        cheque_date = request.data.get('cheque_date')
        cheque_clear_date = request.data.get('cheque_clear_date')

        if not return_id or not bank_account_id or not amount or not date:
            return Response({'detail': 'stock_return_bill_id, bank_account, amount and date are required.'}, status=400)

        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'detail': 'Branch not found.'}, status=404)

        try:
            stock_return = StockReturn.objects.get(id=return_id, branch=my_branch)
        except StockReturn.DoesNotExist:
            return Response({'detail': 'Stock return not found.'}, status=404)

        try:
            bank_account = Account.objects.get(id=bank_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Bank account not found.'}, status=404)

        party_account = get_own_sundry_creditor_main(my_branch)
        if not party_account:
            return Response({
                'detail': 'Please create a Sundry Creditor(Main) account for this branch first.'
            }, status=400)

        total_amount = get_return_total(stock_return)
        paid_amount = get_return_paid(stock_return)
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
                narration=f"Stock Return {stock_return.return_no} payment received",
                type='STRBR',
                stock_return=stock_return,
            )

        remaining = float(pending_amount) - amount
        return Response({
            'success': True,
            'message': f'₹{amount} received against {stock_return.return_no}. Remaining: ₹{remaining}',
            'voucher_no': receipt.voucher_no,
            'remaining_pending': remaining,
        }, status=201)
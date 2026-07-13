# pos/views/stock_return_refund_views.py
# ✅ FIXED — No stock_return FK dependency

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
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.views.stock_transfer_views import IsSuperAdminRole
from pos.views.stock_transfer_receipt_views import get_branch_linked_account


def get_return_total(stock_return):
    """Sum of net_amount across all items of a return."""
    total = Decimal("0")
    for item in stock_return.items.all():
        total += Decimal(str(item.net_amount or 0))
    return total


def get_return_refund_paid(stock_return):
    """
    Total already refunded (cash + bank) by superadmin against this return.
    ✅ FIX: Since CashPayment/BankPayment don't have stock_return FK,
    we find payments by type + narration.
    """
    cash_paid = CashPayment.objects.filter(
        branch=stock_return.to_branch,
        type='STRCP',
        narration__icontains=stock_return.return_no
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    bank_paid = BankPayment.objects.filter(
        branch=stock_return.to_branch,
        type='STRBP',
        narration__icontains=stock_return.return_no
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    return cash_paid + bank_paid


# ════════════════════════════════════════════════════════════
# LIST — Stock Return refunds pending, superadmin side
# ════════════════════════════════════════════════════════════
class StockReturnRefundBillsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

    def get(self, request):
        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        query = request.GET.get('query', '').strip()

        returns = StockReturn.objects.filter(
            to_branch=my_branch,
            status='received',
        ).select_related('branch').prefetch_related('items')

        if query:
            returns = returns.filter(
                Q(return_no__icontains=query) |
                Q(branch__branch_name__icontains=query)
            )

        bills = []
        for r in returns:
            total_amount = get_return_total(r)
            paid_amount = get_return_refund_paid(r)
            pending_amount = total_amount - paid_amount

            if pending_amount <= 0:
                continue

            linked_account, linked_type = get_branch_linked_account(r.branch)

            bills.append({
                'id': r.id,
                'billNo': r.return_no,
                'return_no': r.return_no,
                'from_branch_id': r.branch_id,
                'from_branch_name': r.branch.branch_name,
                'partyName__account_name': r.branch.branch_name,
                'linked_account_id': linked_account.id if linked_account else None,
                'linked_account_name': linked_account.account_name if linked_account else None,
                'linked_account_type': linked_type,
                'date': str(r.return_date),
                'grand_total': float(total_amount),
                'paid_amount': float(paid_amount),
                'pending_amount': float(pending_amount),
            })

        return Response({'success': True, 'bills': bills})


# ════════════════════════════════════════════════════════════
# PAY — Cash refund against a Stock Return
# ════════════════════════════════════════════════════════════
class PayStockReturnBillCashView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

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
            stock_return = StockReturn.objects.get(id=return_id, to_branch=my_branch, status='received')
        except StockReturn.DoesNotExist:
            return Response({'detail': 'Stock return not found or not yet received.'}, status=404)

        try:
            cash_account = Account.objects.get(id=cash_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Cash account not found.'}, status=404)

        party_account, _ = get_branch_linked_account(stock_return.branch)
        if not party_account:
            return Response({
                'detail': f'{stock_return.branch.branch_name} has no Sundry Debitor/Creditor account linked in "Branch Master". Link it first.'
            }, status=400)

        total_amount = get_return_total(stock_return)
        paid_amount = get_return_refund_paid(stock_return)
        pending_amount = total_amount - paid_amount

        try:
            amount = Decimal(str(amount))
        except Exception:
            return Response({'detail': 'Invalid amount.'}, status=400)

        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)
        if amount > pending_amount:
            return Response({'detail': f'Amount exceeds pending balance. Pending: ₹{pending_amount}'}, status=400)

        from pos.models.settings import setting
        settings_obj = setting.objects.filter(branch=my_branch).first()
        prefix = getattr(settings_obj, 'CP', 'CP') if settings_obj else 'CP'
        last = CashPayment.objects.filter(branch=my_branch).order_by('-id').first()
        last_no = 0
        if last and last.voucher_no:
            try:
                parts = last.voucher_no.split('/')
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0
        now = datetime.now()
        fy_start = now.year if now.month >= 4 else now.year - 1
        fy = f"{str(fy_start)[2:]}-{str(fy_start + 1)[2:]}"
        voucher_no = f"{prefix}/{fy}/{str(last_no + 1).zfill(4)}"

        with transaction.atomic():
            payment = CashPayment.objects.create(
                branch=my_branch,
                cash_account=cash_account,
                op_account=party_account,
                voucher_no=voucher_no,
                date=date,
                amount=amount,
                narration=f"Refund against Stock Return {stock_return.return_no}",
                type='STRCP',
                # ✅ No stock_return FK — using narration + type for tracking
            )

        remaining = pending_amount - amount
        return Response({
            'success': True,
            'message': f'₹{amount} refunded against {stock_return.return_no}. Remaining: ₹{remaining}',
            'voucher_no': payment.voucher_no,
            'remaining_pending': float(remaining),
        }, status=201)


# ════════════════════════════════════════════════════════════
# PAY — Bank refund against a Stock Return
# ════════════════════════════════════════════════════════════
class PayStockReturnBillBankView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperAdminRole]

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
            stock_return = StockReturn.objects.get(id=return_id, to_branch=my_branch, status='received')
        except StockReturn.DoesNotExist:
            return Response({'detail': 'Stock return not found or not yet received.'}, status=404)

        try:
            bank_account = Account.objects.get(id=bank_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Bank account not found.'}, status=404)

        party_account, _ = get_branch_linked_account(stock_return.branch)
        if not party_account:
            return Response({
                'detail': f'{stock_return.branch.branch_name} has no Sundry Debitor/Creditor account linked in "Branch Master". Link it first.'
            }, status=400)

        total_amount = get_return_total(stock_return)
        paid_amount = get_return_refund_paid(stock_return)
        pending_amount = total_amount - paid_amount

        try:
            amount = Decimal(str(amount))
        except Exception:
            return Response({'detail': 'Invalid amount.'}, status=400)

        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)
        if amount > pending_amount:
            return Response({'detail': f'Amount exceeds pending balance. Pending: ₹{pending_amount}'}, status=400)
        if mode == 'CHEQUE' and not cheque_no:
            return Response({'detail': 'Cheque No is required for CHEQUE mode.'}, status=400)

        from pos.models.settings import setting
        settings_obj = setting.objects.filter(branch=my_branch).first()
        prefix = getattr(settings_obj, 'BP', 'BP') if settings_obj else 'BP'
        last = BankPayment.objects.filter(branch=my_branch).order_by('-id').first()
        last_no = 0
        if last and last.voucher_no:
            try:
                parts = last.voucher_no.split('/')
                if len(parts) >= 3:
                    last_no = int(parts[-1])
            except (ValueError, IndexError):
                last_no = 0
        now = datetime.now()
        fy_start = now.year if now.month >= 4 else now.year - 1
        fy = f"{str(fy_start)[2:]}-{str(fy_start + 1)[2:]}"
        voucher_no = f"{prefix}/{fy}/{str(last_no + 1).zfill(4)}"

        with transaction.atomic():
            payment = BankPayment.objects.create(
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
                narration=f"Refund against Stock Return {stock_return.return_no}",
                type='STRBP',
                #  No stock_return FK — using narration + type for tracking
            )

        remaining = pending_amount - amount
        return Response({
            'success': True,
            'message': f'₹{amount} refunded against {stock_return.return_no}. Remaining: ₹{remaining}',
            'voucher_no': payment.voucher_no,
            'remaining_pending': float(remaining),
        }, status=201)
        
        
        
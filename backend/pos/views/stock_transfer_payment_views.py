# pos/views/stock_transfer_payment_views.py
# ✅ NEW FILE — "Stock Received" bill listing + Cash/Bank payment
#
# This is the RECEIVE side (normal branches paying superadmin for stock
# they received) — the mirror of stock_transfer_receipt_views.py (which
# is the SEND side, superadmin receiving payment from branches).
#
# Key rule: party account is ALWAYS the paying branch's own single
# "Sundry Creditor(Main)" account — there is exactly one per branch,
# no branch-to-branch linking involved (unlike the SEND side).
#
# Only transfers that are FULLY VERIFIED (all items is_stock_updated=True)
# count as a payable bill — matches the ledger rule in
# LedgerReport_serializers.py (group == "Sundry Creditor(Main)").

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from pos.models.branch import Branch
from pos.models.account import Account
from pos.models.stock_transfer import StockTransfer
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.views.stock_transfer_receipt_views import get_transfer_total  # ✅ reuse


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
def get_transfer_paid_by_receiver(transfer):
    """Total already paid (cash + bank) by the receiving branch against this transfer."""
    cash_paid = CashPayment.objects.filter(stock_transfer=transfer).aggregate(
        total=Sum('amount'))['total'] or Decimal('0')
    bank_paid = BankPayment.objects.filter(stock_transfer=transfer).aggregate(
        total=Sum('amount'))['total'] or Decimal('0')
    return cash_paid + bank_paid


def get_main_sundry_creditor_account(branch):
    """
    Every receiving branch has exactly ONE "Sundry Creditor(Main)" account
    (enforced by AccountSerializer.validate — only one per branch allowed).
    No auto-create here — branch must create it first (same rule already
    enforced in VerifyStockTransferItemView before stock can be verified).
    """
    return Account.objects.filter(branch=branch, group='Sundry Creditor(Main)').first()


def is_fully_verified(transfer):
    items = list(transfer.items.all())
    return bool(items) and all(i.is_stock_updated for i in items)


# ════════════════════════════════════════════════════════════
# LIST — Stock Received bills with pending amount > 0
# ════════════════════════════════════════════════════════════
class StockReceivedBillsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            my_branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Branch not found'}, status=404)

        # Superadmin never "receives" stock (it's always from_branch for them)
        # — query naturally returns empty, but guard explicitly for clarity.
        if request.user.role == 'superadmin':
            return Response({'success': True, 'bills': []})

        query = request.GET.get('query', '').strip()

        main_account = get_main_sundry_creditor_account(my_branch)

        transfers = StockTransfer.objects.filter(
            to_branch=my_branch,
            status__in=['pending', 'completed'],
        ).select_related('from_branch').prefetch_related('items')

        if query:
            transfers = transfers.filter(transfer_no__icontains=query)

        bills = []
        for t in transfers:
            if not is_fully_verified(t):
                continue  # matches ledger rule — only counted once fully verified

            total_amount = get_transfer_total(t)
            paid_amount = get_transfer_paid_by_receiver(t)
            pending_amount = total_amount - paid_amount

            if pending_amount <= 0:
                continue

            bills.append({
                'id': t.id,
                'billNo': t.transfer_no,
                'transfer_no': t.transfer_no,
                'from_branch_name': t.from_branch.branch_name,
                'partyName__account_name': main_account.account_name if main_account else None,
                'main_account_id': main_account.id if main_account else None,
                'main_account_name': main_account.account_name if main_account else None,
                'date': str(t.transfer_date),
                'grand_total': float(total_amount),
                'paid_amount': float(paid_amount),
                'pending_amount': float(pending_amount),
            })

        return Response({'success': True, 'bills': bills})


# ════════════════════════════════════════════════════════════
# PAY — Cash against a Stock Received bill
# ════════════════════════════════════════════════════════════
class PayStockReceivedBillCashView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

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
            transfer = StockTransfer.objects.get(id=transfer_id, to_branch=my_branch)
        except StockTransfer.DoesNotExist:
            return Response({'detail': 'Stock transfer not found.'}, status=404)

        if not is_fully_verified(transfer):
            return Response({'detail': 'This transfer is not fully verified yet.'}, status=400)

        try:
            cash_account = Account.objects.get(id=cash_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Cash account not found.'}, status=404)

        main_account = get_main_sundry_creditor_account(my_branch)
        if not main_account:
            return Response({
                'detail': 'Please create a "Sundry Creditor(Main)" account for your branch first.'
            }, status=400)

        total_amount = get_transfer_total(transfer)
        paid_amount = get_transfer_paid_by_receiver(transfer)
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
                op_account=main_account,
                voucher_no=voucher_no,
                date=date,
                amount=amount,
                narration=f"Stock Received {transfer.transfer_no} payment to HO",
                type='STCP',
                stock_transfer=transfer,
            )

        remaining = pending_amount - amount
        return Response({
            'success': True,
            'message': f'₹{amount} paid against {transfer.transfer_no}. Remaining: ₹{remaining}',
            'voucher_no': payment.voucher_no,
            'remaining_pending': float(remaining),
        }, status=201)


# ════════════════════════════════════════════════════════════
# PAY — Bank against a Stock Received bill
# ════════════════════════════════════════════════════════════
class PayStockReceivedBillBankView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

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
            transfer = StockTransfer.objects.get(id=transfer_id, to_branch=my_branch)
        except StockTransfer.DoesNotExist:
            return Response({'detail': 'Stock transfer not found.'}, status=404)

        if not is_fully_verified(transfer):
            return Response({'detail': 'This transfer is not fully verified yet.'}, status=400)

        try:
            bank_account = Account.objects.get(id=bank_account_id)
        except Account.DoesNotExist:
            return Response({'detail': 'Bank account not found.'}, status=404)

        main_account = get_main_sundry_creditor_account(my_branch)
        if not main_account:
            return Response({
                'detail': 'Please create a "Sundry Creditor(Main)" account for your branch first.'
            }, status=400)

        total_amount = get_transfer_total(transfer)
        paid_amount = get_transfer_paid_by_receiver(transfer)
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
                op_account=main_account,
                voucher_no=voucher_no,
                date=date,
                amount=amount,
                mode=mode,
                cheque_no=cheque_no if mode == 'CHEQUE' else None,
                cheque_date=cheque_date if mode == 'CHEQUE' else None,
                cheque_clear_date=cheque_clear_date if mode == 'CHEQUE' else None,
                narration=f"Stock Received {transfer.transfer_no} payment to Head Office",
                type='STBP',
                stock_transfer=transfer,
            )

        remaining = pending_amount - amount
        return Response({
            'success': True,
            'message': f'₹{amount} paid against {transfer.transfer_no}. Remaining: ₹{remaining}',
            'voucher_no': payment.voucher_no,
            'remaining_pending': float(remaining),
        }, status=201)
        
        
        
# pos/views/outstanding_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q
from decimal import Decimal

from pos.models.salesentry import SalesMaster
from pos.models.purchaseentry import PurchaseMaster
from pos.models.cashreceipt import CashReceipt
from pos.models.bankreceipt import BankReceipt
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.models.salesreturn import SalesReturnMaster
from pos.models.purchasereturn import PurchaseReturnMaster
from pos.models.branch import Branch


class OutstandingReportAPIView(APIView):
    """
    Outstanding Report:
    - Receivable: Sirf woh Sales bills jinka pending > 0 ho
    - Payable:    Sirf woh Purchase bills jinka pending > 0 ho
    Grand total aur values directly DB se — koi extra calculation nahi
    """
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

        report_type = request.GET.get('type', 'both')
        search = request.GET.get('search', '').strip()

        receivable_data = []
        payable_data = []

        # ══════════════════════════════════════════════
        # RECEIVABLE — Sirf pending sales bills
        # ══════════════════════════════════════════════
        if report_type in ('receivable', 'both'):
            sales_qs = SalesMaster.objects.filter(
                branch=branch
            ).select_related('customer').prefetch_related('items').order_by('-date', '-id')

            if search:
                sales_qs = sales_qs.filter(
                    Q(bill_no__icontains=search) |
                    Q(customer__account_name__icontains=search)
                )

            for bill in sales_qs:
                # Cash receipts against this bill (SCR)
                cash_received = CashReceipt.objects.filter(
                    sales_entry=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                # Bank receipts against this bill (SBR)
                bank_received = BankReceipt.objects.filter(
                    sales_entry=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                total_received = cash_received + bank_received

                # Sales Returns against this bill
                total_returned = SalesReturnMaster.objects.filter(
                    branch=branch,
                    original_bill_no=bill.bill_no
                ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

                # Pending = Grand Total - Received - Returned
                pending = bill.grand_total - total_received - total_returned

                # Sirf pending wale bills show karo
                if pending <= Decimal('0.005'):
                    continue

                receivable_data.append({
                    'id': bill.id,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'bill_no': bill.bill_no,
                    'party_name': bill.customer.account_name,
                    'terms': bill.payment_terms,
                    'no_of_items': bill.items.count(),
                    'total_taxable': float(bill.total_basic),
                    'tax': float(bill.total_tax),
                    'grand_total': float(bill.grand_total),
                    'received': float(total_received + total_returned),
                    'pending': float(pending),
                })

        # ══════════════════════════════════════════════
        # PAYABLE — Sirf pending purchase bills
        # ══════════════════════════════════════════════
        if report_type in ('payable', 'both'):
            purchase_qs = PurchaseMaster.objects.filter(
                branch=branch
            ).select_related('partyName').prefetch_related('items').order_by('-date', '-id')

            if search:
                purchase_qs = purchase_qs.filter(
                    Q(billNo__icontains=search) |
                    Q(partyName__account_name__icontains=search)
                )

            for bill in purchase_qs:
                # Cash payments against this bill (PCP)
                cash_paid = CashPayment.objects.filter(
                    purchase=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                # Bank payments against this bill (PBP)
                bank_paid = BankPayment.objects.filter(
                    purchase=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                total_paid = cash_paid + bank_paid

                # Purchase Returns against this bill
                total_returned = PurchaseReturnMaster.objects.filter(
                    branch=branch,
                    original_bill_no=bill.billNo
                ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

                # Pending = Grand Total - Paid - Returned
                pending = bill.grand_total - total_paid - total_returned

                # Sirf pending wale bills show karo
                if pending <= Decimal('0.005'):
                    continue

                payable_data.append({
                    'id': bill.id,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'bill_no': bill.billNo,
                    'party_name': bill.partyName.account_name if bill.partyName else '-',
                    'terms': bill.terms,
                    'no_of_items': bill.items.count(),
                    'total_taxable': float(bill.total_basic),
                    'tax': float(bill.total_tax),
                    'grand_total': float(bill.grand_total),
                    'paid': float(total_paid + total_returned),
                    'pending': float(pending),
                })

        # ══════════════════════════════════════════════
        # SUMMARY — Sirf pending bills ka total
        # ══════════════════════════════════════════════
        receivable_summary = {
            'total_bills': len(receivable_data),
            'total_grand': sum(r['grand_total'] for r in receivable_data),
            'total_received': sum(r['received'] for r in receivable_data),
            'total_pending': sum(r['pending'] for r in receivable_data),
        }

        payable_summary = {
            'total_bills': len(payable_data),
            'total_grand': sum(p['grand_total'] for p in payable_data),
            'total_paid': sum(p['paid'] for p in payable_data),
            'total_pending': sum(p['pending'] for p in payable_data),
        }

        return Response({
            'receivable': receivable_data,
            'payable': payable_data,
            'receivable_summary': receivable_summary,
            'payable_summary': payable_summary,
        })
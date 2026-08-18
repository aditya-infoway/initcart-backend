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

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


class OutstandingReportAPIView(APIView):
    """
    Outstanding Report:
    - Receivable: Sirf woh Sales bills jinka pending > 0 ho
    - Payable:    Sirf woh Purchase bills jinka pending > 0 ho
    Grand total aur values directly DB se — koi extra calculation nahi
    """
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/outStandingReport"  # ✅ ADD: Frontend route

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
            }, status=400)

        # ✅ FIX: Employee ko bhi branch_id override allow karo (agar superadmin branch hai)
        branch_id_param = request.GET.get('branch_id')
        if branch_id_param:
            # Superadmin hamesha allow
            if is_superadmin:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
            # ✅ Employee allow karo agar uski branch superadmin branch hai
            elif is_employee:
                # Check if employee's branch is superadmin branch
                employee_branch = user.get_effective_branch()
                if employee_branch and employee_branch.user and employee_branch.user.role == 'superadmin':
                    try:
                        branch = Branch.objects.get(id=branch_id_param)
                    except Branch.DoesNotExist:
                        return Response({'error': 'Branch not found'}, status=404)
                else:
                    # Employee ki branch superadmin branch nahi hai, toh apni branch hi use kare
                    pass

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
                cash_received = CashReceipt.objects.filter(
                    sales_entry=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                bank_received = BankReceipt.objects.filter(
                    sales_entry=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                total_received = cash_received + bank_received

                total_returned = SalesReturnMaster.objects.filter(
                    branch=branch,
                    original_bill_no=bill.bill_no
                ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

                pending = bill.grand_total - total_received - total_returned

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
                cash_paid = CashPayment.objects.filter(
                    purchase=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                bank_paid = BankPayment.objects.filter(
                    purchase=bill
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                total_paid = cash_paid + bank_paid

                total_returned = PurchaseReturnMaster.objects.filter(
                    branch=branch,
                    original_bill_no=bill.billNo
                ).aggregate(total=Sum('grand_total'))['total'] or Decimal('0')

                pending = bill.grand_total - total_paid - total_returned

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
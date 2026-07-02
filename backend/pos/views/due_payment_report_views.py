# pos/views/due_payment_report_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from decimal import Decimal
from datetime import date


class DuePaymentReportAPIView(APIView):
    """
    Due Payment Report — saari 4 types ke credit bills jinka payment pending hai.

    Query params:
      - overdue_only=true   → sirf wo bills jinka due_date aaj se pehle hai
      - type=purchase|sales|purchase_return|sales_return  → filter by type
      - search=<text>       → party name / bill no se search
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from pos.models.purchaseentry import PurchaseMaster, PurchaseItem
        from pos.models.purchasereturn import PurchaseReturnMaster, PurchaseReturnItem
        from pos.models.salesentry import SalesMaster, SalesItem
        from pos.models.salesreturn import SalesReturnMaster, SalesReturnItem
        from pos.models.cashpayment import CashPayment
        from pos.models.bankpayment import BankPayment
        from pos.models.cashreceipt import CashReceipt
        from pos.models.bankreceipt import BankReceipt

        branch = request.user.branch
        today = date.today()

        overdue_only = request.GET.get('overdue_only', 'false').lower() == 'true'
        filter_type = request.GET.get('type', '').strip().lower()
        search = request.GET.get('search', '').strip()

        results = []

        # ─────────────────────────────────────────────────────────────
        # 1. PURCHASE ENTRY — Credit bills
        # ─────────────────────────────────────────────────────────────
        if not filter_type or filter_type == 'purchase':
            purchases = PurchaseMaster.objects.filter(
                branch=branch,
                terms__iexact='credit',
                dueDate__isnull=False,
            ).select_related('partyName')

            if overdue_only:
                purchases = purchases.filter(dueDate__lt=today)

            if search:
                purchases = purchases.filter(
                    Q(billNo__icontains=search) |
                    Q(partyName__account_name__icontains=search)
                )

            for bill in purchases:
                # Paid via PCP/PBP
                total_paid = (
                    CashPayment.objects.filter(purchase=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )
                total_paid += (
                    BankPayment.objects.filter(purchase=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )

                # Unsettled credit returns
                from pos.models.purchasereturn import PurchaseReturnMaster as PRM
                all_returns = PRM.objects.filter(
                    branch=branch, original_bill_no=bill.billNo
                )
                credit_returns_unsettled = Decimal('0')
                for pr in all_returns.filter(payment_terms__iexact='credit'):
                    pr_receipts = (
                        CashReceipt.objects.filter(purchase_return=pr)
                        .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                    )
                    pr_receipts += (
                        BankReceipt.objects.filter(purchase_return=pr)
                        .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                    )
                    if pr_receipts < pr.grand_total:
                        credit_returns_unsettled += (pr.grand_total - pr_receipts)

                pending = bill.grand_total - total_paid - credit_returns_unsettled

                if pending <= Decimal('0.005'):
                    continue  # fully paid — skip

                item_count = PurchaseItem.objects.filter(purchase=bill).count()
                days_overdue = (today - bill.dueDate).days if bill.dueDate and bill.dueDate < today else 0

                results.append({
                    'id': bill.id,
                    'type': 'Purchase',
                    'type_label': 'Purchase Bill',
                    'due_date': bill.dueDate.strftime('%Y-%m-%d') if bill.dueDate else None,
                    'bill_date': bill.date.strftime('%Y-%m-%d'),
                    'party_name': bill.partyName.account_name if bill.partyName else '-',
                    'party_id': bill.partyName.id if bill.partyName else None,
                    'bill_number': bill.billNo,
                    'purchase_bill_number': bill.purchasebill_no or bill.billNo,
                    'item_count': item_count,
                    'total_amount': float(bill.grand_total),
                    'received_amount': float(total_paid),
                    'pending_amount': float(pending),
                    'days_overdue': days_overdue,
                    'is_overdue': bill.dueDate is not None and bill.dueDate < today,
                })

        # ─────────────────────────────────────────────────────────────
        # 2. PURCHASE RETURN — Credit returns
        # ─────────────────────────────────────────────────────────────
        if not filter_type or filter_type == 'purchase_return':
            from pos.models.purchasereturn import PurchaseReturnMaster as PRM

            pr_bills = PRM.objects.filter(
                branch=branch,
                payment_terms__iexact='credit',
                dueDate__isnull=False,
            ).select_related('party')

            if overdue_only:
                pr_bills = pr_bills.filter(dueDate__lt=today)

            if search:
                pr_bills = pr_bills.filter(
                    Q(return_no__icontains=search) |
                    Q(party__account_name__icontains=search) |
                    Q(original_bill_no__icontains=search)
                )

            for bill in pr_bills:
                total_received = (
                    CashReceipt.objects.filter(purchase_return=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )
                total_received += (
                    BankReceipt.objects.filter(purchase_return=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )

                pending = bill.grand_total - total_received
                if pending <= Decimal('0.005'):
                    continue

                # Decide whether to show (same logic as PurchaseReturnCreditBillsAPIView)
                original_bill_terms = 'unknown'
                original_bill_paid = Decimal('0')
                try:
                    orig = PurchaseMaster.objects.get(
                        billNo=bill.original_bill_no, branch=branch
                    )
                    original_bill_terms = orig.terms.lower()
                    if original_bill_terms == 'credit':
                        original_bill_paid = (
                            CashPayment.objects.filter(purchase=orig)
                            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                        )
                        original_bill_paid += (
                            BankPayment.objects.filter(purchase=orig)
                            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                        )
                except PurchaseMaster.DoesNotExist:
                    pass

                show = False
                if original_bill_terms in ['cash', 'bank']:
                    show = True
                elif original_bill_terms == 'credit':
                    show = original_bill_paid > 0 or total_received > 0

                if not show:
                    continue

                from pos.models.purchasereturn import PurchaseReturnItem as PRI
                item_count = PRI.objects.filter(purchase_return=bill).count()
                days_overdue = (today - bill.dueDate).days if bill.dueDate and bill.dueDate < today else 0

                results.append({
                    'id': bill.id,
                    'type': 'PurchaseReturn',
                    'type_label': 'Purchase Return',
                    'due_date': bill.dueDate.strftime('%Y-%m-%d') if bill.dueDate else None,
                    'bill_date': bill.date.strftime('%Y-%m-%d'),
                    'party_name': bill.party.account_name,
                    'party_id': bill.party.id,
                    'bill_number': bill.return_no,
                    'purchase_bill_number': bill.original_bill_no,
                    'item_count': item_count,
                    'total_amount': float(bill.grand_total),
                    'received_amount': float(total_received),
                    'pending_amount': float(pending),
                    'days_overdue': days_overdue,
                    'is_overdue': bill.dueDate is not None and bill.dueDate < today,
                })

        # ─────────────────────────────────────────────────────────────
        # 3. SALES ENTRY — Credit bills
        # ─────────────────────────────────────────────────────────────
        if not filter_type or filter_type == 'sales':
            from pos.models.salesreturn import SalesReturnMaster as SRM

            sales_bills = SalesMaster.objects.filter(
                branch=branch,
                payment_terms__iexact='credit',
                dueDate__isnull=False,
            ).select_related('customer')

            if overdue_only:
                sales_bills = sales_bills.filter(dueDate__lt=today)

            if search:
                sales_bills = sales_bills.filter(
                    Q(bill_no__icontains=search) |
                    Q(customer__account_name__icontains=search)
                )

            for bill in sales_bills:
                total_received = (
                    CashReceipt.objects.filter(sales_entry=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )
                total_received += (
                    BankReceipt.objects.filter(sales_entry=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )

                all_returns = SRM.objects.filter(
                    branch=branch, original_bill_no=bill.bill_no
                )
                credit_returns_unsettled = Decimal('0')
                for sr in all_returns.filter(payment_terms__iexact='credit'):
                    sr_payments = (
                        CashPayment.objects.filter(sales_return=sr)
                        .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                    )
                    sr_payments += (
                        BankPayment.objects.filter(sales_return=sr)
                        .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                    )
                    if sr_payments < sr.grand_total:
                        credit_returns_unsettled += (sr.grand_total - sr_payments)

                pending = bill.grand_total - total_received - credit_returns_unsettled
                if pending <= Decimal('0.005'):
                    continue

                item_count = SalesItem.objects.filter(sales=bill).count()
                days_overdue = (today - bill.dueDate).days if bill.dueDate and bill.dueDate < today else 0

                results.append({
                    'id': bill.id,
                    'type': 'Sales',
                    'type_label': 'Sales Bill',
                    'due_date': bill.dueDate.strftime('%Y-%m-%d') if bill.dueDate else None,
                    'bill_date': bill.date.strftime('%Y-%m-%d'),
                    'party_name': bill.customer.account_name,
                    'party_id': bill.customer.id,
                    'bill_number': bill.bill_no,
                    'purchase_bill_number': None,
                    'item_count': item_count,
                    'total_amount': float(bill.grand_total),
                    'received_amount': float(total_received),
                    'pending_amount': float(pending),
                    'days_overdue': days_overdue,
                    'is_overdue': bill.dueDate is not None and bill.dueDate < today,
                })

        # ─────────────────────────────────────────────────────────────
        # 4. SALES RETURN — Credit returns
        # ─────────────────────────────────────────────────────────────
        if not filter_type or filter_type == 'sales_return':
            from pos.models.salesreturn import SalesReturnMaster as SRM
            from pos.models.salesreturn import SalesReturnItem as SRI

            sr_bills = SRM.objects.filter(
                branch=branch,
                payment_terms__iexact='credit',
                dueDate__isnull=False,
            ).select_related('customer')

            if overdue_only:
                sr_bills = sr_bills.filter(dueDate__lt=today)

            if search:
                sr_bills = sr_bills.filter(
                    Q(return_no__icontains=search) |
                    Q(customer__account_name__icontains=search) |
                    Q(original_bill_no__icontains=search)
                )

            for bill in sr_bills:
                total_paid = (
                    CashPayment.objects.filter(sales_return=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )
                total_paid += (
                    BankPayment.objects.filter(sales_return=bill)
                    .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )

                pending = bill.grand_total - total_paid
                if pending <= Decimal('0.005'):
                    continue

                # Decide whether to show (same logic as SalesReturnCreditBillsAPIView)
                original_bill_terms = 'unknown'
                original_bill_received = Decimal('0')
                try:
                    orig = SalesMaster.objects.get(
                        bill_no=bill.original_bill_no, branch=branch
                    )
                    original_bill_terms = orig.payment_terms.lower()
                    if original_bill_terms == 'credit':
                        original_bill_received = (
                            CashReceipt.objects.filter(sales_entry=orig)
                            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                        )
                        original_bill_received += (
                            BankReceipt.objects.filter(sales_entry=orig)
                            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
                        )
                except SalesMaster.DoesNotExist:
                    pass

                show = False
                if original_bill_terms in ['cash', 'bank']:
                    show = True
                elif original_bill_terms == 'credit':
                    show = original_bill_received > 0 or total_paid > 0

                if not show:
                    continue

                item_count = SRI.objects.filter(sales_return=bill).count()
                days_overdue = (today - bill.dueDate).days if bill.dueDate and bill.dueDate < today else 0

                results.append({
                    'id': bill.id,
                    'type': 'SalesReturn',
                    'type_label': 'Sales Return',
                    'due_date': bill.dueDate.strftime('%Y-%m-%d') if bill.dueDate else None,
                    'bill_date': bill.date.strftime('%Y-%m-%d'),
                    'party_name': bill.customer.account_name,
                    'party_id': bill.customer.id,
                    'bill_number': bill.return_no,
                    'purchase_bill_number': None,
                    'item_count': item_count,
                    'total_amount': float(bill.grand_total),
                    'received_amount': float(total_paid),
                    'pending_amount': float(pending),
                    'days_overdue': days_overdue,
                    'is_overdue': bill.dueDate is not None and bill.dueDate < today,
                })

        # ─── Sort: overdue first, then by due_date ascending ───
        results.sort(key=lambda x: (
            0 if x['is_overdue'] else 1,
            x['due_date'] or '9999-12-31'
        ))

        # ─── Summary totals ───
        total_pending = sum(r['pending_amount'] for r in results)
        total_overdue_count = sum(1 for r in results if r['is_overdue'])
        total_overdue_amount = sum(r['pending_amount'] for r in results if r['is_overdue'])

        return Response({
            'summary': {
                'total_bills': len(results),
                'total_pending_amount': round(total_pending, 2),
                'overdue_count': total_overdue_count,
                'overdue_amount': round(total_overdue_amount, 2),
                'report_date': today.strftime('%Y-%m-%d'),
            },
            'bills': results,
        }, status=status.HTTP_200_OK)
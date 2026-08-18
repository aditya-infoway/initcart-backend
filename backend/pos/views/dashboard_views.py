# pos/views/dashboard_views.py

from pos.models.purchasereturn import PurchaseReturnMaster
from pos.models.salesreturn import SalesReturnMaster
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated  # ✅ IsAuthenticated hi rakho
from django.utils.timezone import now
from datetime import timedelta
from decimal import Decimal
from django.db.models import Sum
from pos.models.salesentry import SalesMaster
from pos.models.purchaseentry import PurchaseMaster
from pos.models.account import Account
from pos.models.items import items
from pos.serializers.deshboard_serializers import SalesDeshboardSerializers
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.models.cashreceipt import CashReceipt
from pos.models.bankreceipt import BankReceipt

from ecommerce.models.order import Order
from ecommerce.models.vendor import Vendor
from pos.models.branch import Branch  # ✅ Add this import


class DashboardSummaryView(APIView):
    """
    Dashboard Summary API
    ✅ IsAuthenticated - sabko access (Superadmin, Branch, Employee)
    ❌ Employee permission check nahi karna kyunki dashboard sabko dikhna chahiye
    """
    
    # ✅ IsAuthenticated hi rakho (Employee permission check ki zaroorat nahi)
    permission_classes = [IsAuthenticated]
    # ❌ page_key mat do - kyunki dashboard sabko dikhna chahiye

    def get(self, request, *args, **kwargs):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        # ✅ Branch selection logic → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=400)

        # ✅ Employee ko bhi branch_id override allow karo
        branch_id_param = request.query_params.get('branch_id')
        if branch_id_param:
            if is_superadmin or is_employee:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)

        today = now().date()
        
        # ---------------- HEADER ----------------
        branch_name = branch.branch_name if branch else ""

        # ---------------- TODAY PAYMENTS ----------------
        today_cash_payment = CashPayment.objects.filter(
            branch=branch,
            date=today
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        today_bank_payment = BankPayment.objects.filter(
            branch=branch,
            date=today
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        total_today_payment = today_cash_payment + today_bank_payment

        # ---------------- TODAY RECEIPTS ----------------
        today_cash_receipt = CashReceipt.objects.filter(
            branch=branch,
            date=today
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        today_bank_receipt = BankReceipt.objects.filter(
            branch=branch,
            date=today
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        total_today_receipt = today_cash_receipt + today_bank_receipt

        # ---------------- TOTAL SALES ----------------
        total_sales = SalesMaster.objects.filter(branch=branch).aggregate(
            total=Sum("grand_total")
        )["total"] or Decimal("0.00")

        # ---------------- TOTAL PURCHASE ----------------
        total_purchase = PurchaseMaster.objects.filter(branch=branch).aggregate(
            total=Sum("grand_total")
        )["total"] or Decimal("0.00")
        
        # ---------------- TOTAL SALES RETURN ----------------
        total_salesreturn = SalesReturnMaster.objects.filter(branch=branch).aggregate(
            total=Sum("grand_total")
        )["total"] or Decimal("0.00")

        # ---------------- TOTAL PURCHASE RETURN ----------------
        total_purchasereturn = PurchaseReturnMaster.objects.filter(branch=branch).aggregate(
            total=Sum("grand_total")
        )["total"] or Decimal("0.00")

        # ---------------- TOTAL RECEIVABLE ----------------
        receivables = Account.objects.filter(
            branch=branch,
            group__in=["Customer"],
            drcr="Cr"
        ).aggregate(
            total=Sum("current_balance")
        )["total"] or Decimal("0.00")

        # ---------------- TOTAL PAYABLE ----------------
        payables = Account.objects.filter(
            branch=branch,
            group__in=["Supplier"],
            drcr="Cr"
        ).aggregate(
            total=Sum("current_balance")
        )["total"] or Decimal("0.00")

        # ---------------- WEBSITE ORDERS ----------------
        total_orders = 0

        try:
            vendor = Vendor.objects.get(user=branch.user) if branch.user else None
            if vendor:
                total_orders = Order.objects.filter(
                    items__vendor=vendor
                ).distinct().count()
        except Vendor.DoesNotExist:
            total_orders = 0

        # ---------------- TOTAL ITEMS ----------------
        total_items = items.objects.filter(branch=branch).count()

        return Response({
            "welcome": f"Welcome {user.username}",
            "branch_name": branch_name,

            # TODAY (flattened for frontend)
            "total_today_payment": float(total_today_payment),
            "total_today_receipt": float(total_today_receipt),

            # MAIN TOTALS
            "total_sales": float(total_sales),
            "total_purchase": float(total_purchase),

            # RETURNS FIXED
            "total_salesreturn": float(total_salesreturn),
            "total_purchasereturn": float(total_purchasereturn),

            # EXTRA
            "total_receivable": float(receivables),
            "total_payable": float(payables),
            "total_items": total_items,

            # WEBSITE ORDERS FIX NAME
            "total_website_orders": total_orders,
        })


def sales_sum(start_date, end_date, branch_filter=None):
    branch_filter = branch_filter or {}
    return SalesMaster.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        **branch_filter
    ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")


def tax_sum(start_date, end_date, branch_filter=None):
    branch_filter = branch_filter or {}
    return SalesMaster.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        **branch_filter
    ).aggregate(total=Sum("total_tax"))["total"] or Decimal("0.00")


def chart_data(start_date, days=6, branch_filter=None):
    branch_filter = branch_filter or {}
    data = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        total = SalesMaster.objects.filter(
            date=day,
            **branch_filter
        ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")
        data.append(float(total))
    return data


def total_profit(start_date, end_date, branch_filter=None):
    branch_filter = branch_filter or {}
    # Total sales for period
    sales_total = SalesMaster.objects.filter(
        date__gte=start_date, date__lte=end_date, **branch_filter
    ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")

    # Total purchase for period
    purchase_total = PurchaseMaster.objects.filter(
        date__gte=start_date, date__lte=end_date, **branch_filter
    ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")

    # Profit = Sales - Purchase
    profit = sales_total - purchase_total
    return profit


# ---------------- API View ----------------

class ProductStatisticsAPIView(APIView):
    """
    Product Statistics API
    ✅ IsAuthenticated - sabko access
    """
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        branch = user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=400)

        branch_id_param = request.query_params.get('branch_id')
        if branch_id_param:
            if is_superadmin or is_employee:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)

        today = now().date()
        day_start = today
        week_start = today - timedelta(days=6)
        month_start = today.replace(day=1)

        branch_filter = {"branch": branch} if branch else {}

        # ----- Total Sales -----
        def sales_sum(start_date, end_date):
            return SalesMaster.objects.filter(
                date__gte=start_date, date__lte=end_date, **branch_filter
            ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")

        day_sales = sales_sum(day_start, today)
        week_sales = sales_sum(week_start, today)
        month_sales = sales_sum(month_start, today)

        # ----- Total Tax -----
        def tax_sum(start_date, end_date):
            return SalesMaster.objects.filter(
                date__gte=start_date, date__lte=end_date, **branch_filter
            ).aggregate(total=Sum("total_tax"))["total"] or Decimal("0.00")

        day_tax = tax_sum(day_start, today)
        week_tax = tax_sum(week_start, today)
        month_tax = tax_sum(month_start, today)

        # ----- All Time Sales -----
        all_time_sales = SalesMaster.objects.filter(**branch_filter).aggregate(
            total=Sum("grand_total")
        )["total"] or Decimal("0.00")

        # ----- Profit: Sales Total – Purchase Total -----
        def total_profit(start_date, end_date):
            sales_total = SalesMaster.objects.filter(
                date__gte=start_date, date__lte=end_date, **branch_filter
            ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")

            purchase_total = PurchaseMaster.objects.filter(
                date__gte=start_date, date__lte=end_date, **branch_filter
            ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")

            return sales_total - purchase_total

        day_profit = total_profit(day_start, today)
        week_profit = total_profit(week_start, today)
        month_profit = total_profit(month_start, today)

        # ----- Stats block -----
        def stats_block(total_sales, total_tax, total_profit):
            return [
                {"label": "Author Sales", "amount": float(total_sales), "icon": "sales"},
                {"label": "Tax Collected", "amount": float(total_tax), "icon": "tax"},
                {"label": "Total Profit", "amount": float(total_profit), "icon": "profit"},
                {"label": "All Time Sales", "amount": float(all_time_sales), "icon": "wallet"},
            ]

        # ----- Dummy chart data -----
        def chart_data(start_date, branch_filter):
            data = []
            for i in range(7):
                day = start_date + timedelta(days=i)
                total = SalesMaster.objects.filter(
                    date=day,
                    **branch_filter
                ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0.00")
                data.append(float(total))
            return data

        response = {
            "month": {
                "stats": stats_block(month_sales, month_tax, month_profit),
                "chartData": chart_data(month_start, branch_filter=branch_filter),
            },
            "week": {
                "stats": stats_block(week_sales, week_tax, week_profit),
                "chartData": chart_data(week_start, branch_filter=branch_filter),
            },
            "day": {
                "stats": stats_block(day_sales, day_tax, day_profit),
                "chartData": chart_data(today, branch_filter=branch_filter),
            },
        }

        return Response(response)


class SalesDashboardAPIView(APIView):
    """
    Sales Dashboard API
    ✅ IsAuthenticated - sabko access
    """
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        branch = user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=400)

        branch_id_param = request.query_params.get('branch_id')
        if branch_id_param:
            if is_superadmin or is_employee:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)

        period = request.query_params.get("period", "month")
        today = now().date()

        if period == "day":
            start_date = today
        elif period == "week":
            start_date = today - timedelta(days=6)
        else:
            start_date = today.replace(day=1)

        queryset = SalesMaster.objects.filter(
            date__gte=start_date,
            branch=branch
        ).order_by("-date")

        serializer = SalesDeshboardSerializers(queryset, many=True)
        return Response(serializer.data)
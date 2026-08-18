# pos/views/sales_profit_report_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from decimal import Decimal
from pos.models.salesentry import SalesMaster
from pos.models.branch import Branch
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


class SalesBillWiseProfitReportAPIView(APIView):
    """
    Bill-Wise Profit Report
    Sales Net = basic_amount (already correct from SalesItem.save())
    Profit = Sales Net - Purchase Cost
    """
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/salesProfitReport"  # ✅ ADD: Frontend route

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        print(f"\n{'='*50}")
        print(f"🔍 PROFIT REPORT API CALLED")
        print(f"User: {user.username}, Role: {user.role}, Superadmin: {is_superadmin}")
        print(f"{'='*50}")

        # ✅ CHANGE: Branch selection logic → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch and not is_superadmin:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=400)

        # ✅ FIX: Employee ko bhi branch_id override allow karo
        branch_id = request.GET.get('branch_id')
        
        # Superadmin: kisi bhi branch ka data
        if is_superadmin:
            print(f"Branch ID param: {branch_id}")
            if branch_id:
                try:
                    branch = Branch.objects.get(id=branch_id)
                    print(f"✅ Branch found: {branch.branch_name}")
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
                queryset = SalesMaster.objects.filter(branch=branch, is_cancelled=False)
            else:
                print("No branch_id - fetching ALL branches")
                queryset = SalesMaster.objects.filter(is_cancelled=False)
        
        # ✅ Employee: sirf apni branch, lekin agar branch_id diya hai toh wo bhi allow
        elif is_employee:
            if branch_id:
                try:
                    branch = Branch.objects.get(id=branch_id)
                    print(f"✅ Employee viewing branch: {branch.branch_name}")
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
            else:
                # Employee ki default branch
                branch = user.get_effective_branch()
                if not branch:
                    return Response({'error': 'Branch not found'}, status=400)
            queryset = SalesMaster.objects.filter(branch=branch, is_cancelled=False)
        
        else:
            # Normal user
            branch = user.get_effective_branch()
            if not branch:
                return Response({'error': 'Branch not found'}, status=400)
            queryset = SalesMaster.objects.filter(branch=branch, is_cancelled=False)

        print(f"📊 Total sales records before filters: {queryset.count()}")

        # Filters
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        search = request.GET.get('search', '').strip()

        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if search:
            queryset = queryset.filter(
                Q(bill_no__icontains=search) |
                Q(customer__account_name__icontains=search)
            )

        print(f"📊 After filters: {queryset.count()}")

        queryset = queryset.select_related('customer', 'branch').prefetch_related(
            'items__variant', 'items__item_name'
        ).order_by('-date', '-id')

        # Pagination
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        print(f"📊 Paginated records: {len(page) if page else 0}")

        # Build report data
        report_data = []
        total_sales_amount = Decimal('0.00')
        total_sales_net = Decimal('0.00')
        total_purchase_cost = Decimal('0.00')
        total_profit = Decimal('0.00')
        total_items_count = 0

        for sale in page:
            items = sale.items.all()
            items_count = items.count()
            total_items_count += items_count

            bill_sales_net = Decimal('0.00')
            bill_purchase_cost = Decimal('0.00')

            line_items = []
            for item in items:
                # Sales Net = basic_amount
                sales_net = item.basic_amount
                
                # Purchase Cost
                purchase_price = Decimal('0.00')
                if item.variant and item.variant.purchasePrice:
                    purchase_price = Decimal(str(item.variant.purchasePrice))
                
                purchase_cost = (purchase_price * item.qty).quantize(Decimal('0.01'))
                line_profit = sales_net - purchase_cost

                bill_sales_net += sales_net
                bill_purchase_cost += purchase_cost

                line_items.append({
                    'item_name': item.item_name.itemName if item.item_name else '-',
                    'hsn_code': item.hsn_code or '-',
                    'qty': float(item.qty),
                    'price': float(item.price),
                    'unit': item.unit or '-',
                    'discount_percent': float(item.discount_percent),
                    'tax_percent': float(str(item.item_name.taxSlab).replace('%', '').strip() or 0) if item.item_name else 0,
                    'basic_amount': float(item.basic_amount),
                    'discount_amount': float(item.discount_amount),
                    'tax_amount': float(item.tax_amount),
                    'net_amount': float(item.net_amount),
                    'sales_net': float(sales_net),
                    'purchase_price': float(purchase_price),
                    'purchase_cost': float(purchase_cost),
                    'line_profit': float(line_profit),
                    'gst_toggle_status': item.gst_toggle_status,
                })

            bill_profit = bill_sales_net - bill_purchase_cost
            profit_percent = (bill_profit / bill_sales_net * 100) if bill_sales_net > 0 else Decimal('0.00')

            report_data.append({
                'id': sale.id,
                'bill_no': sale.bill_no,
                'bill_date': sale.date.strftime('%Y-%m-%d'),
                'customer_name': sale.customer.account_name if sale.customer else '-',
                'number_of_items': items_count,
                'bill_amount': float(sale.grand_total),
                'sales_net': float(bill_sales_net),
                'purchase_cost': float(bill_purchase_cost),
                'profit_amount': float(bill_profit),
                'profit_percent': round(float(profit_percent), 2),
                'payment_terms': sale.payment_terms,
                'branch_name': sale.branch.branch_name if sale.branch else '-',
                'line_items': line_items,
                'gst_toggle_status': sale.items.first().gst_toggle_status if sale.items.exists() else None,
            })

            total_sales_amount += sale.grand_total
            total_sales_net += bill_sales_net
            total_purchase_cost += bill_purchase_cost
            total_profit += bill_profit

        overall_margin = (total_profit / total_sales_net * 100) if total_sales_net > 0 else Decimal('0.00')

        summary = {
            'total_bills': queryset.count(),
            'total_sales_amount': float(total_sales_amount),
            'total_sales_net': float(total_sales_net),
            'total_purchase_cost': float(total_purchase_cost),
            'total_profit': float(total_profit),
            'total_items': total_items_count,
            'profit_margin': round(float(overall_margin), 2),
        }

        print(f"Report data count: {len(report_data)}")
        print(f" Summary: {summary}")
        print(f"{'='*50}\n")

        response_data = {
            'success': True,
            'summary': summary,
            'data': report_data,
        }

        return paginator.get_paginated_response(response_data)
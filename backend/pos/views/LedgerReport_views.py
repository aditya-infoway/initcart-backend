# pos/views/LedgerReport_views.py

from datetime import date
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from pos.models.account import Account
from pos.serializers.LedgerReport_serializers import (
    LedgerAccountSerializer,
    LedgerReportSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# LEDGER ACCOUNT LIST VIEW (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class LedgerAccountListView(APIView):
    """
    GET /api/ledger-report/
    Returns paginated list of all accounts for the user's branch.
    Supports ?search=<name> and ?group=<Customer|Supplier|…>
    """
    
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/ledger-report"

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        # ✅ FIX: Branch selection logic - Employee ko sirf apni branch
        branch = user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ FIX: Branch filter - Superadmin ko kisi bhi branch ka data, Employee ko sirf apna
        branch_id_param = request.query_params.get('branch_id', '').strip()
        if branch_id_param:
            # Superadmin hamesha allow
            if is_superadmin:
                from pos.models.branch import Branch
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'detail': 'Branch not found.'}, status=404)
            # ✅ Employee allow karo agar uski branch superadmin branch hai
            elif is_employee:
                employee_branch = user.get_effective_branch()
                if employee_branch and employee_branch.user and employee_branch.user.role == 'superadmin':
                    from pos.models.branch import Branch
                    try:
                        branch = Branch.objects.get(id=branch_id_param)
                    except Branch.DoesNotExist:
                        return Response({'detail': 'Branch not found.'}, status=404)
                else:
                    # Employee ki branch superadmin branch nahi hai, toh apni branch hi use kare
                    pass

        search = request.query_params.get("search", "").strip()
        group = request.query_params.get("group", "").strip()

        qs = Account.objects.filter(branch=branch).order_by("account_name")
        if search:
            qs = qs.filter(account_name__icontains=search)
        if group:
            qs = qs.filter(group__iexact=group)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = LedgerAccountSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# LEDGER HISTORY VIEW (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class LedgerHistoryAPIView(APIView):
    """
    GET /api/ledger-history/<account_id>/
    Returns full ledger with running balance for one account.
    Optional: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    """
    
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/ledger-report"
    http_method_names = ['get']

    def get(self, request, account_id):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        # ✅ FIX: Branch fetch
        if is_superadmin:
            # Superadmin kisi bhi branch ka account dekh sakta hai
            try:
                account = Account.objects.get(id=account_id)
            except Account.DoesNotExist:
                return Response({'detail': 'Account not found.'}, status=404)
        else:
            branch = user.get_effective_branch()
            if not branch:
                return Response({
                    "success": False,
                    "error": "No branch linked to this user"
                }, status=status.HTTP_400_BAD_REQUEST)
            try:
                account = Account.objects.get(id=account_id, branch=branch)
            except Account.DoesNotExist:
                return Response({'detail': 'Account not found.'}, status=404)

        date_from = None
        date_to = None

        date_from_str = request.query_params.get("date_from", "").strip()
        date_to_str = request.query_params.get("date_to", "").strip()

        if date_from_str:
            try:
                date_from = date.fromisoformat(date_from_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid date_from format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if date_to_str:
            try:
                date_to = date.fromisoformat(date_to_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid date_to format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        data = LedgerReportSerializer.generate_ledger(
            account,
            date_from=date_from,
            date_to=date_to,
            update_current=True,
        )
        return Response(data)
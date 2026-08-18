# pos/views/schemeoffer_views.py

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from django.shortcuts import get_object_or_404
from pos.models.account import Account
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.models.branch import Branch
from pos.models.salesentry import SalesMaster
from pos.models.schemeoffer import SchemeOffer
from pos.serializers.schemeoffer_serializers import SchemeOfferSerializer

# ✅ Permission imports (already available)
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee, IsSuperAdminOrPagePermittedEmployee


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def is_main_branch_accessible(user):
    """
    Check if user belongs to main/superadmin branch.
    - Superadmin: Always True
    - Employee: True if his branch is superadmin branch
    - Others: False
    """
    role = getattr(user, "role", None)
    
    # Superadmin hamesha allow
    if role == "superadmin":
        return True
    
    # Employee check - uski branch superadmin branch hai?
    if role == "employee":
        branch = user.get_effective_branch()
        if branch and branch.user and branch.user.role == 'superadmin':
            return True
    
    return False


def _get_user_branch(user):
    # ✅ CHANGE: Branch.objects.get(user=user) → get_effective_branch()
    return user.get_effective_branch()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CRUD VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class SchemeOfferListCreateAPIView(APIView):
    """List schemes (branch user sees applicable, superadmin sees all) and create new scheme"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/SchemeOffer"  # ✅ ADD: Frontend route

    def get(self, request):
        user = request.user
        
        if is_main_branch_accessible(user):
            schemes = SchemeOffer.objects.all()
        else:
            # ✅ CHANGE: _get_user_branch() → get_effective_branch()
            branch = user.get_effective_branch()
            if not branch:
                return Response({
                    "success": False,
                    "error": "No branch linked to this user"
                }, status=400)
            schemes = SchemeOffer.objects.filter(
                Q(availability="all") | Q(branches=branch)
            ).distinct()

        return Response(SchemeOfferSerializer(schemes, many=True).data)

    def post(self, request):
        user = request.user
        
        # ✅ FIX: Superadmin OR Employee (with superadmin branch) can create
        if not is_main_branch_accessible(user):
            return Response(
                {"error": "Only main branch users (superadmin/employee) can create schemes"},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = SchemeOfferSerializer(
            data=request.data,
            context={"request": request}  
        )
        serializer.is_valid(raise_exception=True)
        branch = user.get_effective_branch()
        serializer.save(created_by_branch=branch)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SchemeOfferDetailAPIView(APIView):
    """Get, update, or delete a specific scheme offer"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/SchemeOffer"  # ✅ ADD: Frontend route

    def get_object(self, pk):
        return get_object_or_404(SchemeOffer, pk=pk)

    def get(self, request, pk):
        scheme = self.get_object(pk)
        user = request.user
        
        if not is_main_branch_accessible(user):
            branch = user.get_effective_branch()
            if not branch:
                return Response({
                    "success": False,
                    "error": "No branch linked to this user"
                }, status=400)
            applicable = scheme.get_applicable_branches()
            if not applicable.filter(id=branch.id).exists():
                return Response({"error": "Not permitted"}, status=403)
        return Response(SchemeOfferSerializer(scheme).data)

    def put(self, request, pk):
        # ✅ FIX: Superadmin OR Employee (with superadmin branch) can edit
        if not is_main_branch_accessible(request.user):
            return Response(
                {"error": "Only main branch users (superadmin/employee) can edit schemes"},
                status=403,
            )
        scheme = self.get_object(pk)
        serializer = SchemeOfferSerializer(scheme, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        # ✅ FIX: Superadmin OR Employee (with superadmin branch) can delete
        if not is_main_branch_accessible(request.user):
            return Response(
                {"error": "Only main branch users (superadmin/employee) can delete schemes"},
                status=403,
            )
        scheme = self.get_object(pk)
        scheme.delete()
        return Response({"message": "Scheme deleted"}, status=204)


# ─────────────────────────────────────────────────────────────────────────────
# SCHEME REPORT VIEW (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class SchemeOfferReportAPIView(APIView):
    """
    Month-wise → branch-wise → customer report for one scheme.

    ALL-MONTHS-CONSISTENCY rule: a customer qualifies for a scheme only if
    their monthly sales total clears that scheme's amount threshold in
    EVERY single month of the scheme's date range — not just some months.
    """
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/SchemeOffer"  # ✅ ADD: Frontend route

    def get(self, request, pk):
        scheme = get_object_or_404(SchemeOffer, pk=pk)
        user = request.user

        applicable_branches = scheme.get_applicable_branches()

        if not is_main_branch_accessible(user):
            # ✅ CHANGE: _get_user_branch() → get_effective_branch()
            user_branch = user.get_effective_branch()
            if not user_branch:
                return Response({
                    "success": False,
                    "error": "No branch linked to this user"
                }, status=400)
            if not applicable_branches.filter(id=user_branch.id).exists():
                return Response(
                    {"error": "This scheme is not applicable to your branch"},
                    status=403,
                )
            applicable_branches = applicable_branches.filter(id=user_branch.id)

        periods = scheme.get_month_periods()
        period_keys = [(p["year"], p["month"]) for p in periods]

        report_data = {key: {} for key in period_keys}

        for branch in applicable_branches:
            candidates = list(
                SchemeOffer.objects.filter(status="active")
                .filter(
                    start_date__lte=scheme.end_date,
                    end_date__gte=scheme.start_date,
                )
                .filter(Q(availability="all") | Q(branches=branch))
                .distinct()
            )
            if scheme.pk not in [c.pk for c in candidates]:
                candidates.append(scheme)
            candidates.sort(key=lambda s: s.amount, reverse=True)

            sales = SalesMaster.objects.filter(
                branch=branch,
                is_cancelled=False,
                date__gte=scheme.start_date,
                date__lte=scheme.end_date,
            ).values("customer_id", "customer__account_name", "date", "grand_total")

            customer_names = {}
            monthly_totals = defaultdict(lambda: defaultdict(lambda: Decimal("0")))

            for row in sales:
                cid = row["customer_id"]
                customer_names[cid] = row["customer__account_name"]
                key = (row["date"].year, row["date"].month)
                if key in period_keys:
                    monthly_totals[cid][key] += row["grand_total"] or Decimal("0")

            customer_ids = list(monthly_totals.keys())
            phone_lookup = dict(
                Account.objects.filter(id__in=customer_ids).values_list("id", "mobile")
            )

            for cid, totals_by_month in monthly_totals.items():
                full_totals = [totals_by_month.get(key, Decimal("0")) for key in period_keys]

                qualifying_scheme = None
                for candidate in candidates:
                    if all(t >= candidate.amount for t in full_totals):
                        qualifying_scheme = candidate
                        break

                if not qualifying_scheme or qualifying_scheme.pk != scheme.pk:
                    continue

                for key in period_keys:
                    bucket = report_data[key].setdefault(
                        branch.id,
                        {"branch_id": branch.id, "branch_name": branch.branch_name, "customers": []},
                    )
                    bucket["customers"].append(
                        {
                            "customer_id": cid,
                            "customer_name": customer_names[cid],
                            "customer_phone": phone_lookup.get(cid) or "",
                            "total_sales": float(totals_by_month.get(key, Decimal("0"))),
                        }
                    )

        months_report = []
        for p in periods:
            key = (p["year"], p["month"])
            branch_reports = list(report_data[key].values())
            for br in branch_reports:
                br["customers"].sort(key=lambda c: -c["total_sales"])
            months_report.append(
                {
                    "year": p["year"],
                    "month": p["month"],
                    "label": p["label"],
                    "period_start": str(p["period_start"]),
                    "period_end": str(p["period_end"]),
                    "branches": branch_reports,
                }
            )

        return Response(
            {
                "scheme_id": scheme.id,
                "offer_name": scheme.offer_name,
                "amount": float(scheme.amount),
                "scheme_type": scheme.scheme_type,
                "status": scheme.status,
                "start_date": str(scheme.start_date),
                "end_date": str(scheme.end_date),
                "months": months_report,
            }
        )


class BranchSchemeListAPIView(APIView):
    """Schemes applicable to the logged-in branch user, for their own view."""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/SchemeOffer"  # ✅ ADD: Frontend route

    def get(self, request):
        # ✅ CHANGE: _get_user_branch() → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=400)

        schemes = SchemeOffer.objects.filter(
            Q(availability="all") | Q(branches=branch)
        ).distinct()

        return Response(SchemeOfferSerializer(schemes, many=True).data)
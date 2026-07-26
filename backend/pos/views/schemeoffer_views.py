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


def _is_main_branch_user(user):
    """
    Main branch = the superadmin branch. Adjust this if your project
    marks the main branch with a dedicated flag (e.g. Branch.is_main)
    instead of a user role.
    """
    return getattr(user, "role", "") == "superadmin"


def _get_user_branch(user):
    try:
        return Branch.objects.get(user=user)
    except Branch.DoesNotExist:
        return None


class SchemeOfferListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if _is_main_branch_user(user):
            schemes = SchemeOffer.objects.all()
        else:
            branch = _get_user_branch(user)
            if not branch:
                return Response({"error": "Branch not found"}, status=400)
            schemes = SchemeOffer.objects.filter(
                Q(availability="all") | Q(branches=branch)
            ).distinct()

        return Response(SchemeOfferSerializer(schemes, many=True).data)

    def post(self, request):
        user = request.user
        if not _is_main_branch_user(user):
            return Response(
                {"error": "Only the main branch (superadmin) can create schemes"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SchemeOfferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = _get_user_branch(user)
        serializer.save(created_by_branch=branch)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SchemeOfferDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(SchemeOffer, pk=pk)

    def get(self, request, pk):
        scheme = self.get_object(pk)
        user = request.user
        if not _is_main_branch_user(user):
            branch = _get_user_branch(user)
            applicable = scheme.get_applicable_branches()
            if not branch or not applicable.filter(id=branch.id).exists():
                return Response({"error": "Not permitted"}, status=403)
        return Response(SchemeOfferSerializer(scheme).data)

    def put(self, request, pk):
        if not _is_main_branch_user(request.user):
            return Response(
                {"error": "Only the main branch (superadmin) can edit schemes"},
                status=403,
            )
        scheme = self.get_object(pk)
        serializer = SchemeOfferSerializer(scheme, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        if not _is_main_branch_user(request.user):
            return Response(
                {"error": "Only the main branch (superadmin) can delete schemes"},
                status=403,
            )
        scheme = self.get_object(pk)
        scheme.delete()
        return Response({"message": "Scheme deleted"}, status=204)


class SchemeOfferReportAPIView(APIView):
    """
    Month-wise -> branch-wise -> customer report for one scheme.

    ALL-MONTHS-CONSISTENCY rule: a customer qualifies for a scheme only if
    their monthly sales total clears that scheme's amount threshold in
    EVERY single month of the scheme's date range — not just some months.
    A month with no sales at all counts as ₹0 and fails the threshold.

    Among every active, overlapping scheme (same branch, same date range)
    that a customer fully clears this way, they are placed under the
    HIGHEST one only — never more than one scheme, and never a scheme
    they only partially qualify for.

    Example: Scheme A = ₹1000/month, Scheme B = ₹500/month, both Jul-Sep.
    Customer sells ₹1000 in July, ₹700 in August, ₹1000 in September.
    August breaks the ₹1000 streak, so the customer does NOT qualify for
    Scheme A at all (even though July & Sept individually hit ₹1000) —
    but they clear ₹500 in all three months, so they qualify for Scheme B
    and show under Scheme B in July, August, AND September.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        scheme = get_object_or_404(SchemeOffer, pk=pk)
        user = request.user

        applicable_branches = scheme.get_applicable_branches()

        if not _is_main_branch_user(user):
            user_branch = _get_user_branch(user)
            if not user_branch:
                return Response({"error": "Branch not found"}, status=400)
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

            # NEW: bulk fetch phone numbers in ONE query for all customers in this branch
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

    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch = _get_user_branch(request.user)
        if not branch:
            return Response({"error": "Branch not found"}, status=400)

        schemes = SchemeOffer.objects.filter(
            Q(availability="all") | Q(branches=branch)
        ).distinct()

        return Response(SchemeOfferSerializer(schemes, many=True).data)


# pos/models/schemeoffer.py
import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

from pos.models.branch import Branch
from pos.models.mixins import CreatedByMixin


class SchemeOffer(CreatedByMixin, models.Model):  
    """
    A branch-scoped sales scheme/offer.
    Only the main branch (superadmin) can create/edit/delete these.
    A scheme defines a monthly sales-amount threshold; every calendar
    month within [start_date, end_date] is evaluated independently, per
    applicable branch, against each customer's total sales for that month.
    """

    AVAILABILITY_CHOICES = [
        ("all", "All Branch"),
        ("selected", "Selected Branch"),
    ]
    TYPE_CHOICES = [
        ("per_month", "Per Month"),
        # Future types (Per Week / Per Quarter / Total Period) can be added
        # here later without touching existing data — the report logic
        # keys off `scheme_type` so new types just need their own
        # `get_month_periods`-equivalent method.
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    offer_name = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()

    availability = models.CharField(
        max_length=20, choices=AVAILABILITY_CHOICES, default="all"
    )
    branches = models.ManyToManyField(
        Branch, blank=True, related_name="scheme_offers"
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    scheme_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="per_month"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active"
    )

    created_by_branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_schemes",
        help_text="Main branch (superadmin) that created this scheme",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.offer_name} ({self.start_date} - {self.end_date})"

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError("End date must be on/after start date")

    def get_applicable_branches(self):
        """All branches this scheme applies to."""
        if self.availability == "all":
            return Branch.objects.all()
        return self.branches.all()

    def get_month_periods(self):
        """
        Returns every calendar month touched by [start_date, end_date],
        clipped to the scheme's own start/end dates. e.g. a scheme running
        01/07/2026 -> 01/10/2026 returns July, Aug, Sep, Oct — each with
        its own (period_start, period_end) window used for the report.
        """
        periods = []
        cursor_year = self.start_date.year
        cursor_month = self.start_date.month

        while (cursor_year, cursor_month) <= (self.end_date.year, self.end_date.month):
            month_first = date(cursor_year, cursor_month, 1)
            last_day = calendar.monthrange(cursor_year, cursor_month)[1]
            month_last = date(cursor_year, cursor_month, last_day)

            period_start = max(month_first, self.start_date)
            period_end = min(month_last, self.end_date)

            periods.append(
                {
                    "year": cursor_year,
                    "month": cursor_month,
                    "label": f"{calendar.month_name[cursor_month]} {cursor_year}",
                    "period_start": period_start,
                    "period_end": period_end,
                }
            )

            if cursor_month == 12:
                cursor_year += 1
                cursor_month = 1
            else:
                cursor_month += 1

        return periods
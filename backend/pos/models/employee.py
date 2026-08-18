# pos/models/employee.py
from django.db import models
from django.contrib.auth import get_user_model
from pos.models.branch import Branch

User = get_user_model()

DEPARTMENT_CHOICES = [
    ('purchase', 'Purchase Department'),
    ('sales', 'Sales Department'),
    ('accounting', 'Accounting Department'),
]

STATUS_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
]


class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='employees')

    full_name = models.CharField(max_length=255)
    mobile = models.CharField(max_length=15)
    email = models.EmailField(unique=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.full_name} ({self.branch.branch_name})"


class EmployeePermission(models.Model):
    """
    Har page (frontend route) ke liye employee ka granular access.
    page_key = frontend route ka 'to' value, e.g. '/addAccounts', '/Addsalesitem'
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='permissions')
    page_key = models.CharField(max_length=150)
    page_label = models.CharField(max_length=150, blank=True)

    can_view = models.BooleanField(default=False)
    can_add = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        unique_together = ('employee', 'page_key')

    def __str__(self):
        return f"{self.employee.full_name} → {self.page_key}"
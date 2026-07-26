# pos/models/sales_bill_display_setting.py
from django.db import models
from pos.models.branch import Branch


class SalesBillDisplaySetting(models.Model):
    """
    Global (poore system ke liye ek hi row) 
    (one row for whole system)setting — sirf superadmin edit karega.
    Controls: sales receipt/PDF pe branch name/address kiski dikhegi.
    """
    MODE_CHOICES = [
        ('main', 'Main Branch (Superadmin)'),
        ('branch', 'Selected Branches'),
    ]

    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='branch')
    selected_branches = models.ManyToManyField(
        Branch, blank=True, related_name='sales_bill_display_settings'
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return f"SalesBillDisplaySetting(mode={self.mode})"
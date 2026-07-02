#mlm/models/mlm_settings.py
from django.db import models
from django.core.cache import cache

class MLMSettings(models.Model):

    minimum_sale_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Minimum Sale: {self.minimum_sale_amount}"
    
    
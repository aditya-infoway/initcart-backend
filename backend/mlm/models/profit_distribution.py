#mlm/models/profit_distribution.py
from django.db import models

class ProfitDistribution(models.Model):
    pos_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    service_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    mlm_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    company_percentage = models.DecimalField(max_digits=5, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total_percentage(self):
        return (
            self.pos_percentage +
            self.service_percentage +
            self.mlm_percentage +
            self.company_percentage
        )

    def __str__(self):
        return "Global Profit Distribution"
#mlm/models/mlm_level.py
from django.db import models
from mlm.models.mlm_level_config import MLMLevelConfig

class MLMLevel(models.Model):

    config = models.ForeignKey(
        MLMLevelConfig,
        on_delete=models.CASCADE,
        related_name="levels"
    )

    level_number = models.PositiveIntegerField()
    percentage = models.FloatField()

    class Meta: 
        ordering = ["level_number"]

    def __str__(self):
        return f"Level {self.level_number} - {self.percentage}%"
    
    
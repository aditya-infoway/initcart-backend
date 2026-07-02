# services/models/base.py  ← naya file banao
from django.db import models

class ServiceBaseModel(models.Model):
    is_active = models.BooleanField(default=True)
    
    class Meta:
        abstract = True  # ← DB mein table nahi banega, sirf inherit hoga
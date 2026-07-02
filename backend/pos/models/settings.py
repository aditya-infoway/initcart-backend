#pos/models/settings.py
from django.db import models
from pos.models.branch import Branch

class setting(models.Model):
    BP = models.CharField(max_length=50, blank=True, null=True, default="BP")
    CP = models.CharField(max_length=50, blank=True, null=True, default="CP")
    CR = models.CharField(max_length=50, blank=True, null=True, default="CR")
    BR = models.CharField(max_length=50, blank=True, null=True, default="BR")
    PI = models.CharField(max_length=50, blank=True, null=True, default="PI")
    SI = models.CharField(max_length=50, blank=True, null=True, default="SI")
    PR = models.CharField(max_length=50, blank=True, null=True, default="PR")
    SR = models.CharField(max_length=50, blank=True, null=True, default="SR")
    ST = models.CharField(max_length=50, blank=True, null=True, default="ST")  
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True)
    JE = models.CharField(max_length=50, blank=True, null=True, default="JE")
    gst_toggle = models.BooleanField(blank=True, null=True, default=False)
    sales_gst_toggle = models.BooleanField(blank=True, null=True, default=False)
    contra = models.CharField(max_length=50 , blank=True, null=True, default="CT")
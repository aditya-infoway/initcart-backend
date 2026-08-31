# pos/models/ai_purchase_document.py
from django.conf import settings
from django.db import models
from pos.models.branch import Branch
from pos.models.purchaseentry import PurchaseMaster


class AIPurchaseDocument(models.Model):
    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("extracted", "Extracted"),
        ("excel_generated", "Excel Generated"),
        ("imported", "Imported"),
        ("failed", "Failed"),
    ]

    file = models.FileField(upload_to="purchase_ai_bills/originals/")
    generated_excel = models.FileField(
        upload_to="purchase_ai_bills/excel/", null=True, blank=True
    )
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    extracted_data = models.JSONField(null=True, blank=True)
    file_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    created_purchase = models.ForeignKey(
        PurchaseMaster, on_delete=models.SET_NULL, null=True, blank=True
    )
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AIPurchaseDocument #{self.id} ({self.status})"
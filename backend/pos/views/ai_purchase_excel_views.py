# pos/views/ai_purchase_excel_views.py
"""
AI Bill Upload -> Excel Generation.

YAHAN SIRF 2 CHEEZEIN HOTI HAIN:
  1. Bill image/PDF upload -> AI padhta hai -> data extract hota hai
  2. Extract hui data ko EXACT USER TEMPLATE format me Excel bana kar
     download ke liye deta hai

Import/validation/Purchase-creation ka SAARA logic
pos/views/purchase_excel_views.py (PurchaseExcelImportView) me hai —
usse yahan se bilkul touch nahi kiya gaya.
"""
import hashlib
import io
import logging

from django.core.files.base import ContentFile
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee
from pos.models.ai_purchase_document import AIPurchaseDocument
from pos.services.ai_purchase_excel_generator import generate_ai_filled_excel
from pos.services.purchase_invoice_ai_service import extract_invoice

logger = logging.getLogger(__name__)

ALLOWED_BILL_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "application/pdf"}
MAX_BILL_SIZE_MB = 15


class PurchaseAIBillUploadView(APIView):
    """POST /purchase/ai-bill/extract/  multipart bill=<image/pdf>"""

    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"

    def post(self, request):
        bill_file = request.FILES.get("bill")
        if not bill_file:
            return Response({"success": False, "error": "No bill file uploaded"}, status=400)

        if bill_file.content_type not in ALLOWED_BILL_TYPES:
            return Response({
                "success": False,
                "error": "Unsupported file type. Allowed: jpg, jpeg, png, webp, pdf",
            }, status=400)

        if bill_file.size > MAX_BILL_SIZE_MB * 1024 * 1024:
            return Response({"success": False, "error": f"File too large (max {MAX_BILL_SIZE_MB}MB)"}, status=400)

        branch = request.user.get_effective_branch()
        if not branch:
            return Response({"success": False, "error": "No branch linked to this user"}, status=400)

        file_bytes = bill_file.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        existing = AIPurchaseDocument.objects.filter(
            file_hash=file_hash, branch=branch, status="excel_generated"
        ).first()
        if existing:
            return Response({
                "success": True,
                "message": "This bill was already processed earlier",
                "document_id": existing.id,
                "download_url": f"/api/pos/purchase/ai-bill/{existing.id}/download/",
                "already_processed": True,
                "warnings": [],
            })

        doc = AIPurchaseDocument.objects.create(
            file=ContentFile(file_bytes, name=bill_file.name),
            branch=branch,
            uploaded_by=request.user,
            status="processing",
            file_hash=file_hash,
        )

        try:
            extracted = extract_invoice(file_bytes, bill_file.content_type)
            doc.extracted_data = extracted
            doc.status = "extracted"
            doc.save(update_fields=["extracted_data", "status"])

            wb, warnings = generate_ai_filled_excel(branch, extracted)

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            doc.generated_excel.save(f"purchase_ai_{doc.id}.xlsx", ContentFile(buf.read()), save=False)
            doc.status = "excel_generated"
            doc.save(update_fields=["generated_excel", "status"])

        except Exception as e:
            logger.exception("AI bill extraction failed (doc_id=%s)", doc.id)
            doc.status = "failed"
            doc.error_message = str(e)
            doc.save(update_fields=["status", "error_message"])
            return Response({"success": False, "error": str(e), "document_id": doc.id}, status=400)

        supplier = (extracted.get("supplier") or {}).get("name")
        invoice = extracted.get("invoice") or {}
        totals = extracted.get("totals") or {}

        return Response({
            "success": True,
            "document_id": doc.id,
            "preview": {
                "supplier": supplier,
                "bill_no": invoice.get("bill_no"),
                "date": invoice.get("date"),
                "items_detected": len(extracted.get("items") or []),
                "grand_total": totals.get("grand_total"),
            },
            "warnings": warnings,
            "download_url": f"/api/pos/purchase/ai-bill/{doc.id}/download/",
        }, status=201)


class AIPurchaseDocumentDownloadView(APIView):
    """GET /purchase/ai-bill/<id>/download/"""

    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Addpurchaseitem"

    def get(self, request, doc_id):
        branch = request.user.get_effective_branch()
        try:
            doc = AIPurchaseDocument.objects.get(id=doc_id, branch=branch)
        except AIPurchaseDocument.DoesNotExist:
            return Response({"error": "Document not found"}, status=404)

        if not doc.generated_excel:
            return Response({"error": "Excel not generated for this document"}, status=400)

        response = HttpResponse(
            doc.generated_excel.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="purchase_ai_{doc.id}.xlsx"'
        return response
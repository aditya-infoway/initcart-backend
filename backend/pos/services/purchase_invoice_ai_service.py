# pos/services/purchase_invoice_ai_service.py
import base64
import io
import json
import logging
import requests
from PIL import Image
from django.conf import settings

logger = logging.getLogger(__name__)

CANONICAL_SCHEMA_HINT = """
You are reading a PURCHASE INVOICE / BILL image. Bills can be in ANY design,
layout, language mix, handwritten, printed, GST or non-GST, single or
multi-column — read the WHOLE document carefully like a human accountant
would, regardless of format.

Return ONLY valid JSON, no markdown, no preamble, matching exactly this shape:
{
  "supplier": {"name": null, "gstin": null, "address": null, "phone": null},
  "invoice": {"bill_no": null, "date": null, "due_date": null, "purchase_bill_no": null},
  "terms": null,
  "items": [
    {
      "item_name": null, "hsn_code": null, "barcode": null,
      "size": null, "color": null, "serial_no": null, "warranty_date": null,
      "quantity": null, "alt_quantity": null, "unit": null,
      "purchase_price": null, "discount_percent": null, "gst_rate": null,
      "basic_amount": null, "discount_amount": null, "tax_amount": null,
      "cgst": null, "sgst": null, "igst": null, "net_value": null
    }
  ],
  "totals": {
    "total_basic": null, "total_tax": null, "total_net": null,
    "grand_total": null, "freight_charge": null, "other_expense": null, "round_off": null
  }
}

STRICT RULES:
1. Never invent a value. If a field is not visible or you are not confident,
   return null for it — do NOT guess.
2. supplier.name = the SELLER/VENDOR name printed on the bill (not the buyer).
3. items array = EVERY line item row in the bill's item table, in the same
   order as printed. If the same product appears with different size/color/
   variant on separate rows, list them as SEPARATE item entries.
4. quantity/purchase_price/discount_percent/gst_rate/basic_amount/tax_amount/
   cgst/sgst/igst/net_value — extract these as printed NUMBERS ONLY (no
   currency symbols, no commas, no % sign) — e.g. 1250.50 not "₹1,250.50".
5. If a bill shows CGST+SGST columns, fill cgst and sgst separately (leave
   igst null). If it shows only IGST, fill igst only (leave cgst/sgst null).
   If no tax breakdown shown at all, leave all three null even if gst_rate
   is known.
6. discount_percent should be a plain number like 5 (for 5%), not "5%".
7. "terms" (payment terms) must be exactly one of "Credit", "Cash", "Bank"
   — ONLY if the bill explicitly states it (e.g. "Payment: Cash",
   "Credit 30 days"). If not stated anywhere, return null — do not assume.
8. Dates: preserve exactly as printed on the bill (e.g. "19/08/2026" or
   "19-Aug-2026") — do not reformat or guess the format.
9. size/color/serial_no/warranty_date: only fill if the bill clearly shows
   a variant attribute for that item row (e.g. "Size: L", "Sr No: 12345").
   Otherwise null.
10. If handwriting is unclear or a number is ambiguous/smudged, prefer null
    over a wrong guess for that specific field only — still extract every
    other field you ARE confident about from the same row.
11. totals: total_basic/total_tax/total_net/grand_total should be the
    invoice's own printed summary/footer totals (not something you compute).
12. Output ONLY the JSON object — no explanation, no markdown code fences,
    no extra text before or after.
"""

# Low-end CPU hardware ke liye — image jitni badi, utna slow. 1280px max side
# rakhne se text still readable rehta hai lekin processing time drastically kam ho jaata hai.
MAX_IMAGE_DIMENSION = 1280


def _resize_image_for_speed(file_bytes: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")

        width, height = img.size
        max_side = max(width, height)

        if max_side > MAX_IMAGE_DIMENSION:
            scale = MAX_IMAGE_DIMENSION / max_side
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)
            logger.info("Resized image from %sx%s to %s for faster AI processing", width, height, new_size)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    except Exception:
        logger.exception("Image resize failed, using original")
        return file_bytes


def extract_invoice(file_bytes: bytes, content_type: str) -> dict:
    """Local Qwen2.5-VL (Ollama) se invoice padhta hai. 100% free, offline."""
    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = getattr(settings, "PURCHASE_INVOICE_AI_MODEL", "qwen2.5vl:3b")

    is_pdf = "pdf" in (content_type or "").lower()
    if is_pdf:
        file_bytes = _pdf_first_page_to_png(file_bytes)

    file_bytes = _resize_image_for_speed(file_bytes)
    image_b64 = base64.b64encode(file_bytes).decode("utf-8")

    logger.info("AI extraction started (local Ollama, model=%s)", model)

    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": CANONICAL_SCHEMA_HINT,
                "images": [image_b64],
                "stream": False,
                "format": "json",
                "keep_alive": "30m",
                "options": {"num_predict": 2000, "temperature": 0.1},
            },
            timeout=600,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Local AI (Ollama) is not running. Pehle 'ollama serve' chalao "
            "ya 'ollama run qwen2.5vl:3b' se model start karo."
        )
    except requests.exceptions.ReadTimeout:
        raise RuntimeError(
            "AI is taking too long to respond (CPU-only processing is slow). "
            "Try again with a clearer/smaller image."
        )
    except Exception:
        logger.exception("Ollama call failed")
        raise

    raw_text = response.json().get("response", "").strip()

    cleaned = raw_text
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("AI returned non-JSON output: %s", raw_text[:500])
        raise ValueError("AI is bill se data nahi nikal paya. Zyada clear image try karo.")

    logger.info("AI extraction completed: %d row(s) detected", len(data.get("items", []) or []))
    return data


def _pdf_first_page_to_png(pdf_bytes: bytes) -> bytes:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes
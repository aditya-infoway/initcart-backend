import time
from django.core.cache import cache

CACHE_TTL = 60 * 60 * 6  # 6 ghante (safety net; asli invalidation signals se hota hai)

# Process-local copy: Redis se poora blob har request pe unpickle na karna pade.
# { branch_id: (version, data) } -- version Redis se check hota hai, to multiple workers me bhi sahi rehta hai.
_LOCAL = {}


def _ver_key(branch_id):
    return f"pos:items:ver:{branch_id}"


def get_items_version(branch_id):
    """Har branch ka ek 'version'. Item badle to version badal jaata hai -> purana cache apne aap bekaar."""
    key = _ver_key(branch_id)
    ver = cache.get(key)                       # normal case: sirf 1 chhoti Redis call
    if ver is None:
        cache.add(key, int(time.time() * 1000), None)
        ver = cache.get(key)
    return ver


def bump_items_version(branch_id):
    cache.set(_ver_key(branch_id), int(time.time() * 1000), None)
    _LOCAL.pop(branch_id, None)


def _build_branch_data(branch):
    """DB se ek baar saare variants nikalke rows + search index + barcode map banata hai."""
    from pos.models.items import itemvariants

    variants = (itemvariants.objects.filter(item__branch=branch)
                .select_related("item", "item__unit").order_by("id"))

    rows, index, barcodes = [], [], {}
    for variant in variants:
        item = variant.item

        unit_name = "-"
        unit_symbol = "pc"
        unit_supports_fractional = False
        if item.unit:
            unit_name = item.unit.name if hasattr(item.unit, "name") else str(item.unit)
            unit_symbol = item.unit.symbol if hasattr(item.unit, "symbol") else item.unit.name
            unit_supports_fractional = getattr(item.unit, "supports_fractional", False)

        purchase_price = variant.purchasePrice or 0
        per_unit_price = purchase_price
        if unit_supports_fractional and variant.opStock and variant.opStock > 0:
            per_unit_price = purchase_price / variant.opStock

        rows.append({
            "id": variant.id,
            "itemId": item.id,
            "itemName": item.itemName,
            "hsnCode": item.hsnCode or "",
            "purchasePrice": float(purchase_price),
            "per_unit_price": float(per_unit_price),
            "barcode": variant.barcode or "",
            "size": variant.size or "-",
            "color": variant.color or "-",
            "srno": variant.srno or "-",
            "warrantydate": variant.warrantydate or "-",
            "unit": unit_symbol,
            "unit_name": unit_name,
            "unit_supports_fractional": unit_supports_fractional,
            "taxSlab": item.taxSlab or "0",
            "opStock": float(variant.opStock or 0),
        })

        # exact barcode lookup ke liye (scanner): barcode -> rows ka index
        bc = (variant.barcode or "").strip().lower()
        if bc:
            barcodes[bc] = len(rows) - 1

        # search ke liye ek lowercase string (rows ke saath same order)
        index.append(" ".join(str(x) for x in (
            item.itemName, item.hsnCode or "", purchase_price,
            variant.size or "", variant.color or "",
            variant.barcode or "", variant.srno or "",
        )).lower())

    return {"rows": rows, "index": index, "barcodes": barcodes}


def get_branch_variant_data(branch):
    ver = get_items_version(branch.id)

    hit = _LOCAL.get(branch.id)
    if hit and hit[0] == ver:                  # sabse tez: process memory se
        return hit[1]

    key = f"pos:items:data:v2:{branch.id}:{ver}"   # v2: naya shape (barcodes map)
    data = cache.get(key)
    if data is None:                           # Redis miss -> DB se banao
        data = _build_branch_data(branch)
        cache.set(key, data, CACHE_TTL)
    if len(_LOCAL) >= 20:      # memory cap
        _LOCAL.clear()
    _LOCAL[branch.id] = (ver, data)
    return data


def search_variants(branch, query, limit=50):
    data = get_branch_variant_data(branch)
    rows, index = data["rows"], data["index"]

    tokens = (query or "").strip().lower().split()
    if not tokens:
        return rows[:limit] if limit else rows

    result = []
    for row, text in zip(rows, index):
        if all(t in text for t in tokens):     # "red shirt" jaisi multi-word search bhi chalegi
            result.append(row)
            if limit and len(result) >= limit:
                break
    return result


def find_by_barcode(branch, barcode):
    """Exact barcode match (scanner ke liye) -- dict lookup, O(1)."""
    data = get_branch_variant_data(branch)
    idx = data.get("barcodes", {}).get((barcode or "").strip().lower())
    return data["rows"][idx] if idx is not None else None
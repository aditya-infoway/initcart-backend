import os
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from pos.models.branch import Branch
from pos.models.account import Account
from pos.models.items import itemvariants as IV
from pos.models.b2b_sales import B2BSale, B2BSaleItem
from pos.models.purchaseentry import PurchaseItem
from pos.models.salesentry import SalesItem
from pos.models.purchasereturn import PurchaseReturnItem
from pos.models.salesreturn import SalesReturnItem
from pos.models.stock_transfer import StockTransferItem
from pos.models.stock_return import StockReturnItem
from pos.models.b2b_transfer import B2BStockTransferItem
from pos.models.b2b_stock_return import B2BStockReturnItem
from ecommerce.models.order import OrderItem
from pos.serializers.b2b_sales_serializers import B2BSaleCreateSerializer
from pos.serializers.LedgerReport_serializers import LedgerReportSerializer
from pos.utils.variant_mapping import get_or_create_dest_variant
from pos.utils.b2b_purchase_entry import create_purchase_entry_from_b2b_sale

# ================= CONFIG =================
DRY_RUN        = os.environ.get("DRY_RUN", "1") != "0"
ADD_QTY        = 2000
TRANSFER_QTY   = 100
SEED_THRESHOLD = 2000     # opStock isse zyada/barabar ho to +2000 dubara nahi jodna
MARKER         = "AUTO-BULK-100 (initial stock seeding)"
# ==========================================

Z = Decimal("0")


class FakeReq:
    pass


def calc_stock(variants, branch_id, is_sa):
    """StockReportAPIView ka EXACT formula, bina DB write ke."""
    ids = [v.id for v in variants]

    def agg(qs, key, field):
        return {r[key]: Decimal(str(r["t"])) for r in qs.order_by().values(key).annotate(t=Sum(field)) if r["t"] is not None}

    pur  = agg(PurchaseItem.objects.filter(variant_id__in=ids), "variant_id", "quantity")
    pret = agg(PurchaseReturnItem.objects.filter(variant_id__in=ids), "variant_id", "return_quantity")
    trr  = agg(StockTransferItem.objects.filter(to_variant_id__in=ids, transfer__to_branch_id=branch_id, is_stock_updated=True), "to_variant_id", "quantity")
    trs  = agg(StockTransferItem.objects.filter(from_variant_id__in=ids, transfer__from_branch_id=branch_id, is_stock_updated=True), "from_variant_id", "quantity") if is_sa else {}
    srp  = {} if is_sa else agg(StockReturnItem.objects.filter(branch_variant_id__in=ids, return_request__branch_id=branch_id, is_packaging_ready=True), "branch_variant_id", "quantity")
    srr  = agg(StockReturnItem.objects.filter(company_variant_id__in=ids, return_request__to_branch_id=branch_id, is_returned_to_company=True), "company_variant_id", "quantity") if is_sa else {}
    b2r  = agg(B2BStockTransferItem.objects.filter(to_variant_id__in=ids, transfer__to_branch_id=branch_id, is_received=True), "to_variant_id", "quantity")
    b2s  = agg(B2BStockTransferItem.objects.filter(from_variant_id__in=ids, transfer__from_branch_id=branch_id, is_packaged=True), "from_variant_id", "quantity")
    brp  = {} if is_sa else agg(B2BStockReturnItem.objects.filter(branch_variant_id__in=ids, return_request__branch_id=branch_id, is_packaging_ready=True), "branch_variant_id", "quantity")
    brr  = agg(B2BStockReturnItem.objects.filter(company_variant_id__in=ids, return_request__to_branch_id=branch_id, is_returned_to_company=True), "company_variant_id", "quantity") if is_sa else {}
    bsal = agg(B2BSaleItem.objects.filter(from_variant_id__in=ids, sale__from_branch_id=branch_id).exclude(Q(sale__status="cancelled") & Q(is_stock_updated=False)), "from_variant_id", "quantity") if is_sa else {}
    spos = agg(SalesItem.objects.filter(variant_id__in=ids), "variant_id", "qty")
    sweb = agg(OrderItem.objects.filter(product_stock_id__in=ids, item_status="delivered"), "product_stock_id", "quantity")
    sret = agg(SalesReturnItem.objects.filter(variant_id__in=ids), "variant_id", "return_quantity")

    out = {}
    for v in variants:
        g = lambda m: m.get(v.id, Z)
        c = (Decimal(str(v.opStock or 0)) + g(pur) - g(pret) + g(trr) - g(trs) - g(srp) + g(srr)
             + g(b2r) - g(b2s) - g(brp) + g(brr) - (g(spos) + g(sweb)) + g(sret) - g(bsal))
        out[v.id] = c if c > 0 else Z
    return out


print("=" * 70)
print("MODE:", "DRY RUN (poora flow chalega, end me ROLLBACK)" if DRY_RUN else "*** LIVE RUN ***")
print("=" * 70)

# ---------- 1. Superadmin branch ----------
sa = Branch.get_superadmin_branch()
if not sa or not sa.user:
    raise SystemExit("ABORT: Superadmin branch / user nahi mila.")
sa_user = sa.user
eff = sa_user.get_effective_branch()
if eff is None or eff.id != sa.id:
    raise SystemExit("ABORT: Superadmin effective branch mismatch.")
print("Superadmin branch:", sa.id, sa.branch_name)

# ---------- 2. Pichli marker sales ----------
marker_sales = list(B2BSale.objects.filter(note=MARKER).exclude(status="cancelled").order_by("id"))
if not marker_sales:
    raise SystemExit("ABORT: Pichli marker sales nahi mili (note: %s)." % MARKER)
print("\nPichli marker sales:")
for s in marker_sales:
    print("   ", s.id, s.sale_no, "-> branch", s.to_branch_id, "| created:", s.created_at.strftime("%Y-%m-%d %H:%M"))

done, any_marker = {}, set()
rows = (B2BSaleItem.objects.filter(sale__note=MARKER).exclude(sale__status="cancelled")
        .values_list("sale__to_branch_id", "from_variant_id"))
for to_b, fv in rows:
    done.setdefault(to_b, set()).add(fv)
    any_marker.add(fv)

# ---------- 3. Variants, franchises ----------
variants = list(IV.objects.filter(item__branch=sa).select_related("item").order_by("id"))
vmap = {v.id: v for v in variants}
print("\nSuperadmin variants (total):", len(variants))

franchises = list(Branch.objects.filter(ownership_type="franchise", status="active").order_by("created_at", "id"))
print("Active franchises:", [(f.id, f.branch_name) for f in franchises])

# ---------- 4. Naye variants (marker sales me nahi) ----------
seed, high = [], []
for v in variants:
    if v.id in any_marker:
        continue
    (high if (v.opStock or 0) >= SEED_THRESHOLD else seed).append(v)
new_all = seed + high
print("\nNaye variants (kisi marker sale me nahi):", len(new_all))
if new_all:
    print("   created range:", min(v.created_at for v in new_all).strftime("%Y-%m-%d %H:%M"),
          "->", max(v.created_at for v in new_all).strftime("%Y-%m-%d %H:%M"))
print("   +%d opStock milega:" % ADD_QTY, len(seed),
      "| inme se pehle se opStock>0:", sum(1 for v in seed if (v.opStock or 0) > 0))
print("   opStock >= %d (add NAHI karunga, sirf transfer):" % SEED_THRESHOLD, len(high),
      [(v.id, v.item.itemName[:20], v.opStock) for v in high[:10]])

# ---------- 5. Har franchise ka kaam ----------
work = []
for fr in franchises:
    missing = [v for v in variants if v.id not in done.get(fr.id, set())]
    if not missing:
        print("SKIP (kuch baaki nahi):", fr.id, fr.branch_name)
        continue
    if fr.id not in done:
        print("!!! NAYI FRANCHISE (pehle kuch nahi gaya): %s -> SAARE %d variants jayenge" % (fr.branch_name, len(missing)))
    work.append((fr, missing))

if not work:
    raise SystemExit("\nKuch karne ko nahi hai. Sab up-to-date.")

no_acct = [fr.branch_name for fr, m in work
           if not Account.objects.filter(branch=fr, group="Sundry Creditor(Main)").exists()]
if no_acct:
    raise SystemExit("ABORT: In franchises me Sundry Creditor(Main) account nahi hai, pehle UI se banao: %s" % no_acct)

# ---------- 6. Rate (branchPrice, 0 ho to purchasePrice) ----------
involved_ids = set(v.id for v in seed) | set(v.id for _, m in work for v in m)
rate_map, r_bp, r_pp, r_zero = {}, 0, 0, 0
for vid in involved_ids:
    v = vmap[vid]
    bp, pp = v.branchPrice or 0, v.purchasePrice or 0
    if bp > 0:
        rate_map[vid] = float(bp); r_bp += 1
    elif pp > 0:
        rate_map[vid] = float(pp); r_pp += 1
    else:
        rate_map[vid] = 0.0; r_zero += 1
print("\nRate: branchPrice=%d | purchasePrice fallback=%d | dono 0=%d" % (r_bp, r_pp, r_zero))

# ---------- 7. Plan (memory me seed lagake stock predict) ----------
for v in seed:
    v.opStock = int(v.opStock or 0) + ADD_QTY
inv_objs = [vmap[i] for i in sorted(involved_ids)]
avail = {k: float(c) for k, c in calc_stock(inv_objs, sa.id, True).items()}

print("\nPLAN:")
for fr, missing in work:
    sendable = [v for v in missing if avail[v.id] >= TRANSFER_QTY]
    short = [v for v in missing if avail[v.id] < TRANSFER_QTY]
    for v in sendable:
        avail[v.id] -= TRANSFER_QTY
    print("   %s (id=%s): bhejenge=%d | stock kam (skip)=%d" % (fr.branch_name, fr.id, len(sendable), len(short)))
    for v in short[:10]:
        print("        SHORT:", v.id, v.item.itemName[:25], "available ~", avail[v.id])

# ---------- 8. Execute ----------
today = timezone.localdate()
ok, failed = [], []

with transaction.atomic():
    if seed:
        IV.objects.bulk_update(seed, ["opStock"], batch_size=500)
        print("\nSTEP 1: %d variants me +%d opStock." % (len(seed), ADD_QTY))

    synced = calc_stock(inv_objs, sa.id, True)
    chg = []
    for v in inv_objs:
        if Decimal(str(v.current_stock or 0)) != synced[v.id]:
            v.current_stock = synced[v.id]
            chg.append(v)
    if chg:
        IV.objects.bulk_update(chg, ["current_stock"], batch_size=500)
    print("STEP 2: source current_stock report-formula se sync: %d badle." % len(chg))

    for fr, missing in work:
        try:
            with transaction.atomic():
                ids = [v.id for v in missing]
                cur = dict(IV.objects.filter(id__in=ids).values_list("id", "current_stock"))
                send = [v for v in missing if Decimal(str(cur.get(v.id) or 0)) >= TRANSFER_QTY]
                skipped = len(missing) - len(send)
                if not send:
                    print("INFO :", fr.branch_name, "- bhejne layak kuch nahi")
                    continue

                req = FakeReq()
                req.user = sa_user
                payload = {
                    "to_branch_id": fr.id,
                    "sale_date": today,
                    "note": MARKER,
                    "items": [{"from_variant_id": v.id, "quantity": str(TRANSFER_QTY), "rate": rate_map[v.id]} for v in send],
                }
                ser = B2BSaleCreateSerializer(data=payload, context={"request": req})
                ser.is_valid(raise_exception=True)
                sale = ser.save()

                items = list(sale.items.select_related("from_variant").filter(is_stock_updated=False))
                for it in items:
                    dv, _c = get_or_create_dest_variant(
                        it.from_variant, fr, sync_fields=True, price_override=it.rate,
                        source="B2B Sale", reference=sale.sale_no,
                    )
                    dv.current_stock = (dv.current_stock or 0) + it.quantity
                    dv.purchasePrice = it.rate
                    dv.save(update_fields=["current_stock", "purchasePrice"])
                    it.is_stock_updated = True
                    it.website_display_on_verify = False
                    it.to_variant = dv
                    it.save(update_fields=["is_stock_updated", "website_display_on_verify", "to_variant"])

                sale.status = "completed"
                sale.save(update_fields=["status"])

                to_ids = [i.to_variant_id for i in items]
                qty = {i.to_variant_id: Decimal(str(i.quantity)) for i in items}
                tvs = list(IV.objects.filter(id__in=to_ids))
                pre = calc_stock(tvs, fr.id, False)

                purchase = create_purchase_entry_from_b2b_sale(sale)
                if purchase is None:
                    raise Exception("Purchase entry not processed ( check account/items )")

                tvs = list(IV.objects.filter(id__in=to_ids))
                res = calc_stock(tvs, fr.id, False)
                wrong = [(v.id, float(pre[v.id]), float(res[v.id]), float(qty[v.id]))
                         for v in tvs if res[v.id] != pre[v.id] + qty[v.id]]
                if wrong:
                    raise Exception("%d variants ka stock expected (pehle+qty) nahi aaya: %s" % (len(wrong), wrong[:5]))

                upd = []
                for v in tvs:
                    if Decimal(str(v.current_stock or 0)) != res[v.id]:
                        v.current_stock = res[v.id]
                        upd.append(v)
                if upd:
                    IV.objects.bulk_update(upd, ["current_stock"], batch_size=500)

            ok.append((fr.id, fr.branch_name, sale.sale_no, purchase.billNo, len(send), skipped))
            print("OK   : %s | %s | %s | items=%d | skipped(stock kam)=%d | purchase total=%s"
                  % (fr.branch_name, sale.sale_no, purchase.billNo, len(send), skipped, purchase.grand_total))
        except Exception as e:
            failed.append((fr.id, fr.branch_name, repr(e)[:400]))
            print("FAIL :", fr.id, fr.branch_name, "->", repr(e)[:400], "(is franchise ka rollback)")

    # ---- Ledger refresh ----
    for fr_id in set(o[0] for o in ok):
        acct = Account.objects.filter(branch_id=fr_id, group="Sundry Creditor(Main)").first()
        if acct:
            LedgerReportSerializer.generate_ledger(acct, update_current=True)
            print("Ledger:", acct.branch.branch_name, "->", acct.current_balance, acct.current_drcr)

    # ---- Source final check ----
    fresh = list(IV.objects.filter(id__in=involved_ids))
    fin = calc_stock(fresh, sa.id, True)
    fix = []
    for v in fresh:
        if Decimal(str(v.current_stock or 0)) != fin[v.id]:
            v.current_stock = fin[v.id]
            fix.append(v)
    if fix:
        IV.objects.bulk_update(fix, ["current_stock"], batch_size=500)
    print("Source final check: %d variants me current_stock formula se match nahi tha (fix kiya)." % len(fix))

    if DRY_RUN:
        transaction.set_rollback(True)
        print("\n>>> DRY RUN: sab ROLLBACK, DB me kuch save nahi hua.")

print("\n" + "=" * 70)
print("SUCCESS:", len(ok), "| FAILED:", len(failed))
for f in failed:
    print("  FAILED:", f)
print("=" * 70)
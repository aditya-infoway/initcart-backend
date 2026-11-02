import os
import csv
from collections import defaultdict, Counter
from django.apps import apps
from django.db import transaction, connection
from django.db.models import ForeignKey
from django.utils import timezone

from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as IV
from pos.models.stock_transfer import VariantBranchMapping

DRY_RUN      = os.environ.get("DRY_RUN", "1") != "0"
SYNC_FIELDS  = os.environ.get("SYNC_FIELDS", "0") == "1"    # size/color/srno/barcode/warrantydate sync
DELETE_EMPTY = os.environ.get("DELETE_EMPTY", "1") != "0"   # khali + reference-free franchise item delete
TS = timezone.localtime().strftime("%Y%m%d_%H%M%S")
REPORT = "/app/structure_fix_%s_%s.csv" % ("dry" if DRY_RUN else "live", TS)

FIELDS_ID = ["size", "color", "srno", "barcode", "warrantydate"]
FIELDS_PRICE = ["mrp", "salesPrice"]          # sirf report, auto-change nahi
CLONE = ["entry_type", "itemName", "brand", "c_brand", "category", "c_category", "subCategory",
         "c_subCategory", "subSubCategory", "c_subSubCategory", "group", "unit", "hsnCode", "taxSlab",
         "short_description", "full_description", "keywords", "main_image", "thumbnail_image", "gallery",
         "product_condition", "return_policy", "estimated_delivery_time", "free_shipping",
         "warranty_available", "warranty_period", "warranty_type", "warranty_description",
         "description_features", "specifications"]


def fmt(dt):
    return timezone.localtime(dt).strftime("%d-%b %H:%M") if dt else "-"


def clone_kwargs(src, branch):
    kw = {fl: getattr(src, fl) for fl in CLONE}
    kw.update(branch=branch, created_by_superadmin=True, website_display=False, website_status="pending")
    return kw


def find_pairs():
    """Wo tables jinme item aur variant dono ke FK hain (PurchaseItem jaise)."""
    out = []
    for m in apps.get_models():
        if m in (Items, IV):
            continue
        fks = [x for x in m._meta.get_fields() if isinstance(x, ForeignKey)]
        ifs = [x.name for x in fks if x.related_model is Items]
        vfs = [x.name for x in fks if x.related_model is IV]
        for i in ifs:
            for v in vfs:
                out.append((m, i, v))
    return out


def has_refs(item_id):
    for rel in Items._meta.related_objects:
        try:
            if rel.related_model._default_manager.filter(**{rel.field.name: item_id}).exists():
                return True
        except Exception:
            return True
    return False


print("=" * 70)
print("MODE:", "DRY RUN (poora flow chalke ROLLBACK)" if DRY_RUN else "*** LIVE RUN ***")
print("SYNC_FIELDS:", SYNC_FIELDS, "| DELETE_EMPTY:", DELETE_EMPTY)
print("=" * 70)

with connection.cursor() as c:
    c.execute("SELECT COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
              "AND TABLE_NAME = %s AND COLUMN_NAME = 'itemName'", [Items._meta.db_table])
    r = c.fetchone()
print("itemName collation:", r[0] if r else "?", "(_ci = capital/small ek hi maana jata hai)")

# ---------- Data load ----------
sa = Branch.get_superadmin_branch()
if not sa:
    raise SystemExit("ABORT: Superadmin branch nahi mila.")
franchises = {b.id: b for b in Branch.objects.filter(ownership_type="franchise")}
fr_ids = list(franchises)
if not fr_ids:
    raise SystemExit("ABORT: Koi franchise nahi.")

sa_items = {r["id"]: r for r in Items.objects.filter(branch=sa).values("id", "itemName", "created_at", "updated_at")}
sa_var_item = dict(IV.objects.filter(item__branch=sa).values_list("id", "item_id"))
fr_items = {r["id"]: r for r in Items.objects.filter(branch_id__in=fr_ids).values(
    "id", "branch_id", "itemName", "created_at", "linked_product_id", "website_display")}
fr_var_item = dict(IV.objects.filter(item__branch_id__in=fr_ids).values_list("id", "item_id"))
rows = list(VariantBranchMapping.objects.filter(to_branch_id__in=fr_ids)
            .values_list("to_branch_id", "source_variant_id", "dest_variant_id"))
print("Superadmin items:", len(sa_items), "| Franchise items:", len(fr_items), "| Mapping rows:", len(rows))

# ---------- Superadmin me same naam wale items ----------
by_norm = defaultdict(list)
for i, r in sa_items.items():
    by_norm[" ".join((r["itemName"] or "").lower().split())].append(i)
dup = {k: v for k, v in by_norm.items() if len(v) > 1}
print("\nSUPERADMIN me abhi bhi same naam (capital/small/space ignore) wale items:", len(dup), "groups")
for k, v in list(dup.items())[:25]:
    print("   ", [(i, sa_items[i]["itemName"], fmt(sa_items[i]["created_at"])) for i in v])


def verify():
    res = {}
    fv = dict(IV.objects.filter(item__branch_id__in=fr_ids).values_list("id", "item_id"))
    fn = dict(Items.objects.filter(branch_id__in=fr_ids).values_list("id", "itemName"))
    for f in fr_ids:
        by_s, by_d = defaultdict(set), defaultdict(set)
        for sv, dv in VariantBranchMapping.objects.filter(to_branch_id=f).values_list("source_variant_id", "dest_variant_id"):
            s, d = sa_var_item.get(sv), fv.get(dv)
            if s is None or d is None:
                continue
            by_s[s].add(d)
            by_d[d].add(s)
        res[f] = dict(
            sa_items=len(by_s), fr_items=len(by_d),
            split=sum(1 for v in by_s.values() if len(v) > 1),
            merged=sum(1 for v in by_d.values() if len(v) > 1),
            badname=sum(1 for s, ds in by_s.items() if len(ds) == 1 and fn[next(iter(ds))] != sa_items[s]["itemName"]),
        )
    return res


def show(title, res):
    print("\n" + title)
    for f, r in res.items():
        print("   %-22s superadmin items=%d | franchise items=%d | merged=%d | split=%d | naam galat=%d"
              % (franchises[f].branch_name, r["sa_items"], r["fr_items"], r["merged"], r["split"], r["badname"]))


BEFORE = verify()
show("PARITY ABHI (merged/split/naam galat sab 0 hone chahiye):", BEFORE)

# ---------- Grouping ----------
dest_src = defaultdict(set)
for f, sv, dv in rows:
    dest_src[dv].add(sv)
shared_dest = {dv for dv, s in dest_src.items() if len(s) > 1}
if shared_dest:
    print("\nINFO: %d dest variants ek se zyada source se linked (skip): %s" % (len(shared_dest), sorted(shared_dest)[:10]))

group = defaultdict(list)                 # (f, S) -> [(sv, dv)]
hosts = defaultdict(set)                  # (f, D) -> {S}
owner_min = {}                            # (f, D, S) -> sabse purana dest variant id
for f, sv, dv in rows:
    s, d = sa_var_item.get(sv), fr_var_item.get(dv)
    if s is None or d is None or dv in shared_dest or fr_items[d]["branch_id"] != f:
        continue
    group[(f, s)].append((sv, dv))
    hosts[(f, d)].add(s)
    owner_min[(f, d, s)] = min(owner_min.get((f, d, s), dv), dv)

# ---------- PROOF ----------
merged_groups = sorted([(f, d, sorted(s)) for (f, d), s in hosts.items() if len(s) > 1])
print("\nPROOF 1: CONFLICT (ek franchise item me 2+ superadmin items):", len(merged_groups))
for f, d, srcs in merged_groups[:40]:
    D = fr_items[d]
    print("  [%s] franchise item #%s %r (bana: %s)" % (franchises[f].branch_name, d, D["itemName"], fmt(D["created_at"])))
    for s in srcs:
        S = sa_items[s]
        n = sum(1 for sv, dv in group[(f, s)] if fr_var_item[dv] == d)
        print("        <- superadmin #%s %r | bana: %s | edit: %s | variants: %d"
              % (s, S["itemName"], fmt(S["created_at"]), fmt(S["updated_at"]), n))

split_groups = sorted([(f, s) for (f, s), p in group.items() if len({fr_var_item[dv] for sv, dv in p}) > 1])
print("\nPROOF 2: SPLIT (ek superadmin item ke 2+ franchise items):", len(split_groups))
for f, s in split_groups[:40]:
    S = sa_items[s]
    print("  [%s] superadmin #%s %r | bana: %s | edit: %s"
          % (franchises[f].branch_name, s, S["itemName"], fmt(S["created_at"]), fmt(S["updated_at"])))
    cnt = Counter(fr_var_item[dv] for sv, dv in group[(f, s)])
    for d, n in sorted(cnt.items()):
        print("        franchise #%s %r | bana: %s | variants: %d" % (d, fr_items[d]["itemName"], fmt(fr_items[d]["created_at"]), n))

# ---------- Plan: canonical item ----------
eff = {k: set(v) for k, v in hosts.items()}
canon, pending, skipped_web, cands = {}, [], [], {}
for (f, s), pairs_ in group.items():
    cand = sorted({fr_var_item[dv] for sv, dv in pairs_})
    cands[(f, s)] = cand
    if any(fr_items[x]["linked_product_id"] or fr_items[x]["website_display"] for x in cand):
        skipped_web.append((f, s, cand))
        continue
    pure = [x for x in cand if hosts[(f, x)] == {s}]
    if pure:
        canon[(f, s)] = min(pure)
        for x in cand:
            if x != canon[(f, s)]:
                eff[(f, x)].discard(s)
    else:
        pending.append((f, s))
for f, s in pending:
    cand = cands[(f, s)]
    pure = [x for x in cand if eff[(f, x)] == {s}]
    if pure:
        pick = min(pure)
    else:
        owned = [x for x in cand if min(eff[(f, x)], key=lambda z: owner_min[(f, x, z)]) == s]
        pick = min(owned) if owned else None
    canon[(f, s)] = pick
    for x in cand:
        if x != pick:
            eff[(f, x)].discard(s)

moves, new_items, renames = [], [], []
for (f, s), pairs_ in group.items():
    if (f, s) not in canon:
        continue
    c_id = canon[(f, s)]
    if c_id is None:
        new_items.append((f, s))
    else:
        if fr_items[c_id]["itemName"] != sa_items[s]["itemName"]:
            renames.append((c_id, sa_items[s]["itemName"], fr_items[c_id]["itemName"]))
    for sv, dv in pairs_:
        if fr_var_item[dv] != c_id:
            moves.append((f, s, dv, fr_var_item[dv], c_id))

per = defaultdict(Counter)
for m_ in moves:
    per[m_[0]]["variants_move"] += 1
for f, s in new_items:
    per[f]["naye_items"] += 1
for c_id, new, old in renames:
    per[fr_items[c_id]["branch_id"]]["rename"] += 1
print("\nPLAN:")
for f in fr_ids:
    print("   %-22s %s" % (franchises[f].branch_name, dict(per[f])))
print("   SKIP (website/linked_product wale): %d %s" % (len(skipped_web), [(franchises[f].branch_name, s) for f, s, _ in skipped_web[:5]]))

# ---------- Variant field farak ----------
src_vals = {r["id"]: r for r in IV.objects.filter(item__branch=sa).values("id", *FIELDS_ID, *FIELDS_PRICE)}
dst_vals = {r["id"]: r for r in IV.objects.filter(item__branch_id__in=fr_ids).values("id", *FIELDS_ID, *FIELDS_PRICE)}
diff = defaultdict(list)
for f, sv, dv in rows:
    a, b = src_vals.get(sv), dst_vals.get(dv)
    if not a or not b:
        continue
    for fld in FIELDS_ID + FIELDS_PRICE:
        if (a[fld] or None) != (b[fld] or None):
            diff[fld].append((f, dv, a[fld], b[fld]))
print("\nVARIANT FIELD farak (superadmin vs franchise):")
for fld in FIELDS_ID + FIELDS_PRICE:
    print("   %-12s: %d" % (fld, len(diff[fld])))
    for f, dv, va, vb in diff[fld][:3]:
        print("        [%s] variant #%s superadmin=%r franchise=%r" % (franchises[f].branch_name, dv, va, vb))
print("   (mrp/salesPrice kabhi auto-change nahi hote. Baaki 5 fields sirf SYNC_FIELDS=1 par.)")

mapped_src = {sv for _, sv, _ in rows}
unmapped = [v for v in sa_var_item if v not in mapped_src]
print("Superadmin variants jinka franchise me mapping nahi (naye, nightly job se jayenge):", len(unmapped))

# ---------- Report CSV ----------
with open(REPORT, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["action", "franchise", "source_item", "dest_item", "dest_variant", "old", "new", "note"])
    for f, s, dv, cur_item, target in moves:
        w.writerow(["MOVE", franchises[f].branch_name, s, cur_item, dv, "", "", "to=%s" % (target or "NEW")])
    for f, s in new_items:
        w.writerow(["NEW_ITEM", franchises[f].branch_name, s, "", "", "", sa_items[s]["itemName"], ""])
    for c_id, new, old in renames:
        w.writerow(["RENAME", franchises[fr_items[c_id]["branch_id"]].branch_name, "", c_id, "", old, new, ""])
    for f, s, cand in skipped_web:
        w.writerow(["SKIP_WEBSITE", franchises[f].branch_name, s, cand, "", "", "", ""])
    for fld in FIELDS_ID + FIELDS_PRICE:
        for f, dv, va, vb in diff[fld]:
            w.writerow(["FIELD_DIFF", franchises[f].branch_name, "", "", dv, vb, va, fld])
print("\nReport file:", REPORT, "(host par: /var/www/supercommerce_com/backend/)")

# ---------- Apply (DRY me bhi chalta hai, end me rollback) ----------
pairs = find_pairs()
print("\nItem+Variant dono wale tables (item bhi update honge):", sorted({"%s.%s" % (m.__name__, i) for m, i, v in pairs}))
stats = Counter()
kept = []
with transaction.atomic():
    new_id = {}
    for f, s in new_items:
        d = Items.objects.create(**clone_kwargs(Items.objects.get(id=s), franchises[f]))
        new_id[(f, s)] = d.id
        stats["naye_items_bane"] += 1

    emptied = set()
    for f, s, dv, cur_item, target in moves:
        tid = new_id[(f, s)] if target is None else target
        IV.objects.filter(id=dv).update(item_id=tid)
        stats["variants_moved"] += 1
        emptied.add(cur_item)
        for m, i, v in pairs:
            n = m._default_manager.filter(**{v: dv, i: cur_item}).update(**{i: tid})
            if n:
                stats["rows %s.%s" % (m.__name__, i)] += n

    now = timezone.now()
    for c_id, new, old in renames:
        Items.objects.filter(id=c_id).update(itemName=new, updated_at=now)
        stats["renamed"] += 1

    if DELETE_EMPTY:
        for d in sorted(emptied):
            if IV.objects.filter(item_id=d).exists():
                continue
            if has_refs(d):
                kept.append(d)
                stats["khali_par_reference_hai(rakha)"] += 1
                continue
            Items.objects.filter(id=d).delete()
            stats["khali_item_delete"] += 1

    if SYNC_FIELDS:
        for fld in FIELDS_ID:
            for f, dv, va, vb in diff[fld]:
                IV.objects.filter(id=dv).update(**{fld: va})
                stats["sync_%s" % fld] += 1

    AFTER = verify()
    show("PARITY BAAD ME (%s):" % ("predicted" if DRY_RUN else "actual"), AFTER)
    print("\nKARYAVAHI:", dict(stats))
    if kept:
        print("Khali par referenced items (rakhe gaye):", kept[:20])
    if DRY_RUN:
        transaction.set_rollback(True)
        print("\n>>> DRY RUN: sab ROLLBACK, DB me kuch change nahi hua.")
    else:
        print("\n>>> LIVE: sab save ho gaya.")
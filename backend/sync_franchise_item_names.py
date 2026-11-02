import os
import csv
from collections import defaultdict
from django.db import transaction
from django.utils import timezone

from pos.models.branch import Branch
from pos.models.items import items as Items, itemvariants as IV
from pos.models.b2b_sales import B2BSaleItem
from pos.models.stock_transfer import VariantBranchMapping, StockTransferItem

DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
TS = timezone.localtime().strftime("%Y%m%d_%H%M%S")
REPORT = "/app/name_sync_%s_%s.csv" % ("dry" if DRY_RUN else "live", TS)

print("=" * 70)
print("MODE:", "DRY RUN (kuch save nahi hoga)" if DRY_RUN else "*** LIVE RUN ***")
print("=" * 70)


def has_fields(model, names):
    have = {f.name for f in model._meta.get_fields()}
    return set(names) <= have, sorted(set(names) - have)


ok, miss = has_fields(VariantBranchMapping, ["source_variant", "to_branch", "dest_variant"])
if not ok:
    raise SystemExit("ABORT: VariantBranchMapping me fields nahi mile: %s" % miss)
use_st, _ = has_fields(StockTransferItem, ["transfer", "from_variant", "to_variant"])

# ---------- Branches ----------
sa = Branch.get_superadmin_branch()
if not sa:
    raise SystemExit("ABORT: Superadmin branch nahi mila.")
franchises = {b.id: b.branch_name for b in Branch.objects.filter(ownership_type="franchise")}
print("Superadmin:", sa.id, sa.branch_name)
print("Franchises:", list(franchises.items()))
if not franchises:
    raise SystemExit("Koi franchise nahi.")
fr_ids = list(franchises.keys())

# ---------- Data load ----------
sa_items = {r["id"]: r["itemName"] for r in Items.objects.filter(branch=sa).values("id", "itemName")}
sa_var_item = dict(IV.objects.filter(item__branch=sa).values_list("id", "item_id"))

fr_items = {
    r["id"]: r
    for r in Items.objects.filter(branch_id__in=fr_ids).values(
        "id", "branch_id", "itemName", "created_by_superadmin", "linked_product_id"
    )
}
fr_var_item = dict(IV.objects.filter(item__branch_id__in=fr_ids).values_list("id", "item_id"))
print("Superadmin items:", len(sa_items), "| Franchise items (total):", len(fr_items))

# ---------- Links: (franchise, dest_variant, source_variant) ----------
links = set()
for to_b, dv, sv in VariantBranchMapping.objects.filter(to_branch_id__in=fr_ids).values_list(
        "to_branch_id", "dest_variant_id", "source_variant_id"):
    links.add((to_b, dv, sv))
n_map = len(links)

before = len(links)
for to_b, dv, sv in B2BSaleItem.objects.filter(
        to_variant__isnull=False, sale__to_branch_id__in=fr_ids).values_list(
        "sale__to_branch_id", "to_variant_id", "from_variant_id"):
    links.add((to_b, dv, sv))
n_b2b_extra = len(links) - before

before = len(links)
if use_st:
    for to_b, dv, sv in StockTransferItem.objects.filter(
            to_variant__isnull=False, transfer__to_branch_id__in=fr_ids).values_list(
            "transfer__to_branch_id", "to_variant_id", "from_variant_id"):
        links.add((to_b, dv, sv))
n_st_extra = len(links) - before

print("\nLinks: mapping=%d | B2B se extra=%d | Stock Transfer se extra=%d | total=%d"
      % (n_map, n_b2b_extra, n_st_extra, len(links)))

# ---------- Group: dest item -> source items ----------
by_dest = defaultdict(set)
src_to_dest = defaultdict(set)
bad = {"dest_missing": 0, "src_not_superadmin": 0, "branch_mismatch": 0}
for to_b, dv, sv in links:
    d_item = fr_var_item.get(dv)
    s_item = sa_var_item.get(sv)
    if d_item is None:
        bad["dest_missing"] += 1
        continue
    if s_item is None:
        bad["src_not_superadmin"] += 1
        continue
    if fr_items[d_item]["branch_id"] != to_b:
        bad["branch_mismatch"] += 1
        continue
    by_dest[d_item].add(s_item)
    src_to_dest[(s_item, to_b)].add(d_item)
print("Link skip (dikkat nahi, sirf info):", bad)
print("Franchise items jinka superadmin source mila:", len(by_dest))

# ---------- Plan ----------
rename, same, conflicts = [], 0, []
for d_id, s_ids in by_dest.items():
    names = {sa_items[s] for s in s_ids}
    d = fr_items[d_id]
    if len(names) != 1:
        conflicts.append((d_id, franchises[d["branch_id"]], d["itemName"], sorted(names)))
        continue
    target = next(iter(names))
    if d["itemName"] == target:
        same += 1
    else:
        rename.append((d_id, d["branch_id"], d["itemName"], target, d["linked_product_id"]))

splits = [(s, b, sorted(ds)) for (s, b), ds in src_to_dest.items() if len(ds) > 1]
unlinked = [r for r in fr_items.values() if r["created_by_superadmin"] and r["id"] not in by_dest]

final = {i: r["itemName"] for i, r in fr_items.items()}
for d_id, b, old, new, lp in rename:
    final[d_id] = new
renamed_ids = {r[0] for r in rename}
cnt = defaultdict(list)
for i, nm in final.items():
    cnt[(fr_items[i]["branch_id"], nm)].append(i)
dups_new = {k: v for k, v in cnt.items() if len(v) > 1 and renamed_ids & set(v)}

per = defaultdict(int)
for r in rename:
    per[r[1]] += 1

print("\n" + "-" * 70)
print("PEHLE SE SAHI NAAM        :", same)
print("RENAME HOGA               :", len(rename))
for b, n in per.items():
    print("     %s (id=%s): %d" % (franchises[b], b, n))
print("CONFLICT (skip)           :", len(conflicts))
for c in conflicts[:15]:
    print("     ", c)
print("SPLIT ITEMS (merge nahi)  :", len(splits))
for s in splits[:10]:
    print("      superadmin item", s[0], "-> franchise", s[1], "ke dest items", s[2])
print("UNLINKED franchise items  :", len(unlinked), "(chhedenge nahi)")
for r in unlinked[:10]:
    print("     ", r["id"], franchises[r["branch_id"]], "|", r["itemName"])
print("Rename ke baad same naam  :", len(dups_new), "(split items ki wajah se expected)")
print("Rename wale items me linked_product wale:", sum(1 for r in rename if r[4]))
print("-" * 70)
print("Samples (pehle 15):")
for d_id, b, old, new, lp in rename[:15]:
    print("   [%s] #%s | %r -> %r" % (franchises[b], d_id, old, new))

with open(REPORT, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["franchise_id", "franchise", "dest_item_id", "old_name", "new_name", "linked_product_id"])
    for d_id, b, old, new, lp in rename:
        w.writerow([b, franchises[b], d_id, old, new, lp or ""])
print("\nReport file:", REPORT, "(host par: /var/www/supercommerce_com/backend/)")

# ---------- Apply ----------
if DRY_RUN:
    print("\n>>> DRY RUN: DB me kuch change nahi hua.")
elif not rename:
    print("\nKuch rename karne ko nahi hai.")
else:
    now = timezone.now()
    with transaction.atomic():
        for d_id, b, old, new, lp in rename:
            Items.objects.filter(id=d_id).update(itemName=new, updated_at=now)

    ids = [r[0] for r in rename]
    got = {}
    for i in range(0, len(ids), 1000):
        got.update(dict(Items.objects.filter(id__in=ids[i:i + 1000]).values_list("id", "itemName")))
    wrong = [r for r in rename if got.get(r[0]) != r[3]]
    print("\n>>> LIVE: %d items ka naam badla | verify me galat: %d" % (len(rename), len(wrong)))
    for r in wrong[:10]:
        print("   GALAT:", r)
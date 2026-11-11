#!/usr/bin/env python3 -I
"""Re-key the CA supplemental file for one country so it matches that country's primary feed.
Rows are kept only if their ID exists in the country's primary file (a supplemental row for a missing item is ignored by
Merchant Center, so parity is enforced here). No price column: the primary feed already carries the local price.
The variant_option columns are dropped: the primary feed carries material, size and color as structured attributes.
Usage: rekey_supplemental.py <CC> supplemental_all.csv GOOGLE_PRIMARY_<CC>.tsv out.csv"""
import csv, sys
cc, sup, primary, out = sys.argv[1:5]
csv.field_size_limit(10**8)
ids = {r["id"] for r in csv.DictReader(open(primary, encoding="utf-8", newline=""), delimiter="\t")}
with open(sup, encoding="utf-8", newline="") as f:
    rd = csv.reader(f); header = next(rd); rows = list(rd)
if header[0] != "id" or not all(r[0].startswith("shopify_CA_") for r in rows):
    sys.exit("supplemental file must have IDs shopify_CA_...")
keep_cols = [i for i, c in enumerate(header) if c != "variant_option"]
header = [header[i] for i in keep_cols]
rows = [[r[i] for i in keep_cols] for r in rows]
kept = []
for r in rows:
    new = f"shopify_{cc}_" + r[0][len("shopify_CA_"):]
    if new in ids:
        kept.append([new] + r[1:])
dropped = len(rows) - len(kept)
if len(kept) < 0.9 * len(ids):
    sys.exit(f"only {len(kept)} of {len(ids)} primary items are covered; refusing to write")
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f); w.writerow(header); w.writerows(kept)
print(f"{cc}: {len(kept)} rows written ({dropped} supplemental rows had no primary item; {len(ids) - len(kept)} primary items have no supplemental row)")

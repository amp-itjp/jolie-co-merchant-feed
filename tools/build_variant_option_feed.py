#!/usr/bin/env python3 -I
"""Build the Merchant Center supplemental file (GOOGLE_SUPPLEMENTAL_ALL.csv format).

The Essential Product Feeds CSV puts every variant_option pair in one cell
("Bar length:10mm,Material:14k Gold"). Merchant Center needs one name:value pair per column,
every column named variant_option. Everything else is passed through unchanged.

Usage: build_variant_option_feed.py <source csv path or URL> <out.csv>
Output columns: id, item_group_id, item_group_title, title, description, variant_option x N
(N is the widest variant in the source, so a fourth pair widens the file instead of failing).
Rows with no title are dropped: they are the Gift and Piercing Concierge variants that the
Merchant Center exclusion rule already hides, and they supply nothing.
"""
import csv, io, re, subprocess, sys

SRC, OUT = sys.argv[1], sys.argv[2]
KEEP = ["id", "item_group_id", "item_group_title", "title", "description"]
# A new pair starts at a comma followed by "Name:"; a comma inside a value stays in the value.
PAIR_SPLIT = re.compile(r",(?=[A-Za-z][A-Za-z ]*:)")

csv.field_size_limit(10**8)
if SRC.startswith("http"):
    got = subprocess.run(["curl", "-sfL", "--max-time", "180", "-A", "Mozilla/5.0", SRC], capture_output=True)
    if got.returncode != 0:
        sys.exit(f"download failed (curl exit {got.returncode})")
    raw = got.stdout.decode("utf-8")
else:
    raw = open(SRC, encoding="utf-8", newline="").read()

rows = list(csv.DictReader(io.StringIO(raw, newline="")))
missing = [c for c in KEEP + ["variant_option"] if not rows or c not in rows[0]]
if missing:
    sys.exit(f"source is missing columns: {missing}")

kept, widest = [], 0
for r in rows:
    if not (r["title"] or "").strip():
        continue
    v = (r["variant_option"] or "").strip()
    pairs = PAIR_SPLIT.split(v) if v else []
    if any(":" not in p for p in pairs):
        sys.exit(f"unparseable variant_option on {r['id']}: {v!r}")
    widest = max(widest, len(pairs))
    kept.append((r, pairs))

# Sanity floor so a broken source never replaces a good file.
if len(kept) < 10000:
    sys.exit(f"only {len(kept)} rows with a title; refusing to write {OUT}")

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(KEEP + ["variant_option"] * widest)
    for r, pairs in kept:
        w.writerow([r[c] for c in KEEP] + pairs + [""] * (widest - len(pairs)))
print(f"source rows {len(rows)}, written {len(kept)}, variant_option columns {widest}, wrote {OUT}")

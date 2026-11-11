#!/usr/bin/env python3 -I
"""Build the Merchant Center supplemental file (GOOGLE_SUPPLEMENTAL_ALL.csv format).

The Essential Product Feeds CSV carries two values Google wants as repeated columns:
  variant_option    one cell "Bar length:10mm,Material:14k Gold"  ->  one name:value pair per column
  product_highlight one cell JSON list ["a","b"] (optional column) ->  one highlight per column
Everything else is passed through unchanged, and product_type is added from the group ID prefix.

NOTE: variant_option is still read and validated from the source but is NOT written: the primary feed now carries
material, size and color as structured attributes.
Usage: build_variant_option_feed.py <source csv path or URL> <out.csv>
Output columns: id, item_group_id, item_group_title, title, description,
product_type, product_highlight x M (M is 0 when the source has no product_highlight column).
Rows with no title are dropped: they are the Gift and Piercing Concierge variants that the
Merchant Center exclusion rule already hides, and they supply nothing.
"""
import csv, io, json, re, subprocess, sys

SRC, OUT = sys.argv[1], sys.argv[2]
KEEP = ["id", "item_group_id", "item_group_title", "title", "description"]
# A new pair starts at a comma followed by "Name:"; a comma inside a value stays in the value.
PAIR_SPLIT = re.compile(r",(?=[A-Za-z][A-Za-z ]*:)")

# product_type paths, keyed by the item_group_id prefix. Exact group IDs win over prefixes.
PRODUCT_TYPE_BY_PREFIX = {
    "br": "Jewelry > Body Jewelry > Belly Rings",
    "nb": "Jewelry > Body Jewelry > Nipple Barbells",
    "ch": "Jewelry > Body Jewelry > Charms",
    "pt": "Jewelry > Body Jewelry > Tops",
    "er": "Jewelry > Earrings",
}
PRODUCT_TYPE_BY_GROUP = {
    "pt_luna_ruler_kit": "Accessories > Fitting Tools",
    "marry-me-charm": "Jewelry > Body Jewelry > Charms",
    "marry_me_charm": "Jewelry > Body Jewelry > Charms",
}
HIGHLIGHT_MAX_CHARS = 150  # Google: 2 to 100 highlights, each up to 150 characters


def product_type(group_id):
    if group_id in PRODUCT_TYPE_BY_GROUP:
        return PRODUCT_TYPE_BY_GROUP[group_id]
    return PRODUCT_TYPE_BY_PREFIX.get(group_id.split("_")[0], "")


def highlights(cell, stats):
    """Parse the JSON-list cell into clean highlights; [] when fewer than 2 survive."""
    cell = (cell or "").strip()
    if not cell:
        return []
    try:
        items = json.loads(cell)
    except ValueError:
        items = [cell]
    if not isinstance(items, list):
        items = [items]
    out = []
    for t in items:
        t = re.sub(r"\s+", " ", str(t)).strip().strip("\"'").strip()
        if not t or t in out:
            continue
        if len(t) > HIGHLIGHT_MAX_CHARS:
            stats["too_long"] += 1
            continue
        out.append(t)
    if len(out) < 2:
        stats["under_two"] += 1
        return []
    return out


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
has_highlights = "product_highlight" in rows[0]

kept, widest, widest_hl = [], 0, 0
stats = {"too_long": 0, "under_two": 0, "no_type": 0, "with_highlights": 0}
for r in rows:
    if not (r["title"] or "").strip():
        continue
    v = (r["variant_option"] or "").strip()
    pairs = PAIR_SPLIT.split(v) if v else []
    if any(":" not in p for p in pairs):
        sys.exit(f"unparseable variant_option on {r['id']}: {v!r}")
    ptype = product_type(r["item_group_id"])
    if not ptype:
        stats["no_type"] += 1
    hl = highlights(r["product_highlight"], stats) if has_highlights else []
    stats["with_highlights"] += bool(hl)
    widest, widest_hl = max(widest, len(pairs)), max(widest_hl, len(hl))
    kept.append((r, pairs, ptype, hl))

# Sanity floor so a broken source never replaces a good file.
if len(kept) < 10000:
    sys.exit(f"only {len(kept)} rows with a title; refusing to write {OUT}")

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(KEEP + ["product_type"] + ["product_highlight"] * widest_hl)
    for r, pairs, ptype, hl in kept:
        w.writerow([r[c] for c in KEEP] + [ptype] + hl + [""] * (widest_hl - len(hl)))
print(f"source rows {len(rows)}, written {len(kept)}, variant_option columns dropped from the output (widest source row had {widest}), "
      f"product_highlight columns {widest_hl}, rows with highlights {stats['with_highlights']}, "
      f"rows without a product_type {stats['no_type']}, highlights dropped (over {HIGHLIGHT_MAX_CHARS} chars) {stats['too_long']}, "
      f"rows with fewer than 2 highlights {stats['under_two']}, wrote {OUT}")

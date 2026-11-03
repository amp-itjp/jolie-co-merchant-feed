#!/usr/bin/env python3 -I
"""Compare two supplemental source CSVs (EPF vs the Shopify export) and print a parity report.
Usage: compare_feeds.py <epf.csv> <shopify.csv>"""
import csv, sys

csv.field_size_limit(10**8)
load = lambda p: {r["id"]: r for r in csv.DictReader(open(p, encoding="utf-8", newline=""))}
a, b = load(sys.argv[1]), load(sys.argv[2])
norm = lambda s: (s or "").replace("\r\n", "\n").strip()
print(f"EPF rows {len(a)}, Shopify rows {len(b)}")
only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
print(f"only in EPF {len(only_a)}, only in Shopify {len(only_b)}")
for k in only_a[:3]: print("  only EPF:", k)
for k in only_b[:3]: print("  only Shopify:", k)
for col in ["item_group_id", "item_group_title", "title", "description", "variant_option"]:
    diff = [k for k in a if k in b and norm(a[k].get(col)) != norm(b[k].get(col))]
    print(f"{col}: {len(diff)} of {len(set(a) & set(b))} differ")
    for k in diff[:2]:
        print("   ", k, "| EPF:", norm(a[k].get(col))[:80].replace("\n", " "), "| SHOP:", norm(b[k].get(col))[:80].replace("\n", " "))
hl = sum(1 for r in b.values() if norm(r.get("product_highlight")))
print(f"Shopify rows with a product_highlight value: {hl}")

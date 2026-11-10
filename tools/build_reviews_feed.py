#!/usr/bin/env python3 -I
"""Build a Google Merchant Center product reviews feed (XML schema 2.3) from Judge.me reviews.

Inputs
  reviews.json   list of Judge.me review objects (from the public reviews_for_widget endpoint, or
                 converted from a Judge.me export). Needs: uuid, rating, title, body_html, created_at,
                 reviewer_name, is_anonymous_reviewer, verified_buyer, product_url.
  variants.csv   one row per variant with handle and variant_mpn (the Shopify export).
Each review is attached to every variant MPN of the product it was written for, plus brand.
Reviews with no product (store reviews) are skipped, as are Gift and Piercing Concierge variants.

Usage: build_reviews_feed.py reviews.json variants.csv out.xml
"""
import csv, html, json, re, sys
from collections import defaultdict
from xml.sax.saxutils import escape

REVIEWS, VARIANTS, OUT = sys.argv[1:4]
SITE, BRAND, PUBLISHER = "https://jolie-co.com", "Jolie Co Jewelry", "Jolie Co Jewelry"

mpns = defaultdict(list)
titles = {}
with open(VARIANTS, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        m = r["variant_mpn"] or r["sku"]
        if not m or "GIFT" in m.upper() or "-PC" in m.upper():
            continue
        mpns[r["handle"]].append(m)
        titles[r["handle"]] = r["title"]

def text(s):
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "")
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()

out, skipped = [], defaultdict(int)
for r in sorted(json.load(open(REVIEWS)), key=lambda r: r["created_at"]):
    url = r.get("product_url") or ""
    handle = url.split("/products/")[-1].split("?")[0] if "/products/" in url else ""
    if not handle:
        skipped["no product (store review)"] += 1; continue
    if handle not in mpns:
        skipped["product not in feed / no MPN"] += 1; continue
    body = text(r["body_html"])
    if not body:
        skipped["empty body"] += 1; continue
    anon = "true" if r.get("is_anonymous_reviewer") else "false"
    name = "Anonymous" if anon == "true" else (r.get("reviewer_name") or "Anonymous")
    ts = r["created_at"][:19] + "Z"
    link = f"{SITE}/products/{handle}"
    mp = "".join(f"<mpn>{escape(m)}</mpn>" for m in mpns[handle])
    out.append(f"""<review>
<review_id>{escape(r['uuid'])}</review_id>
<reviewer><name is_anonymous="{anon}">{escape(name)}</name></reviewer>
<review_timestamp>{ts}</review_timestamp>
<title>{escape(text(r.get('title')))}</title>
<content>{escape(body)}</content>
<review_url type="singleton">{escape(link)}</review_url>
<ratings><overall min="1" max="5">{int(r['rating'])}</overall></ratings>
<products><product><product_ids><mpns>{mp}</mpns><brands><brand>{escape(BRAND)}</brand></brands></product_ids>
<product_name>{escape(html.unescape(titles[handle]))}</product_name><product_url>{escape(link)}</product_url></product></products>
{'<collection_method>post_fulfillment</collection_method>' if r.get('verified_buyer') else ''}
</review>""")

with open(OUT, "w", encoding="utf-8") as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<feed xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:noNamespaceSchemaLocation="http://www.google.com/shopping/reviews/schema/product/2.3/product_reviews.xsd">\n'
            f"<version>2.3</version>\n<publisher><name>{escape(PUBLISHER)}</name></publisher>\n<reviews>\n")
    f.write("\n".join(out)); f.write("\n</reviews>\n</feed>\n")
print(f"wrote {len(out)} reviews to {OUT}; skipped: {dict(skipped)}")

#!/usr/bin/env python3 -I
"""Build one Merchant Center primary feed per country from catalog.csv (shopify_primary_export.py output).

Each file is a tab-separated feed for one country (feed label = country code):
  id shopify_<CC>_<product>_<variant>, title, description, link (that country's store URL, so the page shows the
  same price), image_link, additional_image_link, availability, price (Shopify's own price for the country, in
  the country's currency), brand, mpn, condition, item_group_id, product_type, material (option Material), size (option Bar length, else Ball size).
Gift and Piercing Concierge variants (MPN contains GIFT or -PC) are left out, as in the current exclusion rule.
The run stops, and writes nothing, if a variant lacks a price for a country, or Shopify's currency differs from
the expected currency for that country.

Usage: build_primary_feed.py catalog.csv outdir [--skip-unpriced]
"""
import csv, json, os, re, sys
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
COUNTRIES = {"AU": "AUD", "BH": "CAD", "BE": "EUR", "CA": "CAD", "CZ": "CZK", "DK": "EUR", "FR": "EUR", "DE": "EUR",
             "GR": "EUR", "IE": "EUR", "IT": "EUR", "KW": "CAD", "LV": "EUR", "MX": "MXN", "NL": "EUR", "NZ": "NZD",
             "NO": "NOK", "OM": "CAD", "PL": "PLN", "RO": "EUR", "SA": "SAR", "ES": "EUR", "SE": "SEK", "CH": "CHF",
             "AE": "AED", "GB": "GBP", "US": "USD"}
PRODUCT_TYPE = {"br": "Jewelry > Body Jewelry > Belly Rings", "nb": "Jewelry > Body Jewelry > Nipple Barbells",
                "ch": "Jewelry > Body Jewelry > Charms", "pt": "Jewelry > Body Jewelry > Tops", "er": "Jewelry > Earrings"}
FIELDS = ["id", "title", "description", "link", "image_link", "additional_image_link", "availability", "price",
          "brand", "mpn", "condition", "item_group_id", "product_type", "material", "size"]
# Variant option names (Shopify) that fill Google's structured attributes. The first name found wins.
OPTION_MAP = {"material": ["Material Option", "Material"], "size": ["Bar Length", "Ball Size"]}
METAL = re.compile(r"\b(Yellow|White|Rose)\b(?:[ -]Gold)?", re.I)


def clean_size(v):
    v = re.sub(r"\s*\(.*?\)", "", v).strip()
    return v + "mm" if re.fullmatch(r"\d+(\.\d+)?", v) else v


def clean_material(v, title, handle):
    # Shopify's Material option is a karat ("14k") or karat plus colour ("14k Rose"); a bare karat takes the gold
    # colour from the product title, then from the URL handle. Result matches the supplemental wording.
    m = re.fullmatch(r"(\d+)k(?:\s+(?:solid\s+)?(yellow|white|rose)(?:\s+gold)?)?", v.strip(), re.I)
    if not m:
        return v
    colour = m.group(2) or next((g.group(1) for g in (METAL.search(title), METAL.search(handle)) if g), "")
    return f"{m.group(1)}k Solid {colour.title()} Gold" if colour else v


args = [a for a in sys.argv[1:] if not a.startswith("--")]
CATALOG, OUTDIR = args
skip = "--skip-unpriced" in sys.argv
urls = json.load(open(os.path.join(HERE, "market_urls.json")))

csv.field_size_limit(10**8)
rows = [r for r in csv.DictReader(open(CATALOG, encoding="utf-8", newline=""))
        if "GIFT" not in r["mpn"].upper() and "-PC" not in r["mpn"].upper()]
names_seen = {}
for r in rows:
    for k, _ in json.loads(r.get("options") or "[]"):
        names_seen[k] = names_seen.get(k, 0) + 1
print("option names:", sorted(names_seen.items(), key=lambda kv: -kv[1])[:20])
os.makedirs(OUTDIR, exist_ok=True)
for cc, cur in COUNTRIES.items():
    out, bad = [], []
    for r in rows:
        p = r[f"price_{cc}"]
        if not p:
            bad.append(r["variant_id"]); continue
        amount, code = p.split()
        if code != cur:
            sys.exit(f"{cc}: Shopify prices in {code} but {cur} is expected; no files written")
        opts = {k.strip().lower(): v for k, v in json.loads(r.get("options") or "[]")}
        mapped = {g: next((opts[n.lower()] for n in names if opts.get(n.lower())), "")[:200] for g, names in OPTION_MAP.items()}
        mapped["size"] = clean_size(mapped["size"])
        mapped["material"] = clean_material(mapped["material"], r["title"], r["handle"])
        title = r["title"] if r["variant_title"] in ("", "Default Title") else f"{r['title']}, {r['variant_title']}"
        out.append({
            "id": f"shopify_{cc}_{r['product_id']}_{r['variant_id']}", "title": title[:150],
            "description": " ".join(r["description"].split())[:5000] or title,
            "link": f"{urls[cc]}/products/{r['handle']}?variant={r['variant_id']}", "image_link": r["image_link"],
            "additional_image_link": ",".join(r["additional_images"].split("|")[:10]) if r["additional_images"] else "",
            "availability": "in_stock" if r["available"] == "1" else "out_of_stock",
            "price": f"{Decimal(amount).quantize(Decimal('0.01'), ROUND_HALF_UP)} {code}", "brand": r["vendor"],
            "mpn": r["mpn"], "condition": "new", "item_group_id": r["group_id"],
            "product_type": PRODUCT_TYPE.get(r["group_id"].split("_")[0], ""), **mapped})
    if bad and not skip:
        sys.exit(f"{cc}: {len(bad)} variants have no price, e.g. {bad[:3]}; no files written")
    with open(os.path.join(OUTDIR, f"GOOGLE_PRIMARY_{cc}.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        w.writeheader(); w.writerows(out)
print(f"{len(rows)} variants x {len(COUNTRIES)} countries written to {OUTDIR}")

#!/usr/bin/env python3 -I
"""Build one Merchant Center primary feed per country from catalog.csv (shopify_primary_export.py output).

Each file is a tab-separated feed for one country (feed label = country code):
  id shopify_<CC>_<product>_<variant>, title, description, link (that country's store URL, so the page shows the
  same price), image_link, additional_image_link, availability, price (Shopify's own price for the country, in
  the country's currency), brand, mpn, condition, item_group_id, product_type, material (option Material), size (option Bar length, else Ball size).
Gift and Piercing Concierge variants (MPN contains GIFT or -PC, set in mapping_rules.json) are left out.
The mapping lives in mapping_rules.json; run events and mapping_report.json go to $RUN_LOG_DIR (default ./logs).
The run stops, and writes nothing, if a variant lacks a price for a country, or Shopify's currency differs from
the expected currency for that country.

Usage: build_primary_feed.py catalog.csv outdir [--skip-unpriced]
"""
import csv, json, os, re, shutil, sys
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # -I mode does not add the script folder
from runlog import Step

RULES = json.load(open(os.path.join(HERE, "mapping_rules.json"), encoding="utf-8"))
COUNTRIES = RULES["countries"]
PRODUCT_TYPE, GOOGLE_CATEGORY = RULES["product_type"], RULES["google_category"]
OPTION_MAP = RULES["option_map"]  # Variant option names (Shopify) that fill Google attributes; the first name found wins
FIELDS = [f["google"] for f in RULES["fields"]]
NATIVE = "native_commerce(checkout_eligibility)"  # Gemini checkout opt-in; false until UCP onboarding is done
GENDER, AGE_GROUP = RULES["defaults"]["gender"], RULES["defaults"]["age_group"]  # set only when a category matches
METAL = re.compile(r"\b(Yellow|White|Rose)\b(?:[ -]Gold)?", re.I)


def metal_colour(material):
    # "14k Solid Rose Gold" -> "Rose Gold"; "Platinum" -> "Platinum"; a bare karat has no colour.
    m = re.search(r"\b(Yellow|White|Rose) Gold\b", material, re.I)
    return f"{m.group(1).title()} Gold" if m else ("Platinum" if material.lower() == "platinum" else "")


def clean_size(v):
    v = re.sub(r"\s*\(.*?\)", "", v).strip()
    return v + "mm" if re.fullmatch(r"\d+(\.\d+)?", v) else v


def clean_material(v, title, handle, mpn=""):
    # Shopify's Material option is a karat ("14k") or karat plus colour ("14k Rose"); a bare karat takes the gold
    # colour from the product title, then from the URL handle. Result matches the supplemental wording.
    m = re.fullmatch(r"(\d+)k(?:\s+(?:solid\s+)?(yellow|white|rose)(?:\s+gold)?)?", v.strip(), re.I)
    if not m:
        return v
    colour = m.group(2) or next((g.group(1) for g in (METAL.search(title), METAL.search(handle)) if g), "")
    # A bare karat is the product's base metal, which is yellow gold when the SKU carries the YG code
    # (Shopify tag "#14k yellow gold"). The SKU is only trusted for a bare karat: it is the base metal, not the variant's.
    if not colour and re.search(r"(?:^|-)[A-Z]*YG(?:-|$)", mpn.upper()):
        colour = "Yellow"
    return f"{m.group(1)}k Solid {colour.title()} Gold" if colour else v


def build(step):
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    CATALOG, OUTDIR = args
    skip = "--skip-unpriced" in sys.argv
    urls = json.load(open(os.path.join(HERE, "market_urls.json")))
    excl = [x.upper() for x in RULES["exclude_mpn_contains"]]

    csv.field_size_limit(10**8)
    all_rows = list(csv.DictReader(open(CATALOG, encoding="utf-8", newline="")))
    rows = [r for r in all_rows if not any(x in r["mpn"].upper() for x in excl)]
    step.info(f"{len(all_rows)} variants read, {len(all_rows) - len(rows)} excluded (MPN contains {', '.join(excl)})")
    names_seen = {}
    for r in rows:
        for k, _ in json.loads(r.get("options") or "[]"):
            names_seen[k] = names_seen.get(k, 0) + 1
    top = sorted(names_seen.items(), key=lambda kv: -kv[1])[:20]
    print("option names:", top)
    os.makedirs(OUTDIR, exist_ok=True)
    report = {"rules_version": RULES["version"], "variants": len(rows), "option_names": dict(top), "countries": {}, "samples": {}}
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
            mapped["material"] = clean_material(mapped["material"], r["title"], r["handle"], r["mpn"])
            mapped["color"] = metal_colour(mapped["material"])
            gcat = GOOGLE_CATEGORY.get(r["group_id"].split("_")[0], "")
            title = r["title"] if r["variant_title"] in ("", "Default Title") else f"{r['title']}, {r['variant_title']}"
            out.append({
                "id": f"shopify_{cc}_{r['product_id']}_{r['variant_id']}", "title": title[:150],
                "description": " ".join(r["description"].split())[:5000] or title,
                "link": f"{urls[cc]}/products/{r['handle']}?variant={r['variant_id']}", "image_link": r["image_link"],
                "additional_image_link": ",".join(r["additional_images"].split("|")[:10]) if r["additional_images"] else "",
                "availability": "in_stock" if r["available"] == "1" else "out_of_stock",
                "price": f"{Decimal(amount).quantize(Decimal('0.01'), ROUND_HALF_UP)} {code}", "brand": r["vendor"],
                "mpn": r["mpn"], "condition": "new", "item_group_id": r["group_id"],
                "product_type": PRODUCT_TYPE.get(r["group_id"].split("_")[0], ""), **mapped, "gender": GENDER if gcat else "", "age_group": AGE_GROUP if gcat else "", "google_product_category": gcat, NATIVE: "false"})
        if bad and not skip:
            sys.exit(f"{cc}: {len(bad)} variants have no price, e.g. {bad[:3]}; no files written")
        with open(os.path.join(OUTDIR, f"GOOGLE_PRIMARY_{cc}.tsv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
            w.writeheader(); w.writerows(out)
        # Per-field fill counts for the UI Mapping screen (a few example values come from the first country only).
        report["countries"][cc] = {"currency": cur, "items": len(out), "unpriced": len(bad),
                                   "filled": {fld: sum(1 for o in out if o[fld]) for fld in FIELDS}}
        if not report["samples"]:
            for fld in FIELDS:
                seen = []
                for o in out:
                    if o[fld] and o[fld] not in seen:
                        seen.append(o[fld])
                    if len(seen) == 3:
                        break
                report["samples"][fld] = [v[:120] for v in seen]
    no_cat = sum(1 for r in rows if r["group_id"].split("_")[0] not in GOOGLE_CATEGORY)
    print(f"{no_cat} variants without a Google category")
    print(f"{len(rows)} variants x {len(COUNTRIES)} countries written to {OUTDIR}")
    # Warnings come from one country (US when present): the gaps are the same in every country except price and link.
    ref = report["countries"].get("US") or next(iter(report["countries"].values()))
    for fld, fdef in ((f["google"], f) for f in RULES["fields"]):
        missing = ref["items"] - ref["filled"][fld]
        if missing and fdef["required"]:
            step.warn(f"{missing} items have no {fld} (required)", field=fld, missing=missing)
        elif missing and fld not in ("additional_image_link", "gender", "age_group"):
            step.warn(f"{missing} items have no {fld}", field=fld, missing=missing)
    if no_cat:
        step.warn(f"{no_cat} variants have no Google category", missing=no_cat)
    step.count(variants=len(rows), countries=len(COUNTRIES), excluded=len(all_rows) - len(rows))
    logdir = os.environ.get("RUN_LOG_DIR", "logs")
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, "mapping_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    shutil.copy(os.path.join(HERE, "mapping_rules.json"), os.path.join(logdir, "mapping_rules.json"))


with Step("build_primary_feed", shop=os.environ.get("SHOP", "jolie-je.myshopify.com")) as step:
    build(step)

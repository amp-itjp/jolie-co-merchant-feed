#!/usr/bin/env python3 -I
"""Export everything the primary feed needs from Shopify in one file (Admin GraphQL bulk operation).
One row per active variant that is published to the Online Store. Columns:
  variant_id, product_id, handle, title, variant_title, description, vendor, product_type, group_id, mpn, sku,
  available, image_link, additional_images, options (JSON [[name, value], ...]), price_<CC> (one per country, "amount CURRENCY") ...
Usage: SHOPIFY_ACCESS_TOKEN=... shopify_primary_export.py <shop.myshopify.com> <catalog.csv>
NOT YET RUN against the live store: needs one test run with the stored token."""
import csv, html, json, os, re, sys, time, urllib.request

SHOP, OUT = sys.argv[1], sys.argv[2]
TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
API = "2026-07"
COUNTRIES = "AU BH BE CA CZ DK FR DE GR IE IT KW LV MX NL NZ NO OM PL RO SA ES SE CH AE GB US".split()
if not TOKEN:
    sys.exit("SHOPIFY_ACCESS_TOKEN is not set")
aliases = "\n".join(f"    p_{c}: contextualPricing(context: {{country: {c}}}) {{ price {{ amount currencyCode }} }}" for c in COUNTRIES)
BULK = """
{ products(query: "status:active") { edges { node {
  id handle title descriptionHtml vendor productType onlineStoreUrl
  groupId: metafield(namespace: "google", key: "group_id") { value }
  mf_description: metafield(namespace: "google", key: "custom_product_description") { value }
  images(first: 6) { edges { node { url } } }
  variants { edges { node {
    id sku title availableForSale image { url }
    selectedOptions { name value }
    mpn: metafield(namespace: "mm-google-shopping", key: "mpn") { value }
    mf_title: metafield(namespace: "google", key: "custom_product_title") { value }
    mf_color: metafield(namespace: "mm-google-shopping", key: "color") { value }
    mf_material: metafield(namespace: "mm-google-shopping", key: "material") { value }
    mf_size: metafield(namespace: "mm-google-shopping", key: "size") { value }
    mf_gender: metafield(namespace: "mm-google-shopping", key: "gender") { value }
    mf_age_group: metafield(namespace: "mm-google-shopping", key: "age_group") { value }
    mf_custom_label_1: metafield(namespace: "mm-google-shopping", key: "custom_label_1") { value }
    mf_custom_label_2: metafield(namespace: "mm-google-shopping", key: "custom_label_2") { value }
%s
  } } }
} } } }""" % aliases


def gql(q):
    req = urllib.request.Request(f"https://{SHOP}/admin/api/{API}/graphql.json", data=json.dumps({"query": q}).encode(),
                                 headers={"Content-Type": "application/json", "X-Shopify-Access-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
    if out.get("errors"):
        sys.exit("GraphQL error: " + json.dumps(out["errors"])[:600])
    return out["data"]


cur = lambda: gql("{ currentBulkOperation(type: QUERY) { id status errorCode objectCount url } }")["currentBulkOperation"]
for _ in range(120):
    op = cur()
    if not op or op["status"] not in ("CREATED", "RUNNING"):
        break
    time.sleep(5)
st = gql('mutation { bulkOperationRunQuery(query: """%s""") { bulkOperation { id } userErrors { message } } }' % BULK)["bulkOperationRunQuery"]
if st["userErrors"]:
    sys.exit("bulk operation rejected: " + json.dumps(st["userErrors"]))
op_id = st["bulkOperation"]["id"]
for _ in range(360):
    time.sleep(5)
    op = cur()
    if op and op["id"] == op_id and op["status"] not in ("CREATED", "RUNNING"):
        break
else:
    sys.exit("bulk operation timed out")
if op["status"] != "COMPLETED" or not op.get("url"):
    sys.exit(f"bulk operation ended as {op['status']} ({op.get('errorCode')})")

num = lambda g: g.rsplit("/", 1)[1]
def val(m):
    v = ((m or {}).get("value") or "").strip()
    if v.startswith("["):  # list-type metafield: ["Gold", "White"] -> Gold/White
        try:
            return "/".join(str(x).strip() for x in json.loads(v) if str(x).strip())
        except ValueError:
            pass
    return v


MF = ["title", "color", "material", "size", "gender", "age_group", "custom_label_1", "custom_label_2"]
products, images, variants, child_opts = {}, {}, [], {}
with urllib.request.urlopen(op["url"], timeout=300) as r:
    for line in r:
        o = json.loads(line)
        if "__parentId" not in o:
            products[o["id"]] = o
        elif "sku" in o:
            variants.append(o)
        elif "url" in o:
            images.setdefault(o["__parentId"], []).append(o["url"])
        elif "name" in o and "value" in o:  # selectedOptions delivered as child lines of the variant
            child_opts.setdefault(o["__parentId"], []).append([o["name"], o["value"]])


def text(h):
    h = re.sub(r"<br\s*/?>|</p>|</li>", "\n", h or "")
    return re.sub(r"\n{3,}", "\n\n", html.unescape(re.sub(r"<[^>]+>", "", h))).strip()


rows = []
for v in variants:
    p = products.get(v["__parentId"])
    if p is None or not p.get("onlineStoreUrl"):
        continue
    imgs = images.get(p["id"], [])
    main = (v.get("image") or {}).get("url") or (imgs[0] if imgs else "")
    row = {"variant_id": num(v["id"]), "product_id": num(p["id"]), "handle": p["handle"], "title": p["title"],
           "variant_title": v["title"], "description": text(p["descriptionHtml"]), "vendor": p["vendor"],
           "product_type": p["productType"], "group_id": val(p.get("groupId")), "mpn": val(v.get("mpn")) or v["sku"],
           "sku": v["sku"], "available": "1" if v["availableForSale"] else "0", "image_link": main,
           "additional_images": "|".join(u for u in imgs if u != main)[:2000],
           "mf_description": val(p.get("mf_description")).replace("\r\n", "\n"),
           **{f"mf_{k}": val(v.get(f"mf_{k}")) for k in MF},
           "options": json.dumps([[o["name"], o["value"]] for o in v.get("selectedOptions") or []] or child_opts.get(v["id"], []), ensure_ascii=False)}
    for c in COUNTRIES:
        pr = (v.get(f"p_{c}") or {}).get("price")
        row[f"price_{c}"] = f"{pr['amount']} {pr['currencyCode']}" if pr else ""
    rows.append(row)
n_opts = sum(1 for r in rows if r["options"] != "[]")
print(f"{n_opts} of {len(rows)} variants have option names")
if n_opts < len(rows) * 0.9:
    sys.exit("option names missing on most variants; refusing to write " + OUT)
for k in ["description"] + MF:
    print(f"metafield {k}: {sum(1 for r in rows if r['mf_' + k])} of {len(rows)} variants filled")
if len(rows) < 10000:
    sys.exit(f"only {len(rows)} variants; refusing to write {OUT}")
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
print(f"wrote {len(rows)} variants to {OUT}")

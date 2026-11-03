#!/usr/bin/env python3 -I
"""Export the supplemental-feed fields straight from Shopify (Admin GraphQL bulk operation).

Replaces the Essential Product Feeds CSV as the input of build_variant_option_feed.py and writes the
same columns: id, item_group_id, item_group_title, title, description, variant_option, product_highlight.
  id                 shopify_CA_<product id>_<variant id>
  item_group_id      product   google.group_id
  item_group_title   product   google.group_title
  description        product   google.custom_product_description
  title              variant   google.custom_product_title
  variant_option     variant   google.variant_option
  product_highlight  variant   google-shopping.product_highlight (JSON list)

Usage: SHOPIFY_ACCESS_TOKEN=... shopify_export.py <shop.myshopify.com> <out.csv>
"""
import csv, json, os, sys, time, urllib.request

SHOP, OUT = sys.argv[1], sys.argv[2]
TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
API = "2026-07"
if not TOKEN:
    sys.exit("SHOPIFY_ACCESS_TOKEN is not set")

BULK_QUERY = """
{ products(query: "status:active") { edges { node {
  id
  groupId: metafield(namespace: "google", key: "group_id") { value }
  groupTitle: metafield(namespace: "google", key: "group_title") { value }
  desc: metafield(namespace: "google", key: "custom_product_description") { value }
  variants { edges { node {
    id
    title: metafield(namespace: "google", key: "custom_product_title") { value }
    vo: metafield(namespace: "google", key: "variant_option") { value }
    hl: metafield(namespace: "google-shopping", key: "product_highlight") { value }
  } } }
} } } }
"""


def gql(query):
    req = urllib.request.Request(
        f"https://{SHOP}/admin/api/{API}/graphql.json",
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
    if out.get("errors"):
        sys.exit("GraphQL error: " + json.dumps(out["errors"])[:500])
    return out["data"]


def current_op():
    return gql("{ currentBulkOperation(type: QUERY) { id status errorCode objectCount url } }")["currentBulkOperation"]


# Wait out any operation already running, then start ours.
for _ in range(120):
    op = current_op()
    if not op or op["status"] not in ("CREATED", "RUNNING"):
        break
    time.sleep(5)
start = gql('mutation { bulkOperationRunQuery(query: """%s""") { bulkOperation { id status } userErrors { field message } } }' % BULK_QUERY)
errs = start["bulkOperationRunQuery"]["userErrors"]
if errs:
    sys.exit("bulk operation rejected: " + json.dumps(errs))
op_id = start["bulkOperationRunQuery"]["bulkOperation"]["id"]

for _ in range(360):  # up to 30 minutes
    time.sleep(5)
    op = current_op()
    if op and op["id"] == op_id and op["status"] not in ("CREATED", "RUNNING"):
        break
else:
    sys.exit("bulk operation timed out")
if op["status"] != "COMPLETED" or not op.get("url"):
    sys.exit(f"bulk operation ended as {op['status']} ({op.get('errorCode')}), objects {op.get('objectCount')}")

products, variants = {}, []
with urllib.request.urlopen(op["url"], timeout=300) as r:
    for line in r:
        o = json.loads(line)
        if "__parentId" in o:
            variants.append(o)
        else:
            products[o["id"]] = o

val = lambda m: (m or {}).get("value") or ""
num = lambda gid: gid.rsplit("/", 1)[1]
rows = []
for v in variants:
    p = products.get(v["__parentId"])
    if p is None:
        continue
    rows.append({
        "id": f"shopify_CA_{num(p['id'])}_{num(v['id'])}",
        "item_group_id": val(p.get("groupId")),
        "variant_option": val(v.get("vo")),
        "title": val(v.get("title")),
        "description": val(p.get("desc")).replace("\r\n", "\n"),
        "item_group_title": val(p.get("groupTitle")),
        "product_highlight": val(v.get("hl")),
    })

if len(rows) < 10000:
    sys.exit(f"only {len(rows)} variants exported; refusing to write {OUT}")
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"products {len(products)}, variants {len(rows)}, wrote {OUT}")

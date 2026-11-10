#!/usr/bin/env python3 -I
"""One-off read-only export of review metafields, group id and MPN per variant (Admin GraphQL bulk op).
Usage: SHOPIFY_ACCESS_TOKEN=... review_export.py <shop.myshopify.com> <out.csv>"""
import csv, json, os, sys, time, urllib.request

SHOP, OUT = sys.argv[1], sys.argv[2]
TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
API = "2026-07"
if not TOKEN:
    sys.exit("SHOPIFY_ACCESS_TOKEN is not set")

BULK_QUERY = """
{ products(query: "status:active") { edges { node {
  id handle title
  groupId: metafield(namespace: "google", key: "group_id") { value }
  rating: metafield(namespace: "reviews", key: "rating") { value }
  ratingCount: metafield(namespace: "reviews", key: "rating_count") { value }
  jm: metafields(first: 20, namespace: "judgeme") { edges { node { key value } } }
  pMpn: metafield(namespace: "mm-google-shopping", key: "mpn") { value }
  variants { edges { node {
    id sku
    vMpn: metafield(namespace: "mm-google-shopping", key: "mpn") { value }
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
for _ in range(360):
    time.sleep(5)
    op = current_op()
    if op and op["id"] == op_id and op["status"] not in ("CREATED", "RUNNING"):
        break
else:
    sys.exit("bulk operation timed out")
if op["status"] != "COMPLETED" or not op.get("url"):
    sys.exit(f"bulk operation ended as {op['status']} ({op.get('errorCode')})")

products, variants, jm = {}, [], {}
with urllib.request.urlopen(op["url"], timeout=300) as r:
    for line in r:
        o = json.loads(line)
        if "key" in o and "__parentId" in o:
            jm.setdefault(o["__parentId"], {})[o["key"]] = o["value"]
        elif "__parentId" in o:
            variants.append(o)
        else:
            products[o["id"]] = o

val = lambda m: (m or {}).get("value") or ""
rows = []
for v in variants:
    p = products.get(v["__parentId"])
    if p is None:
        continue
    rows.append({
        "product_id": p["id"].rsplit("/", 1)[1], "handle": p["handle"], "title": p["title"],
        "group_id": val(p.get("groupId")), "reviews_rating": val(p.get("rating")),
        "reviews_rating_count": val(p.get("ratingCount")),
        "judgeme_metafields": json.dumps(jm.get(p["id"], {})),
        "product_mpn": val(p.get("pMpn")), "variant_id": v["id"].rsplit("/", 1)[1],
        "sku": v.get("sku") or "", "variant_mpn": val(v.get("vMpn")),
    })
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"products {len(products)}, variants {len(rows)}")

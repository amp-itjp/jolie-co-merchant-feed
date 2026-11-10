#!/usr/bin/env python3 -I
"""Export each variant's price per country as Shopify Markets sets it (Admin GraphQL contextualPricing, bulk).
Writes id, country, amount, currency (id = shopify_CA_<product>_<variant>), the input of build_country_feed.py.
Usage: SHOPIFY_ACCESS_TOKEN=... shopify_prices_export.py <shop.myshopify.com> <out.csv>
NOT YET RUN: needs one test run with the stored token before it is relied on."""
import csv, json, os, re, sys, time, urllib.request

SHOP, OUT = sys.argv[1], sys.argv[2]
TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
API = "2026-07"
COUNTRIES = "AU BH BE CA CZ DK FR DE GR IE IT KW LV MX NL NZ NO OM PL RO SA ES SE CH AE GB US".split()
if not TOKEN:
    sys.exit("SHOPIFY_ACCESS_TOKEN is not set")
aliases = "\n".join(f"    p_{c}: contextualPricing(context: {{country: {c}}}) {{ price {{ amount currencyCode }} }}" for c in COUNTRIES)
BULK = '{ products(query: "status:active") { edges { node { id variants { edges { node {\n    id\n%s\n} } } } } } }' % aliases


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
rows = []
with urllib.request.urlopen(op["url"], timeout=300) as r:
    for line in r:
        o = json.loads(line)
        if "__parentId" not in o:
            continue
        pid = num(o["__parentId"])
        for c in COUNTRIES:
            p = (o.get(f"p_{c}") or {}).get("price")
            if p:
                rows.append([f"shopify_CA_{pid}_{num(o['id'])}", c, p["amount"], p["currencyCode"]])
if len(rows) < 10000 * len(COUNTRIES) * 0.9:
    sys.exit(f"only {len(rows)} price rows; refusing to write {OUT}")
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f); w.writerow(["id", "country", "amount", "currency"]); w.writerows(rows)
print(f"wrote {len(rows)} price rows to {OUT}")

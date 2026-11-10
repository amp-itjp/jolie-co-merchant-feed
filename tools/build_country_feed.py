#!/usr/bin/env python3 -I
"""Build one supplemental file per country, each row priced with the store's own price for that country.

Input
  supplemental.csv   the CA supplemental file (build_variant_option_feed.py output); IDs shopify_CA_<product>_<variant>
  prices.csv         columns id, country, amount, currency -- the price Shopify Markets charges in each country
                     (tools/shopify_prices_export.py writes it). id is the shopify_CA_ ID of the variant.
Output
  <outdir>/GOOGLE_SUPPLEMENTAL_<CC>.csv  for every country in COUNTRIES
    id      shopify_<CC>_<product>_<variant>   (confirm the real ID pattern in Merchant Center first)
    price   "<amount> <CURRENCY>"  exactly as Shopify prices it for that country, no conversion
    ...all other supplemental columns unchanged

The run stops, and writes nothing, if a country's file would lack a price for any variant, or if Shopify
reports a currency other than the one expected for that country.
Merchant Center only applies a row to an item that already exists with that ID.

Usage: build_country_feed.py supplemental.csv prices.csv outdir [--skip-unpriced]
"""
import csv, os, sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

ID_FORMAT = "shopify_{cc}_{rest}"            # rest = "<product>_<variant>"
COUNTRIES = {  # the 27 countries the Google channel sends to, and the currency each is priced in
    "AU": "AUD", "BH": "CAD", "BE": "EUR", "CA": "CAD", "CZ": "CZK", "DK": "EUR", "FR": "EUR", "DE": "EUR",
    "GR": "EUR", "IE": "EUR", "IT": "EUR", "KW": "CAD", "LV": "EUR", "MX": "MXN", "NL": "EUR", "NZ": "NZD",
    "NO": "NOK", "OM": "CAD", "PL": "PLN", "RO": "EUR", "SA": "SAR", "ES": "EUR", "SE": "SEK", "CH": "CHF",
    "AE": "AED", "GB": "GBP", "US": "USD",
}
args = [a for a in sys.argv[1:] if not a.startswith("--")]
SUP, PRICES, OUTDIR = args
skip = "--skip-unpriced" in sys.argv

csv.field_size_limit(10**8)
price = defaultdict(dict)  # id -> country -> "amount CUR"
for r in csv.DictReader(open(PRICES, encoding="utf-8", newline="")):
    cc, cur = r["country"], r["currency"]
    if cc not in COUNTRIES:
        continue
    if cur != COUNTRIES[cc]:
        sys.exit(f"{cc}: Shopify prices in {cur} but {COUNTRIES[cc]} is expected; no files written")
    price[r["id"]][cc] = f"{Decimal(r['amount']).quantize(Decimal('0.01'), ROUND_HALF_UP)} {cur}"

with open(SUP, encoding="utf-8", newline="") as f:
    rd = csv.reader(f)
    header = next(rd)
    rows = list(rd)
if header[0] != "id" or not all(r[0].startswith("shopify_CA_") for r in rows):
    sys.exit("supplemental file must have IDs shopify_CA_...")
missing = [r[0] for r in rows if set(price[r[0]]) != set(COUNTRIES)]
if missing and not skip:
    sys.exit(f"{len(missing)} variants lack a price for some country, e.g. {missing[:3]}; no files written")
if missing:
    miss = set(missing)
    rows = [r for r in rows if r[0] not in miss]
    print(f"skipping {len(miss)} variants without a full set of prices")

os.makedirs(OUTDIR, exist_ok=True)
for cc in COUNTRIES:
    with open(os.path.join(OUTDIR, f"GOOGLE_SUPPLEMENTAL_{cc}.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header + ["price"])
        for r in rows:
            w.writerow([ID_FORMAT.format(cc=cc, rest=r[0][len("shopify_CA_"):])] + r[1:] + [price[r[0]][cc]])
print(f"{len(rows)} rows x {len(COUNTRIES)} countries written to {OUTDIR}")

# Jolie Co Merchant Center supplemental file

Builds `GOOGLE_SUPPLEMENTAL_ALL.csv` for Google Merchant Center straight from Shopify (Admin API bulk export),
splitting `variant_option` into one name:value pair per column (every column named `variant_option`).

- Runs daily at 03:00 UTC and on demand (Actions > Refresh supplemental feed > Run workflow).
- Publishes to GitHub Pages: https://amp-itjp.github.io/jolie-co-merchant-feed/GOOGLE_SUPPLEMENTAL_ALL.csv
- If the source download fails or returns too few rows, the run fails and the previous file stays live.
- The file holds product titles, descriptions, variant IDs and option values already public on the store.

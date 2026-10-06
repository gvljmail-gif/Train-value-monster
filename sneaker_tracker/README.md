# Sneaker tracker (pilot)

Scripts do the fetching and parsing (zero model tokens); the scheduled Claude run only reads
`data/latest.json`, applies judgement (RRP, suspect listings) and publishes the artifact.

Run (from repo root): `/usr/bin/python3.13 -m sneaker_tracker.run`
Needs `pip install playwright`; uses the preinstalled Chromium in `/opt/pw-browsers`.

## Status
| Source | Status |
|---|---|
| size? | Working. Real per-size stock (`data-stock`), images, prices |
| Footpatrol | Working via Shopify JSON (`/collections/sale/products.json`): real per-size stock, images, compare-at prices |
| Nike UK | Working (search pages, first 24 results each). Sizes only *listed*, not stock-verified. Nike's UK sale is capped ~30% so rarely clears 35% |
| END. | Working (`/gb/sale/nike`, pages 1-2). Sizes only *listed*, not stock-verified. END.'s "full price" can exceed Nike RRP: cross-check |
| Foot Locker UK | Working (search pages). Sizes only *listed*, not stock-verified |
| JD Sports | Next.js site, different parser needed (not built) |
| Schuh | Cloudflare challenge |
| eBay UK | Blocked for scraping; Browse API pending developer key (`EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET`) |
| Onitsuka Tiger UK, ASOS, Very, Vinted, StockX, GOAT | Not built yet |
| Killshot / Dunk coverage | Nike/Foot Locker searches only; size? has no collection pages for these |

`stock_verified: true` = real stock field (size?, Footpatrol). `false` = sizes merely listed -> report as "check stock".

## Rules
- Retail deal = >=35% below RRP AND UK 8.5 or 9 confirmed in stock. Daily ping while it stays live.
- Resale only for styles out of production (e.g. Air Jordan 2): list every 8.5/9 listing, no 35% rule.
- Every run writes a coverage table (source, URL, HTTP status, items, result).

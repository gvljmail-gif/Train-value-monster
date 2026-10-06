# Sneaker tracker (pilot)

Scripts do the fetching and parsing (zero model tokens); the scheduled Claude run only reads
`data/latest.json`, applies judgement (RRP, suspect listings) and publishes the artifact.

Run (from repo root): `/usr/bin/python3.13 -m sneaker_tracker.run`
Needs `pip install playwright`; uses the preinstalled Chromium in `/opt/pw-browsers`.

## Status
| Source | Status |
|---|---|
| size? (JD Group platform) | Working: listing prices, images, and per-size stock via `data-stock` on product pages |
| JD Sports, Footpatrol | Same platform; next to add (list URLs needed) |
| Foot Locker, Nike UK, END. | Reachable with headless Chromium; parsers to write |
| Schuh | Cloudflare challenge; needs another approach |
| eBay UK | Blocked for scraping; use Browse API (env `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET`) |
| Vinted, StockX, GOAT | Not yet tested |
| size? Air Max 97 / Dunk / Killshot | No collection pages; use site search |

## Rules
- Retail deal = >=35% below RRP AND UK 8.5 or 9 confirmed in stock. Daily ping while it stays live.
- Resale only for styles out of production (e.g. Air Jordan 2): list every 8.5/9 listing, no 35% rule.
- Every run writes a coverage table (source, URL, HTTP status, items, result).

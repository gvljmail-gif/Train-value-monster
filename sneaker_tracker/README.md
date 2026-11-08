# Sneaker tracker

Scripts do the fetching and parsing (zero model tokens); the scheduled Claude run only runs them, uploads
images, publishes the artifact and decides whether to notify (from `out/summary.json`).

Run (from repo root): `python3.13 -m sneaker_tracker.run` (about 4-5 minutes), then
`python3.13 -m sneaker_tracker.report prepare` and `... report build`. Offline checks: `python3.13 -m sneaker_tracker.selftest`.
Needs `pip install playwright beautifulsoup4 lxml`; uses the preinstalled Chromium in `/opt/pw-browsers`.

## Layout
| File | Role |
|---|---|
| `config.json` | Sources (label, stock basis, pages, fetch policy), sizes, threshold, reference RRPs, alert settings |
| `rules.py` | The deal rules (effective discount, live vs check lanes, grouping), shared by run and report |
| `health.py` | Page/source health from today's coverage plus the dated snapshots; decides `degraded` |
| `run.py` | Scrapes every source with retries + circuit breaker, stock-checks deal candidates, writes `data/<date>.json` |
| `report.py` | Images (`prepare`) and the page + `summary.json` (`build`) |
| `scrapers/` | One module per site; `shopify.py` serves size?, Footpatrol and END. |

## Sources (Nov 2026)
| Source | How | Stock |
|---|---|---|
| size? | Shopify JSON: `footwear-mens-sale`, `collection-jordan-2` | verified (variant `available`) |
| Footpatrol | Shopify JSON: `footwear-mens-sale` | verified |
| END. | Shopify JSON: `nike`, `air-jordan` (all prices, filtered to men's footwear) | verified |
| JD Sports | Algolia search XHR captured from the site, every page (`?from=72`, ...), men's footwear only | verified (in-stock size list) |
| ASOS | Search pages; candidates checked on the product page (`isInStock` per variant) | verified (product page) |
| Foot Locker UK | Search pages read from the embedded server state (`STATE_FROM_SERVER.search`), with Hybris facets (`:relevance:gender:Men:productTypes:Shoes:saleProduct:True`); candidates checked on the product page ("Sold Out" size buttons) | verified (product page) |
| Nike UK | Search pages; candidates checked on the product page (schema.org InStock offers) | verified (product page) |
| Onitsuka Tiger UK | Magento listing/search pages | prices only |
| Vinted | Catalog search (resale, Air Jordan 2 only) | resale |
| GOAT | Search XHR (resale reference, USD lowest ask) | resale ref |
| Schuh, StockX | Bot protection (Cloudflare / PerimeterX); not fetched, listed as expected-blocked | - |
| eBay UK | Browse API pending developer key (`EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET`) | - |

What changed on 24 Oct and why: size? (21 Oct) and END. (10-21 Oct) moved to Shopify, which broke their HTML
parsers; Footpatrol started returning 403 to Playwright's non-browser `ctx.request` (8 Oct). JSON endpoints are now
loaded as browser pages (`common.fetch_json`).

8 Nov: Foot Locker's search grid often fails to render client-side (empty grid or an "All Products" page) although
the page's server state holds every result, so the scraper reads the state instead of the DOM. The server ignores
`currentPage`; queries with more than 48 results are re-fetched sorted price-asc and price-desc. Scrapers can now
return a third value, `meta`: `unreadable` (page loaded, nothing parseable) and `short` (results cut off, e.g. a
later Shopify page 403'd) both show in the coverage table instead of passing as ok.

Also 8 Nov: Very dropped (Akamai blocked it after one or two searches every day, and it showed prices only). JD now
reads every results page (it had read only the first 72) and skips clothing. Deals are grouped across retailers by
Nike style code from each source's own data (JD `anatwineProductRef`, Foot Locker product page "Supplier-sku",
Shopify handle/description); ASOS pages carry no trustworthy code, so ASOS items stand alone. The Jordan line is
numbered Air Jordans only (signature/lifestyle models such as Luka, Tatum, Zion, Spizike are left out).

## Rules
- Retail deal = at least 35% below typical RRP (`rules.py`) AND UK 8.5 or 9 confirmed in stock -> Live lane.
  Typical RRP: the retailer's was-price, capped at `rrp_tolerance` x the model's `ref_rrp` (regex patterns, most
  specific first; added 8 Nov from Nike UK's own full prices in the snapshots, or the size?/Footpatrol/END. price
  where Nike UK doesn't list the model). Foot Locker's 30-day lowest price was checked as a cross-check and
  dropped: it is either absent or equal to the was-price.
  A deal whose stock could not be confirmed -> Check stock lane. Confirmed sold out in both sizes -> dropped.
- Resale only for styles out of production (Air Jordan 2): list every 8.5/9 listing, no 35% rule.
- NEW = not live (or, for Air Jordan 2, not listed) in any of the last `new_window_days` snapshots.
- Ping: `ping_on_live` and `ping_on_aj2`, both `"new"`: only when a deal / Air Jordan 2 listing appears that wasn't
  seen in the window (`"any"` pings every day one is live; live deals existed on every day of the 14 to 8 Nov).

## Health
Every run writes a coverage table (source, URL, HTTP status, items, state). `health.py` labels each page ok,
quiet (normally empty), missed (empty once), blocked (403/429/timeout) or changed (404, or empty two runs in a row
where it normally has items: the site changed and the scraper needs fixing). A problem = a stock-verified source
down, a page changed, a product-page stock check failing on every item, or fewer than `min_sources_ok` sources up.
Problems always show on the page; `degraded` (the health push) is set only for a problem not alerted in the last
`alert_repeat_days` (7): once when it starts, then weekly while it lasts. Each snapshot records the problem keys it
alerted in `alerts`. If a source becomes permanently unreachable, set `"expected_blocked": true` (and `"type": "blocked"`)
on it in `config.json` so it stops raising alerts.

Fetching: each page is retried with backoff (`backoff`, default 6 s then 20 s) when blocked, or when empty but
normally full; after `breaker` consecutive blocked pages (default 3) a source is left alone for the rest of the run.
No bot-protection workarounds are used: blocked sites are reported, not evaded.

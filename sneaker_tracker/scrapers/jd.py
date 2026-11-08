"""JD Sports UK: Algolia search JSON captured from the site's own XHR. Includes in-stock size list.

The search page asks Algolia for 72 hits at a time; 'Load more' is a plain `?from=72` page load, which asks
for the next page. Until Nov 2026 only the first 72 were read (86 for 'air max 95', 156 for 'air jordan'),
so later results are now fetched the same way, up to MAX_PAGES. Hits are men's adult footwear only; JD's
`anatwineProductRef` carries the Nike style code, used to group the same shoe across retailers.
A query may end in a site path: 'air max 97/sale' -> /search/air+max+97/sale/ (JD's sale filter: 170 results
instead of 762 for that search). Deals need a was-price, which only sale items have.
"""
import json
from .common import capture_json, classify, pct, style_code

BASE = "https://www.jdsports.co.uk"
MAX_PAGES = 6


def _is_search(url):
    return "algolia" in url and "/run" in url


def hits_of(bodies):
    """({objectID: hit}, nbHits the site reported or None, hits per page) from captured Algolia bodies."""
    hits, total, per = {}, None, 72
    for b in bodies:
        try:
            results = json.loads(b).get("results", [])
        except ValueError:
            continue
        for res in results:
            if isinstance(res.get("nbHits"), int):
                total = max(total or 0, res["nbHits"])
            per = res.get("hitsPerPage") or per
            hits.update({h["objectID"]: h for h in res.get("hits", []) if h.get("objectID")})
    return hits, total, per


def parse_hits(hits):
    items = []
    for h in hits:
        name = h.get("name", "")
        if "Mens" not in (h.get("gender") or []) or "Adult" not in (h.get("ageGroup") or ["Adult"]):
            continue
        if h.get("category") and "Footwear" not in h["category"]:
            continue  # JD search also returns clothing and socks
        line = classify(name)
        if not line or h.get("price") is None:
            continue
        price, rrp = float(h["price"]), float(h.get("wasPrice") or h["price"])
        items.append({"name": name + (f" ({h['colour']})" if h.get("colour") else ""),
                      "url": f"{BASE}/product/{h['slug']}/{h['objectID']}/", "line": line,
                      "image": h.get("image"), "rrp": rrp, "price": price,
                      "discount_pct": pct(rrp, price), "style": style_code(h.get("anatwineProductRef")),
                      "all_sizes": {str(s): True for s in h.get("size", [])}, "stock_verified": True})
    return items


async def scrape_search(ctx, query):
    url = f"{BASE}/search/{query.replace(' ', '+')}/"
    status, bodies = await capture_json(ctx, url, _is_search)
    hits, total, per = hits_of(bodies)
    if status == 200 and total is None:
        return status, [], {"unreadable": True}  # page loaded but its search request never answered
    for page in range(1, min(MAX_PAGES, -(-(total or 0) // per))):
        _, more = await capture_json(ctx, f"{url}?from={page * per}", _is_search)
        hits.update(hits_of(more)[0])
    meta = {"short": f"{len(hits)} of {total} results"} if total and len(hits) < total else {}
    return status, parse_hits(hits.values()), meta

"""JD Sports UK: Algolia search JSON captured from the site's own XHR. Includes in-stock size list."""
import json
from .common import capture_json, classify, pct

BASE = "https://www.jdsports.co.uk"


async def scrape_search(ctx, query):
    url = f"{BASE}/search/{query.replace(' ', '+')}/"
    status, bodies = await capture_json(ctx, url, lambda u: "algolia" in u and "/run" in u)
    items = []
    for b in bodies[:1]:
        for res in json.loads(b).get("results", []):
            for h in res.get("hits", []):
                name = h.get("name", "")
                if "Mens" not in (h.get("gender") or []) or "Adult" not in (h.get("ageGroup") or ["Adult"]):
                    continue
                line = classify(name)
                if not line:
                    continue
                price, rrp = float(h["price"]), float(h.get("wasPrice") or h["price"])
                items.append({"name": name + (f" ({h['colour']})" if h.get("colour") else ""),
                              "url": f"{BASE}/product/{h['slug']}/{h['objectID']}/", "line": line,
                              "image": h.get("image"), "rrp": rrp, "price": price,
                              "discount_pct": pct(rrp, price),
                              "all_sizes": {str(s): True for s in h.get("size", [])}, "stock_verified": True})
    return status, items

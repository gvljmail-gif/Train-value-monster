"""GOAT search JSON (resale reference). Prices are USD lowest-ask across sizes; no per-size UK data
in the search response, so this is a market-price reference, not a size-confirmed listing."""
import json
from .common import capture_json, classify

BASE = "https://www.goat.com"


async def scrape_search(ctx, query):
    url = f"{BASE}/search?query={query.replace(' ', '%20')}"
    status, bodies = await capture_json(ctx, url, lambda u: "get-product-search-results" in u)
    items = []
    for b in bodies[:1]:
        for p in json.loads(b).get("data", {}).get("productsList", []):
            name = p.get("title", "")
            line = classify(name)
            if not line:
                continue
            asks = [v["localizedLowestPriceCents"]["amountCents"] for v in p.get("variantsList", [])
                    if v.get("localizedLowestPriceCents")]
            items.append({"name": name, "url": f"{BASE}/sneakers/{p['slug']}", "line": line,
                          "image": p.get("pictureUrl"), "price_usd": (min(asks) / 100 if asks else None),
                          "retail_usd": (p.get("localizedRetailPriceCents") or {}).get("amountCents", 0) / 100 or None,
                          "in_stock": p.get("inStock"), "resale": True, "condition": "New (GOAT-verified)"})
    return status, items

"""Footpatrol (Shopify): structured JSON incl. per-size availability. No HTML parsing needed."""
import json
from .common import classify, pct, num

BASE = "https://www.footpatrol.com"
VENDORS = {"nike", "jordan", "onitsuka tiger", "asics"}


async def scrape_collection(ctx, handle, max_pages=8):
    """Return (status, items) for /collections/<handle>; items carry full per-size stock."""
    items, status = [], None
    for page in range(1, max_pages + 1):
        r = await ctx.request.get(f"{BASE}/collections/{handle}/products.json?limit=250&page={page}", timeout=30000)
        status = r.status
        if r.status != 200:
            break
        prods = json.loads(await r.text()).get("products", [])
        if not prods:
            break
        for p in prods:
            if p.get("vendor", "").lower() not in VENDORS:
                continue
            name = f"{p['vendor']} {p['title']}" if p["vendor"].lower() not in p["title"].lower() else p["title"]
            line = classify(name)
            if not line:
                continue
            vs = p["variants"]
            price = min(num(v["price"]) for v in vs)
            rrp = max([num(v.get("compare_at_price")) or 0 for v in vs] + [price])
            sizes = {v["option1"]: bool(v["available"]) for v in vs}
            items.append({"name": name, "url": f"{BASE}/products/{p['handle']}", "line": line,
                          "image": (p["images"][0]["src"] if p.get("images") else None),
                          "rrp": rrp, "price": price, "discount_pct": pct(rrp, price),
                          "all_sizes": sizes, "stock_verified": True})
    return status, items

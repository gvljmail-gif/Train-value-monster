"""Shopify storefronts (size?, Footpatrol, END.): /collections/<handle>/products.json carries every
variant's price, compare-at price and real `available` flag, so stock is verified with no HTML parsing.

size? (21 Oct) and END. (rolled out 10-21 Oct) moved onto Shopify; Footpatrol already was. All three are
fetched as browser pages (common.fetch_json) because non-browser requests get 403.
"""
from .common import adult_mens, classify, fetch_json, norm_uk, num, pct

VENDORS = {"nike", "jordan", "air jordan", "onitsuka tiger", "asics"}
PAGE_SIZE = 250


def _mens_footwear(p):
    """size?/Footpatrol: product_type 'size > Men's > Footwear'. END.: tags 'cat_high:Footwear', 'gender:Mens'.
    Items with neither marker fall through to the name-based checks."""
    ptype, tags = (p.get("product_type") or "").lower(), [t.lower() for t in p.get("tags") or []]
    if any(w in ptype for w in ("women", "kids", "junior", "infant", "child")):
        return False
    if any(t.startswith("gender:") for t in tags) and not ({"gender:mens", "gender:unisex"} & set(tags)):
        return False
    if any(t.startswith("cat_high:") for t in tags) and "cat_high:footwear" not in tags:
        return False
    return adult_mens(p.get("title"))


def parse_products(products, link_base, sizes):
    """Map Shopify product dicts to tracker items. Price/RRP come from the target-size variants when the
    product has them (sale prices can differ by size), otherwise from all variants."""
    out = []
    for p in products:
        vendor = (p.get("vendor") or "").strip()
        if vendor.lower() not in VENDORS or not _mens_footwear(p):
            continue
        name = p["title"] if vendor.lower() in p["title"].lower() else f"{vendor} {p['title']}"
        line = classify(name)
        if not line:
            continue
        variants = [v for v in p.get("variants", []) if num(v.get("price")) is not None]
        if not variants:
            continue
        by_size = {}
        for v in variants:
            uk = norm_uk(v.get("option1") or v.get("title"))
            if uk:
                by_size[uk] = by_size.get(uk, False) or bool(v.get("available"))
        target = [v for v in variants if norm_uk(v.get("option1") or v.get("title")) in sizes] or variants
        price = min(num(v["price"]) for v in target)
        rrp = max([num(v.get("compare_at_price")) or 0 for v in target] + [price])
        img = (p.get("images") or [{}])[0].get("src")
        out.append({"name": name, "url": f"{link_base}/products/{p['handle']}", "line": line,
                    "image": ("https:" + img if img and img.startswith("//") else img),
                    "rrp": rrp, "price": price, "discount_pct": pct(rrp, price),
                    "all_sizes": by_size, "stock_verified": bool(by_size)})
    return out


async def scrape_collection(ctx, base, handle, link_base, sizes, max_pages=8):
    """Return (status, items) for one collection, following pagination until a short page."""
    items, status = [], None
    for page in range(1, max_pages + 1):
        s, data = await fetch_json(ctx, f"{base}/collections/{handle}/products.json?limit={PAGE_SIZE}&page={page}")
        status = s if page == 1 or s != 200 else status
        if s != 200 or not isinstance(data, dict):
            break
        prods = data.get("products", [])
        items += parse_products(prods, link_base, sizes)
        if len(prods) < PAGE_SIZE:
            break
    return status, items

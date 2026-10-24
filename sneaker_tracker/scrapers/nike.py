"""Nike UK search pages (rendered DOM). Prices from cards; deal candidates are stock-checked from the
product page's per-size schema.org offers (InStock / OutOfStock)."""
import json
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, norm_uk, num, pct


def parse_list(html):
    soup, out = BeautifulSoup(html, "lxml"), []
    for c in soup.select('[data-testid="product-card"]'):
        a = c.select_one("a.product-card__link-overlay")
        title = c.select_one(".product-card__title")
        sub = c.select_one(".product-card__subtitle")
        if not (a and title):
            continue
        name = title.get_text(strip=True) + (" " + sub.get_text(strip=True) if sub else "")
        cur, old = c.select_one('[data-testid="product-price-reduced"]'), c.select_one('[data-testid="product-price"]')
        price = num((cur or old).get_text()) if (cur or old) else None
        rrp = num(old.get_text()) if old and cur else price
        img = c.select_one("img")
        out.append({"name": name, "url": a["href"], "line": classify(name),
                    "image": img.get("src") if img else None,
                    "rrp": rrp, "price": price, "discount_pct": pct(rrp, price), "stock_verified": False})
    return [o for o in out if o["line"]]


async def scrape_list(ctx, url):
    s, h = await fetch_html(ctx, url, 5000)
    return s, (parse_list(h) if h else [])


LABEL = re.compile(r'"label":"([^"]+)","localizedLabel":"([^"]+)","localizedLabelPrefix":"UK"')


def parse_sizes(html):
    """{uk_size: in_stock} from the product page's schema.org offers (one Product per size, keyed by the US
    label, availability InStock/OutOfStock), mapped to UK via the size grid's label/localizedLabel pairs.
    Sold-out sizes are usually omitted from the offers, so grid sizes without an InStock offer count as sold out
    (checked against Nike's own available_gtins API on 24 Oct)."""
    us_to_uk = {us: norm_uk("UK " + uk) for us, uk in LABEL.findall(html)}
    sizes = {}
    for block in BeautifulSoup(html, "lxml").select('script[type="application/ld+json"]'):
        try:
            data = json.loads(block.string or "")
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack += d
            elif isinstance(d, dict):
                offers = d.get("offers")
                if d.get("size") is not None and isinstance(offers, dict) and "availability" in offers:
                    uk = us_to_uk.get(str(d["size"]))
                    if uk:
                        sizes[uk] = sizes.get(uk, False) or offers["availability"].endswith("InStock")
                stack += [v for v in d.values() if isinstance(v, (list, dict))]
    if sizes:  # only when offers were found; otherwise stock is unknown, not sold out
        sizes = {**{uk: False for uk in us_to_uk.values() if uk}, **sizes}
    return sizes


async def check_sizes(ctx, url):
    s, h = await fetch_html(ctx, url, 3000)
    sizes = parse_sizes(h) if h else {}
    return {"http": s, "sizes": sizes, "verified": bool(sizes)}

"""Very UK search pages. Cards show current price only (no was-price), so discount_pct stays 0
unless a reference RRP is applied later. Sizes not fetched."""
from bs4 import BeautifulSoup
from .common import classify, fetch_html, num

BASE = "https://www.very.co.uk"


def parse_list(html):
    out = []
    for c in BeautifulSoup(html, "lxml").select('[data-testid="gallery-product-card"]'):
        a = c.select_one('a[data-testid="fuse-product-card__link"]')
        brand = c.select_one('[data-testid="fuse-product-card__brand"]')
        title = c.select_one('[data-testid="fuse-product-card__title"]')
        price = c.select_one('[data-testid="fuse-product-card__price__basic"]')
        if not (a and title and price):
            continue
        name = ((brand.get_text(strip=True) + " ") if brand else "") + title.get_text(strip=True)
        p = num(price.get_text())
        out.append({"name": name, "url": BASE + a["href"], "line": classify(name), "image": None,
                    "rrp": p, "price": p, "discount_pct": 0, "stock_verified": False})
    return [o for o in out if o["line"]]


async def scrape_search(ctx, query):
    s, h = await fetch_html(ctx, f"{BASE}/e/q/{query.replace(' ', '-')}.end", 4000)
    return s, (parse_list(h) if h else [])

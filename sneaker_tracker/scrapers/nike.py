"""Nike UK search/sale pages (rendered DOM). Prices from cards; sizes are listed, not stock-verified."""
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, num, pct


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


async def check_sizes(ctx, url):
    s, h = await fetch_html(ctx, url, 3000)
    soup = BeautifulSoup(h, "lxml") if h else None
    sizes = {}
    if soup:
        for l in soup.select('[data-testid="size-selector"] label'):
            m = re.match(r"UK\s*([\d.]+)", l.get_text(strip=True))
            if m:
                sizes[m.group(1)] = True  # listed; Nike markup shows no sold-out marker in static DOM
    return s, sizes

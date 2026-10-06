"""END. Clothing UK listing pages. Prices from cards; sizes are listed, not stock-verified."""
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, num, pct

BASE = "https://www.endclothing.com"


def parse_list(html):
    soup, out = BeautifulSoup(html, "lxml"), []
    for a in soup.select('a[data-test-id="ProductCard__ProductCardSC"]'):
        img = a.select_one('img[data-test-id="ProductCard__PlpImage"]')
        name = (img.get("alt", "") if img else "").replace(" - product", "")
        # price spans live in the sibling card block just before the link
        block = a.find_previous(attrs={"data-test-id": "ProductCard__ProductFinalPrice"})
        full = a.find_previous(attrs={"data-test-id": "ProductCard__ProductFullPrice"})
        href = a.get("href", "").split("?")[0]
        if not (name and href):
            continue
        price = num(block.get_text()) if block else None
        rrp = num(full.get_text()) if full else price
        out.append({"name": name, "url": BASE + href, "line": classify(name),
                    "image": img.get("src") if img else None,
                    "rrp": rrp, "price": price, "discount_pct": pct(rrp, price), "stock_verified": False})
    return [o for o in out if o["line"]]


async def scrape_list(ctx, url):
    s, h = await fetch_html(ctx, url, 5000)
    return s, (parse_list(h) if h else [])


async def check_sizes(ctx, url):
    s, h = await fetch_html(ctx, url, 3000)
    sizes = {}
    if h:
        for b in BeautifulSoup(h, "lxml").select('[data-test-id="Size__Button"]'):
            m = re.match(r"UK\s*([\d.]+)", b.get_text(strip=True))
            if m:
                sizes[m.group(1)] = True
    return s, sizes

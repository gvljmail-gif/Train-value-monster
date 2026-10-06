"""Onitsuka Tiger UK official store (Magento). Listing cards: name + price (+ old price if on sale)."""
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, num, pct

TARGETS = re.compile(r"mexico\s*66|moage|tokuten|edr\s*78|colorado", re.I)


def parse_list(html):
    out, seen = [], set()
    for c in BeautifulSoup(html, "lxml").select(".product-item-info"):
        a = c.select_one("a.product-item-link")
        price = c.select_one(".price-final_price .price, .special-price .price, .price")
        old = c.select_one(".old-price .price")
        img = c.select_one("img[src]")
        if not (a and price):
            continue
        href = "https:" + a["href"] if a["href"].startswith("//") else a["href"]
        if href in seen:
            continue
        seen.add(href)
        name = "Onitsuka Tiger " + a.get_text(strip=True).title()
        p, o = num(price.get_text()), (num(old.get_text()) if old else None)
        src = img.get("src", "") if img else ""
        out.append({"name": name, "url": href, "line": "Onitsuka Tiger" if TARGETS.search(name) else None,
                    "image": ("https:" + src if src.startswith("//") else src) or None,
                    "rrp": o or p, "price": p, "discount_pct": pct(o or p, p), "stock_verified": False})
    return [o for o in out if o["line"]]


async def scrape_list(ctx, url):
    s, h = await fetch_html(ctx, url, 5000)
    return s, (parse_list(h) if h else [])

"""ASOS UK search pages: prices from card aria-labels. Sizes not fetched (check stock)."""
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, num, pct

PRICE = re.compile(r"Original price:?\s*£([\d.,]+),?\s*current price:?\s*£([\d.,]+)", re.I)


def parse_list(html):
    out = []
    for a in BeautifulSoup(html, "lxml").select('a[href*="/prd/"]'):
        label = a.get("aria-label", "")
        if not label:
            continue
        name = label.split(", Original price")[0].split(", current price")[0].split(", Current price")[0]
        m = PRICE.search(label)
        if m:
            rrp, price = num(m.group(1)), num(m.group(2))
        else:
            price = num(label.split("price")[-1])
            rrp = price
        img = a.select_one("img")
        src = img.get("src", "") if img else ""
        out.append({"name": name, "url": a["href"].split("#")[0], "line": classify(name),
                    "image": ("https:" + src if src.startswith("//") else src) or None,
                    "rrp": rrp, "price": price, "discount_pct": pct(rrp, price), "stock_verified": False})
    return [o for o in out if o["line"]]


async def scrape_search(ctx, query):
    s, h = await fetch_html(ctx, f"https://www.asos.com/gb/search/?q={query.replace(' ', '+')}", 4000)
    return s, (parse_list(h) if h else [])

"""ASOS UK search pages: prices from card aria-labels. Deal candidates are then stock-checked on their
product page, which embeds every variant's size label and live `isInStock` flag."""
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, norm_uk, num, pct

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


VARIANT = re.compile(r'"variantId":(\d+),"size":"([^"]+)"')
STOCK = re.compile(r'"id":(\d+),"isInStock":(true|false)')
IMAGE = re.compile(r'"url":"(images\.asos-media\.com/products/[^"]+)"')


def parse_stock(html, pid=""):
    """{uk_size: in_stock} from a product page, plus whether sizes are women's (WM US) and the main image.
    Only stock ids belonging to this product's own variants are used; the page also embeds other products."""
    variants = dict(VARIANT.findall(html))
    stock = {vid: v == "true" for vid, v in STOCK.findall(html) if vid in variants}
    sizes, womens = {}, False
    for vid, label in variants.items():
        uk = norm_uk(label)
        if uk and vid in stock:
            sizes[uk] = sizes.get(uk, False) or stock[vid]
        womens = womens or bool(re.match(r"W(M)?\s*US", label))
    img = next((u for u in IMAGE.findall(html) if f"/{pid}-" in u), None) if pid else None
    return sizes, womens, ("https://" + img + "?wid=480" if img else None)


async def check_sizes(ctx, url):
    s, h = await fetch_html(ctx, url, 2500)
    pid = (re.search(r"/prd/(\d+)", url) or [None, ""])[1]
    sizes, womens, img = parse_stock(h, pid) if h else ({}, False, None)
    return {"http": s, "sizes": sizes, "verified": bool(sizes), "womens_sizing": womens, "image": img}

"""Vinted UK catalog pages (resale). Cards carry brand, condition, size and price in the image alt text."""
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, num

BASE = "https://www.vinted.co.uk"
ALT = re.compile(r"^(?P<title>.*?), Brand: (?P<brand>.*?), Condition: (?P<cond>.*?), Size: (?P<size>.*?), (?P<price>[\d.,]+) £", re.S)


def parse_list(html):
    out = []
    for img in BeautifulSoup(html, "lxml").select('img[data-testid$="--image--img"]'):
        m = ALT.match(img.get("alt", ""))
        a = img.find_parent("div", attrs={"data-testid": re.compile(r"^product-item-id-\d+$")})
        link = a.select_one('a[href^="/items/"]') if a else None
        if not (m and link):
            continue
        name = f"{m['brand']} {m['title']}"
        out.append({"name": name, "url": BASE + link["href"].split("?")[0], "line": classify(name),
                    "image": img.get("src"), "price": num(m["price"]), "rrp": None, "discount_pct": None,
                    "condition": m["cond"], "size": m["size"].replace("UK", "").strip(), "resale": True})
    return [o for o in out if o["line"]]


async def scrape_search(ctx, query):
    s, h = await fetch_html(ctx, f"{BASE}/catalog?search_text={query.replace(' ', '%20')}&order=newest_first", 5000)
    return s, (parse_list(h) if h else [])

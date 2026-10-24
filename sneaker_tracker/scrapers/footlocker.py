"""Foot Locker UK listing pages. Prices from cards; deal candidates are stock-checked on the product page,
whose size buttons are marked "Sold Out" when a size has no stock."""
import json
import re
from bs4 import BeautifulSoup
from .common import classify, fetch_html, norm_uk, num, pct

BASE = "https://www.footlocker.co.uk"


def parse_list(html):
    soup, out = BeautifulSoup(html, "lxml"), []
    for a in soup.select("a[data-productcard]"):
        try:
            meta = json.loads(a["data-productcard"])
        except Exception:
            continue
        txt = a.get_text(" ", strip=True)
        spans = a.select('[data-testid="ProductPrice"] span[aria-hidden="true"]')
        prices = [num(s.get_text()) for s in spans if "£" in s.get_text()]
        if not prices:
            continue
        price, rrp = prices[0], (prices[1] if len(prices) > 1 else prices[0])
        name = re.sub(r"\s+", " ", meta.get("name", "")) + " " + txt.split("Men")[0].strip()
        card = a.find_parent(attrs={"data-testid": re.compile("ProductCard")}) or a.parent
        img = card.select_one("img") if card else None
        full = a.select_one("span.relative")
        full = re.sub(r"\s+", " ", full.get_text(" ", strip=True)) if full else meta.get("name", "").strip()
        out.append({"name": full, "url": BASE + a["href"], "line": classify(txt + " " + meta.get("name", "")),
                    "image": (img.get("src") if img and (img.get("src") or "").startswith("http") else None),
                    "rrp": rrp, "price": price, "discount_pct": pct(rrp, price), "stock_verified": False})
    return [o for o in out if o["line"]]


async def scrape_list(ctx, url):
    s, h = await fetch_html(ctx, url, 5000)
    return s, (parse_list(h) if h else [])


def parse_sizes(html):
    """{uk_size: in_stock} from size buttons: aria-label 'Size: 8.5' or 'Size: 9 - Sold Out'."""
    sizes = {}
    for b in BeautifulSoup(html, "lxml").select('button[aria-label^="Size:"]'):
        label = b["aria-label"][5:].strip()
        uk = norm_uk(label.split(" - ")[0])
        if uk:
            sizes[uk] = sizes.get(uk, False) or "sold out" not in label.lower()
    return sizes


async def check_sizes(ctx, url):
    s, h = await fetch_html(ctx, url, 3000)
    sizes = parse_sizes(h) if h else {}
    return {"http": s, "sizes": sizes, "verified": bool(sizes)}

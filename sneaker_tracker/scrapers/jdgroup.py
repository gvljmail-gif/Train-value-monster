"""Parser for the JD Group storefront platform (size?, JD Sports, Footpatrol)."""
import html as htmllib
import re
from .common import fetch_html

ITEM = re.compile(r'<li class="productListItem.*?</li>', re.S)
PRICE = re.compile(r'£\s*([\d,]+\.?\d*)')


def _money(s):
    m = PRICE.search(s or "")
    return float(m.group(1).replace(",", "")) if m else None


def parse_list(html, base):
    items = []
    for card in ITEM.findall(html):
        href = re.search(r'href="(/product/[^"]+)"', card)
        title = re.search(r'data-e2e="product-listing-name">([^<]+)<', card)
        was = re.search(r'class="was">(.*?)</span>\s*</span>', card, re.S)
        now = re.search(r'data-e2e="product-listing-price">(.*?)</span>\s*</span>', card, re.S)
        # first absolute product photo URL; \s before src avoids matching data-fallbacksrc
        img = re.search(r'\ssrc="(https?://[^"]+)"', card) or re.search(r'data-srcset="(https?://[^\s"]+)', card)
        if not (href and title and now):
            continue
        was_p, now_p = _money(was.group(1) if was else None), _money(now.group(1))
        pct = round((1 - now_p / was_p) * 100) if was_p and now_p else 0
        items.append({
            "name": htmllib.unescape(title.group(1)).strip(),
            "url": base + href.group(1),
            "image": htmllib.unescape(img.group(1)) if img else None,
            "rrp": was_p, "price": now_p, "discount_pct": pct,
        })
    return items


def parse_sizes(html):
    """UK sizes in stock on a product page: {size: True}. data-stock>0 = in stock."""
    out = {}
    for m in re.finditer(r'<button[^>]*data-size="([^"]+)"[^>]*data-stock="(\d+)"', html):
        out[m.group(1)] = int(m.group(2)) > 0
    return out


async def scrape_list(ctx, base, path):
    status, html = await fetch_html(ctx, base + path)
    return status, (parse_list(html, base) if html else [])


async def check_sizes(ctx, url):
    status, html = await fetch_html(ctx, url, wait_ms=1500)
    return status, (parse_sizes(html) if html else {})

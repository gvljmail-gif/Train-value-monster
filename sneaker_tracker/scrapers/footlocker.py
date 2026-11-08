"""Foot Locker UK search results, read from the server-rendered page state, not the product grid.

Every search page embeds its full result set in `window.footlocker = { STATE_FROM_SERVER: {...} }` under
`search` (products with price/originalPrice, pagination, facets). The visible grid is drawn from that state
by client-side code that often fails to draw it (Nov 2026: 'nike dunk', 'air force 1' and 'air max 95'
came back as an empty grid or an 'All Products' page while the state held all 24-129 results), which the old
DOM parser read as zero items. The state is there whether or not the grid renders.

Queries use the site's own SAP Hybris facet syntax, `<terms>:<sort>:<facet>:<value>...`, e.g.
`air max 90:relevance:gender:Men:saleProduct:True`, so men's sale results fit on one 48-item page. The
server ignores `currentPage`, so a query with more results than one page is fetched again sorted
price-asc and price-desc and the pages are merged (covers up to 2 x 48).

Deal candidates are stock-checked on the product page, whose size buttons are marked "Sold Out".
"""
import json
import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from .common import classify, fetch_html, norm_uk, pct

BASE = "https://www.footlocker.co.uk"
IMG = "?wid=250&hei=250"  # same rendition the grid used, so already-uploaded photos are reused


def search_url(query):
    return f"{BASE}/en/search?query={quote(query, safe='')}"


def page_state(html):
    """The `search` object from the embedded server state, or None if the page has none (challenge page,
    markup change)."""
    i = html.find("STATE_FROM_SERVER")
    j = html.find("{", i) if i >= 0 else -1
    if j < 0:
        return None
    try:
        state = json.JSONDecoder().raw_decode(html, j)[0]
    except ValueError:
        return None
    s = state.get("search") if isinstance(state, dict) else None
    return s if isinstance(s, dict) and isinstance(s.get("products"), list) else None


def slug(name):
    """'Nike Air Max 90 - Men Shoes' -> 'nike-air-max-90-men-shoes', as the site's own product links: apostrophes
    dropped ("World's" -> 'worlds'), any other run of punctuation becomes one hyphen ('TL 2.5' -> 'tl-2-5')."""
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"['\u2019`]", "", name.lower())).strip("-")


def _value(d):
    return d.get("value") if isinstance(d, dict) and isinstance(d.get("value"), (int, float)) else None


def parse_products(products):
    out = []
    for p in products:
        name, sku, price = (p.get("name") or "").strip(), p.get("sku"), _value(p.get("price"))
        if not (name and sku and price):
            continue
        rrp = _value(p.get("originalPrice")) or price
        style = ((p.get("baseOptions") or [{}])[0].get("selected") or {}).get("style") or ""
        full = name.replace(" - ", " ") + (" " + style.replace("-", " - ") if style else "")
        img = next((i.get("url") for i in p.get("images") or [] if i.get("url")), None)
        out.append({"name": full, "url": f"{BASE}/en/product/{slug(name)}/{sku}.html", "line": classify(name),
                    "image": (img.split("?")[0] + IMG) if img else None,
                    "rrp": rrp, "price": float(price), "discount_pct": pct(rrp, price), "stock_verified": False})
    return [o for o in out if o["line"]]


def parse_list(html):
    """(items, total results the site reported, skus on this page) for one search page;
    ([], None, set()) if the page carries no search state."""
    s = page_state(html)
    if s is None:
        return [], None, set()
    return (parse_products(s["products"]), (s.get("pagination") or {}).get("totalResults"),
            {p.get("sku") for p in s["products"]})


def _resorted(query, sort):
    terms, _, rest = query.partition(":")
    parts = rest.split(":") if rest else ["relevance"]
    return ":".join([terms, sort] + parts[1:])


async def scrape_search(ctx, query):
    """(status, items, meta). meta: `unreadable` when the page loaded without a search state (markup changed
    or a challenge page), `short` when the site reported more results than could be fetched."""
    s, h = await fetch_html(ctx, search_url(query), 1500)  # state is in the HTML; no need to wait for the grid
    items, total, skus = parse_list(h) if h else ([], None, set())
    if s == 200 and total is None:
        return s, [], {"unreadable": True}
    if total and total > len(skus):  # more than one page: the server ignores currentPage, so re-sort instead
        for sort in ("price-asc", "price-desc"):
            _, h2 = await fetch_html(ctx, search_url(_resorted(query, sort)), 1500)
            more, _, more_skus = parse_list(h2) if h2 else ([], None, set())
            items, skus = items + more, skus | more_skus
    meta = {"short": f"{len(skus)} of {total} results"} if total and len(skus) < total else {}
    return s, list({i["url"]: i for i in items}.values()), meta


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

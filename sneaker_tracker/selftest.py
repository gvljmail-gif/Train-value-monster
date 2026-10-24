"""Offline checks for the parsers and rules (no network). Run: python3.13 -m sneaker_tracker.selftest
Fixtures mirror the live page/JSON shapes seen on 24 Oct 2026; if a site changes, update the fixture with it."""
from . import health
from .rules import enrich, key, lanes
from .scrapers import asos, footlocker, nike, shopify
from .scrapers.common import norm_uk


def check_norm_uk():
    cases = {"8.5": "8.5", "UK 9": "9", "UK8.5": "8.5", "UK 9 (EU 44)": "9", "WM US 11 - UK 8.5": "8.5",
             "6 (EU 40)": "6", "EU 44": None, "Medium": None, "10": "10"}
    for label, want in cases.items():
        assert norm_uk(label) == want, (label, norm_uk(label), want)


def check_shopify():
    def prod(title, vendor="Nike", ptype="size > Men's > Footwear", tags=(), sizes=(("8.5", True), ("9", False))):
        return {"title": title, "vendor": vendor, "product_type": ptype, "tags": list(tags), "handle": "h-im2211-001",
                "images": [{"src": "//cdn.shopify.com/x.jpg"}],
                "variants": [{"option1": s, "available": a, "price": "80.00", "compare_at_price": "145.00"} for s, a in sizes]}
    items = shopify.parse_products([
        prod("Air Max 90"),
        prod("Air Max 90", ptype="size > Women's > Footwear"),           # women's: dropped
        prod("Air Max 90 Sneaker", tags=["cat_high:Footwear", "gender:Womens"], ptype=""),  # END. women's: dropped
        prod("Air Max 90 Sneaker", tags=["cat_high:Apparel", "gender:Mens"], ptype=""),     # not footwear: dropped
        prod("Club C", vendor="Reebok"),                                   # vendor not tracked: dropped
    ], "https://shop.example", ["8.5", "9"])
    assert len(items) == 1, items
    it = items[0]
    assert it["name"] == "Nike Air Max 90" and it["all_sizes"] == {"8.5": True, "9": False}
    assert it["stock_verified"] and it["price"] == 80 and it["rrp"] == 145 and it["image"] == "https://cdn.shopify.com/x.jpg"


def check_footlocker():
    html = ('<button aria-label="Size: 8.5">8.5</button><button aria-label="Size: 9 - Sold Out">9</button>'
            '<button aria-label="Size: 6 (EU 40)">6</button>')
    assert footlocker.parse_sizes(html) == {"8.5": True, "9": False, "6": True}


def check_nike():
    html = ('"label":"9.5","localizedLabel":"8.5","localizedLabelPrefix":"UK","label":"10","localizedLabel":"9",'
            '"localizedLabelPrefix":"UK"<script type="application/ld+json">{"@type":"ProductGroup","hasVariant":['
            '{"@type":"Product","size":"9.5","offers":{"availability":"https://schema.org/InStock"}}]}</script>')
    assert nike.parse_sizes(html) == {"8.5": True, "9": False}  # 9 absent from offers = sold out
    assert nike.parse_sizes("<html></html>") == {}  # no offers = unknown, not sold out


def check_asos():
    html = ('{"variantId":11,"size":"UK 8.5","brandSize":"x"},{"variantId":12,"size":"UK 9","brandSize":"x"}'
            '"variants":[{"id":11,"isInStock":true},{"id":12,"isInStock":false},{"id":99,"isInStock":true}]'
            '"url":"images.asos-media.com/products/other/555-1-red""url":"images.asos-media.com/products/this/123-1-grey"')
    sizes, womens, img = asos.parse_stock(html, "123")
    assert sizes == {"8.5": True, "9": False} and not womens
    assert img == "https://images.asos-media.com/products/this/123-1-grey?wid=480"


def check_rules():
    base = {"line": "Air Max 90/95/97", "stock_verified": True, "sizes": {"8.5": True, "9": False}}
    inflated = enrich({**base, "name": "Air Max 90", "source": "size", "url": "u1", "price": 90, "rrp": 250})
    assert inflated["inflated"] and inflated["eff_rrp"] == 145 * 1.15
    very = enrich({**base, "name": "Nike Air Max 90", "source": "very", "url": "u2", "price": 80, "rrp": 80})
    assert very["vs_ref"] and very["eff_pct"] == round((1 - 80 / 145) * 100)
    sold_out = {**base, "name": "Air Max 95", "source": "end", "url": "u3", "price": 60, "rrp": 185, "sizes": {"8.5": False, "9": False}}
    unknown = {**base, "name": "Air Max 95", "source": "asos", "url": "u4", "price": 60, "rrp": 185,
               "stock_verified": False, "sizes": {"8.5": None, "9": None}}
    live, check = lanes([{**base, "name": "Air Max 90", "source": "end", "url": "x/ib7862-100", "price": 70, "rrp": 145},
                         sold_out, unknown])
    assert [g[0]["url"] for g in live] == ["x/ib7862-100"] and [g[0]["url"] for g in check] == ["u4"]
    assert key({"url": "https://e.com/products/nike-x-ib7862-100", "name": ""}) == "IB7862-100"


def check_health():
    base = {("jd", "q"): 30, ("nike", "killshot"): 0}
    row = lambda src, url, http, n: {"source": src, "url": url, "http": http, "items": n}
    assert health.page_state(row("jd", "q", 200, 0), base, {("jd", "q"): 25}) == "missed"
    assert health.page_state(row("jd", "q", 200, 0), base, {("jd", "q"): 0}) == "changed"
    assert health.page_state(row("nike", "killshot", 200, 0), base, {}) == "quiet"
    assert health.page_state(row("jd", "q", 404, 0), base, {}) == "changed"
    assert health.page_state(row("jd", "q", 403, 0), base, {}) == "blocked"


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items()) if k.startswith("check_")]
    for c in checks:
        c()
    print(f"selftest: {len(checks)} checks passed")

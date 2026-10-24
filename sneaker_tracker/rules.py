"""The deal rules, in one place, shared by run.py (which items to stock-check) and report.py (the lanes).

Deal = price at least `deal_threshold_pct` below typical RRP. The retailer's was-price is used, capped at
`rrp_tolerance` x the reference RRP for the model (stops inflated was-prices). Sources that never show a
was-price (`"was_price": false`, e.g. Very) are measured against the reference RRP directly.
Live = deal AND stock confirmed in UK 8.5 or 9 from a real stock signal. Otherwise: Check stock.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
SIZES, THRESH = CFG["sizes"], CFG["deal_threshold_pct"]
SOURCES = CFG["sources"]


def label(src):
    return SOURCES.get(src, {}).get("label", src)


def ref_for(p):
    n = p["name"].lower()
    for k, v in CFG["ref_rrp"].items():
        if k.lower() in n:
            return v
    return CFG["ref_rrp"].get(p.get("line"))


def enrich(p):
    """Add ref_rrp, eff_rrp, eff_pct and inflated (was-price above typical RRP) to a retail item."""
    rrp, price, ref = p.get("rrp"), p.get("price"), ref_for(p)
    no_was = SOURCES.get(p.get("source"), {}).get("was_price") is False
    if no_was and ref:
        eff = ref
    elif rrp and ref:
        eff = min(rrp, ref * CFG["rrp_tolerance"])
    else:
        eff = rrp
    p["ref_rrp"], p["eff_rrp"] = ref, eff
    p["eff_pct"] = round((1 - price / eff) * 100) if (eff and price and eff > price) else 0
    p["inflated"] = bool(rrp and ref and not no_was and rrp > ref * CFG["rrp_tolerance"])
    p["vs_ref"] = bool(no_was and ref)
    return p


def is_candidate(p):
    """Worth a product-page stock check: a retail deal on the rules above, or any retail Air Jordan 2."""
    return not p.get("resale") and (enrich(p)["eff_pct"] >= THRESH or p.get("line") == "Air Jordan 2")


def has_size(p):
    return any((p.get("sizes") or {}).values())


STYLE = re.compile(r"(?<![a-z0-9])([a-z]{2}\d{4}-\d{3})(?![0-9])", re.I)


def key(p):
    """Groups the same shoe across retailers by Nike style code (e.g. IB7862-100, in END./Nike URLs).
    Without a code the item stands alone: names alone merged different colourways (END. names omit colour)."""
    m = STYLE.search(p["url"]) or STYLE.search(p["name"])
    return m.group(1).upper() if m else p["url"]


def lanes(products):
    """(live, check): lists of groups (same shoe across retailers), cheapest first within a group.
    Check = deal whose stock could not be confirmed: sizes listed without stock data, unknown (prices-only
    source or failed product-page check). A confirmed sell-out in both sizes drops the item entirely."""
    live, check = {}, {}
    for p in map(enrich, [x for x in products if not x.get("resale")]):
        if p["eff_pct"] < THRESH or not p.get("price"):
            continue
        sizes = p.get("sizes") or {}
        if p.get("stock_verified"):
            if has_size(p):
                live.setdefault(key(p), []).append(p)
        elif has_size(p) or not sizes or None in sizes.values():
            check.setdefault(key(p), []).append(p)
    live = [sorted(v, key=lambda x: x["price"]) for v in live.values()]
    live_keys = {key(v[0]) for v in live}
    check = [sorted(v, key=lambda x: x["price"]) for k, v in check.items() if k not in live_keys]
    return live, check

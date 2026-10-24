"""Run all scrapers, verify 8.5/9 stock where possible, write a dated snapshot + coverage table.

Usage (from repo root): python3.13 -m sneaker_tracker.run

Stock semantics per item (`sizes` = {'8.5': bool|None, '9': ...}):
  stock_verified=True  -> sizes come from a real stock signal: Shopify `available` (size?, Footpatrol, END.),
                          JD's in-stock size list, or the product page (ASOS isInStock, Foot Locker
                          "Sold Out" buttons, Nike schema.org offers)
  stock_verified=False -> stock unknown (None): prices-only source or the product-page check failed -> "check stock"
Resale items (`resale: True`) are kept only for styles in config `resale_lines` (out of production).

Fetch policy: each page is retried with backoff when blocked (403/429/timeout) or when it comes back empty
but normally has items; after `breaker` consecutive blocked pages a source is left alone for the rest of the run.
"""
import asyncio
import datetime
import json

from . import health
from .rules import CFG, ROOT, SIZES, is_candidate, label, lanes
from .scrapers import asos, footlocker, goat, jd, nike, onitsuka, shopify, very, vinted
from .scrapers.common import adult_mens, browser_context

LIST_MODS = {"nike": nike, "footlocker": footlocker, "onitsuka": onitsuka}
SEARCH_MODS = {"jd": jd, "asos": asos, "very": very, "vinted": vinted, "goat": goat}
SIZE_CHECK = {"nike": nike, "footlocker": footlocker, "asos": asos}  # stock read from the product page
CHECKS_PER_SOURCE = 3  # simultaneous product-page checks per retailer


def cov(src, url, status, n, note=""):
    res = "ok" if n else ("blocked" if status in (403, 429, None) else "empty")
    return {"source": src, "url": url, "http": status, "items": n, "result": res, "note": note}


def pages(ctx, spec):
    """[(coverage url, zero-arg coroutine factory)] for every page a source fetches."""
    t = spec["type"]
    if t == "shopify":
        link = spec.get("link_base", spec["base"])
        return [(f"{spec['base']}/collections/{h}",
                 lambda h=h: shopify.scrape_collection(ctx, spec["base"], h, link, SIZES)) for h in spec["collections"]]
    if t in SEARCH_MODS:
        return [(f"search: {q}", lambda q=q: SEARCH_MODS[t].scrape_search(ctx, q)) for q in spec["queries"]]
    return [(u, lambda u=u: LIST_MODS[t].scrape_list(ctx, u)) for u in spec["lists"]]


async def scrape_source(ctx, src, spec, base):
    if spec["type"] == "blocked":
        return [], [cov(src, "-", 403, 0, spec["note"])]
    found, coverage, blocked_run = [], [], 0
    backoff = spec.get("backoff", [6, 20])
    for i, (url, fetch) in enumerate(pages(ctx, spec)):
        if blocked_run >= spec.get("breaker", 3):
            coverage.append(cov(src, url, None, 0, "skipped: source was blocking this run"))
            continue
        if i and spec.get("delay"):
            await asyncio.sleep(spec["delay"])  # polite spacing for sites that rate-limit
        expect = base.get((src, url), health.BROKEN_MIN) >= health.BROKEN_MIN  # unknown page: assume items
        for attempt in range(len(backoff) + 1):
            s, items = await fetch()
            retry = not items and s not in (404, 410) and (s != 200 or expect)
            if not retry or attempt == len(backoff):
                break
            await asyncio.sleep(backoff[attempt])
        blocked_run = blocked_run + 1 if (not items and s in (403, 429, None)) else 0
        coverage.append(cov(src, url, s, len(items), f"{attempt} retries" if attempt else ""))
        found += items
    for it in found:
        it["source"] = src
    return found, coverage


async def verify_sizes(ctx, it, gates):
    """Fill it['sizes'] (and stock_verified) for a deal candidate."""
    if it.get("all_sizes") is not None:  # Shopify / JD: stock came with the listing
        ok = bool(it.get("stock_verified"))
        it["sizes"] = {s: (it["all_sizes"].get(s, False) if ok else None) for s in SIZES}
        return
    mod = SIZE_CHECK.get(it["source"])
    if not mod:
        it["sizes"] = {s: None for s in SIZES}  # Very / Onitsuka: prices only
        return
    async with gates[it["source"]]:
        r = await mod.check_sizes(ctx, it["url"])
        if not r["verified"] and r["http"] in (403, 429, None):
            await asyncio.sleep(5)
            r = await mod.check_sizes(ctx, it["url"])
    it["stock_verified"] = r["verified"]
    it["sizes"] = {s: (r["sizes"].get(s, False) if r["verified"] else None) for s in SIZES}
    it["size_check_http"] = r["http"]
    if r.get("womens_sizing"):
        it["womens_sizing"] = True
    if r.get("image") and not it.get("image"):
        it["image"] = r["image"]


def keep(it):
    if not adult_mens(it["name"]):
        return False
    if it.get("resale"):
        return it["line"] in CFG["resale_lines"] and (it.get("size") is None or it["size"] in SIZES)
    return True


async def main():
    today = datetime.date.today().isoformat()
    base = health.baselines(health.history(today))
    coverage, products = [], {}
    async with browser_context() as ctx:
        async def one(src, spec):
            try:
                return src, *(await scrape_source(ctx, src, spec, base))
            except Exception as e:  # one broken source must not sink the run
                return src, [], [cov(src, "-", None, 0, f"error: {type(e).__name__}: {str(e)[:80]}")]

        for src, items, cv in await asyncio.gather(*(one(s, sp) for s, sp in CFG["sources"].items())):
            coverage += cv
            for it in items:
                if keep(it):
                    products[it["url"]] = it
        todo = [it for it in products.values() if is_candidate(it)]
        gates = {s: asyncio.Semaphore(CHECKS_PER_SOURCE) for s in SIZE_CHECK}
        await asyncio.gather(*(verify_sizes(ctx, it, gates) for it in todo))
    checks = {}
    for it in todo:
        if it["source"] in SIZE_CHECK:
            c = checks.setdefault(it["source"], {"tried": 0, "verified": 0})
            c["tried"] += 1
            c["verified"] += bool(it.get("stock_verified"))
    snap = {"date": today, "coverage": coverage, "stock_checks": checks, "products": list(products.values())}
    h = health.assess(today, coverage, checks)  # also stamps each coverage row with its state
    (ROOT / "data" / f"{today}.json").write_text(json.dumps(snap, indent=1))
    (ROOT / "data" / "latest.json").write_text(json.dumps(snap, indent=1))
    summarise(snap, h)


def summarise(snap, h):
    P = snap["products"]
    live, check = lanes(P)
    aj2_retail = [p for p in P if not p.get("resale") and p["line"] == "Air Jordan 2" and any((p.get("sizes") or {}).values())]
    aj2_resale = [p for p in P if p.get("resale") and p["source"] == "vinted"]
    state = f"DEGRADED ({', '.join(h['reasons'])}): {h['msg']}" if h["degraded"] else f"healthy: {h['msg']}"
    print(f"{h['up']}/{h['counted']} sources up | {len(P)} items | {len(live)} LIVE | {len(check)} check-stock | "
          f"AJ2: {len(aj2_retail)} retail in size, {len(aj2_resale)} resale | {state}")
    for src, v in h["sources"].items():
        if v["status"] in ("down", "partial"):
            print(f"  {v['status']:7} {label(src):18} {v['pages_ok']}/{v['pages']} pages  {v['why']}")
    for src, c in snap["stock_checks"].items():
        print(f"  stock   {label(src):18} {c['verified']}/{c['tried']} product pages verified")
    for g in live:
        p = g[0]
        print("  LIVE ", label(p["source"]), f"-{p['eff_pct']}%", p["price"], p["name"][:55], p["sizes"])


if __name__ == "__main__":
    asyncio.run(main())

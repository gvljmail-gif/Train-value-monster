"""Run all scrapers, verify 8.5/9 stock where possible, write a dated snapshot + coverage table.

Usage (from repo root): /usr/bin/python3.13 -m sneaker_tracker.run

Stock semantics per item (`sizes` = {'8.5': bool|None, '9': ...}):
  stock_verified=True  -> sizes come from a real stock field (size?, Footpatrol, JD)
  stock_verified=False -> sizes merely *listed* on the product page, or unknown (None): report "check stock"
Resale items (`resale: True`) are kept only for styles in config `resale_lines` (out of production).
"""
import asyncio
import datetime
import json
import pathlib

from .scrapers import asos, end, footlocker, footpatrol, goat, jd, jdgroup, nike, onitsuka, schuh, very, vinted
from .scrapers.common import adult_mens, browser_context, classify

ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
SIZES, THRESH = CFG["sizes"], CFG["deal_threshold_pct"]
LIST_MODS = {"nike": nike, "end": end, "footlocker": footlocker, "onitsuka": onitsuka}
SEARCH_MODS = {"jd": jd, "asos": asos, "very": very, "schuh": schuh, "vinted": vinted, "goat": goat}
SIZE_CHECK = {"nike": nike, "end": end, "footlocker": footlocker}  # product pages list sizes (unverified stock)


def cov(src, url, status, n, note=""):
    res = "ok" if n else ("blocked" if status in (403, 429, None) else "empty")
    return {"source": src, "url": url, "http": status, "items": n, "result": res, "note": note}


async def scrape_source(ctx, src, spec):
    t, found, coverage = spec["type"], [], []
    if t == "blocked":
        return [], [cov(src, "-", 403, 0, spec["note"])]
    if t == "jdgroup":
        for path in spec["lists"]:
            s, items = await jdgroup.scrape_list(ctx, spec["base"], path)
            for it in items:
                it["line"] = classify(it["name"])
            coverage.append(cov(src, spec["base"] + path, s, len(items)))
            found += items
    elif t == "shopify":
        for h in spec["collections"]:
            s, items = await footpatrol.scrape_collection(ctx, h)
            coverage.append(cov(src, f"{footpatrol.BASE}/collections/{h}", s, len(items)))
            found += items
    elif t in SEARCH_MODS:
        for i, q in enumerate(spec["queries"]):
            if i and spec.get("delay"):
                await asyncio.sleep(spec["delay"])  # polite spacing for sites that rate-limit (Very)
            s, items = await SEARCH_MODS[t].scrape_search(ctx, q)
            coverage.append(cov(src, f"search: {q}", s, len(items)))
            found += items
    else:
        for url in spec["lists"]:
            s, items = await LIST_MODS[t].scrape_list(ctx, url)
            coverage.append(cov(src, url, s, len(items)))
            found += items
    for it in found:
        it["source"] = src
    return found, coverage


async def verify_sizes(ctx, it):
    """Fill it['sizes'] for an item."""
    if it.get("all_sizes") is not None:
        it["sizes"] = {s: it["all_sizes"].get(s) for s in SIZES}
        return
    if it["source"] == "size":
        status, sz = await jdgroup.check_sizes(ctx, it["url"])
        it["stock_verified"] = True
    elif it["source"] in SIZE_CHECK:
        status, sz = await SIZE_CHECK[it["source"]].check_sizes(ctx, it["url"])
    else:
        it["sizes"] = {s: None for s in SIZES}  # ASOS / Very / Onitsuka: not fetched
        return
    it["sizes"] = {s: sz.get(s) for s in SIZES}
    it["size_check_http"] = status


def keep(it, spec):
    if not adult_mens(it["name"]):
        return False
    if it.get("resale"):
        return it["line"] in CFG["resale_lines"] and (it.get("size") is None or it["size"] in SIZES)
    return True


async def main():
    today = datetime.date.today().isoformat()
    coverage, products = [], {}
    async with browser_context() as ctx:
        async def one(src, spec):
            try:
                return src, spec, *(await scrape_source(ctx, src, spec))
            except Exception as e:  # one broken source must not sink the run
                return src, spec, [], [cov(src, "-", None, 0, f"error: {type(e).__name__}: {str(e)[:80]}")]

        for src, spec, items, cv in await asyncio.gather(*(one(s, sp) for s, sp in CFG["sources"].items())):
            coverage += cv
            for it in items:
                if keep(it, spec):
                    products[it["url"]] = it
        todo = [it for it in products.values() if not it.get("resale")
                and ((it["discount_pct"] or 0) >= THRESH or it["line"] == "Air Jordan 2")]
        await asyncio.gather(*(verify_sizes(ctx, it) for it in todo))
    snap = {"date": today, "coverage": coverage, "products": list(products.values())}
    (ROOT / "data" / f"{today}.json").write_text(json.dumps(snap, indent=1))
    (ROOT / "data" / "latest.json").write_text(json.dumps(snap, indent=1))
    summarise(snap)


def summarise(snap):
    P, cov_ = snap["products"], snap["coverage"]
    retail = [p for p in P if not p.get("resale")]
    deals = [p for p in retail if (p["discount_pct"] or 0) >= THRESH]
    has = lambda p: any((p.get("sizes") or {}).values())
    live = [p for p in deals if p.get("stock_verified") and has(p)]
    check = [p for p in deals if not (p.get("stock_verified") and has(p)) and (has(p) or not p.get("stock_verified") and None in (p.get("sizes") or {}).values())]
    aj2_retail = [p for p in retail if p["line"] == "Air Jordan 2" and has(p)]
    aj2_resale = [p for p in P if p.get("resale")]
    srcs = {c["source"] for c in cov_ if c["result"] == "ok"}
    print(f"{sum(c['result'] == 'ok' for c in cov_)}/{len(cov_)} pages ok across {len(srcs)}/{len({c['source'] for c in cov_})} sources | "
          f"{len(P)} items | {len(deals)} >= {THRESH}% | {len(live)} LIVE verified | {len(check)} check-stock | "
          f"AJ2: {len(aj2_retail)} retail in size, {len(aj2_resale)} resale")
    bad = [c for c in cov_ if c["result"] != "ok"]
    for c in bad:
        print(f"  {c['result']:7} {c['http']} {c['source']:10} {c['url'][:70]} {c['note']}")
    for p in live:
        print("  LIVE ", p["source"], p["discount_pct"], p["price"], p["name"][:55], p["sizes"])
    for p in aj2_retail + aj2_resale:
        print("  AJ2  ", p["source"], p.get("price") or p.get("price_usd"), p["name"][:55], p.get("size") or p.get("sizes") or "")


if __name__ == "__main__":
    asyncio.run(main())

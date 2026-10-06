"""Run all scrapers, verify 8.5/9 stock where possible, write a dated snapshot + coverage table.

Usage (from repo root): /usr/bin/python3.13 -m sneaker_tracker.run

Stock semantics per item: stock_verified=True means sizes come from a real stock field
(size?, Footpatrol). False means sizes are merely *listed* on the product page (Nike, END.,
Foot Locker) and the report must say "check stock".
"""
import asyncio
import datetime
import json
import pathlib

from .scrapers import end, footlocker, footpatrol, jdgroup, nike
from .scrapers.common import adult_mens, browser_context, classify

ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
SIZES, THRESH = CFG["sizes"], CFG["deal_threshold_pct"]
LIST_MODS = {"nike": nike, "end": end, "footlocker": footlocker}


def cov(src, url, status, n, note=""):
    res = "ok" if n else ("blocked" if status in (403, 429, None) else "empty")
    return {"source": src, "url": url, "http": status, "items": n, "result": res, "note": note}


async def scrape_source(ctx, src, spec):
    t, found, coverage = spec["type"], [], []
    if t == "jdgroup":
        for path in spec["lists"]:
            s, items = await jdgroup.scrape_list(ctx, spec["base"], path)
            for it in items:
                it["line"] = classify(it["name"]) or "Jordan" if "jordan" in it["name"].lower() else classify(it["name"])
            coverage.append(cov(src, spec["base"] + path, s, len(items)))
            found += items
    elif t == "shopify":
        for h in spec["collections"]:
            s, items = await footpatrol.scrape_collection(ctx, h)
            coverage.append(cov(src, f"{footpatrol.BASE}/collections/{h}", s, len(items)))
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
    """Fill it['sizes'] ({'8.5': bool|None, '9': ...}) for discounted adult items."""
    if it.get("all_sizes") is not None:
        it["sizes"] = {s: it["all_sizes"].get(s) for s in SIZES}
        return
    if it["source"] == "size":
        status, sz = await jdgroup.check_sizes(ctx, it["url"])
        it["stock_verified"] = True
    else:
        status, sz = await LIST_MODS[it["source"]].check_sizes(ctx, it["url"])
    it["sizes"] = {s: sz.get(s) for s in SIZES}
    it["size_check_http"] = status


async def main():
    today = datetime.date.today().isoformat()
    coverage, products = [], {}
    async with browser_context() as ctx:
        for src, spec in CFG["sources"].items():
            try:
                items, cv = await scrape_source(ctx, src, spec)
            except Exception as e:  # one broken source must not sink the run
                items, cv = [], [cov(src, "-", None, 0, f"error: {type(e).__name__}: {str(e)[:80]}")]
            coverage += cv
            for it in items:
                if adult_mens(it["name"]):
                    products[it["url"]] = it
        for it in products.values():
            if it["discount_pct"] >= THRESH:
                await verify_sizes(ctx, it)
    snap = {"date": today, "coverage": coverage, "products": list(products.values())}
    (ROOT / "data" / f"{today}.json").write_text(json.dumps(snap, indent=1))
    (ROOT / "data" / "latest.json").write_text(json.dumps(snap, indent=1))

    deals = [p for p in snap["products"] if p["discount_pct"] >= THRESH]
    live = [p for p in deals if p.get("stock_verified") and any(p["sizes"].values())]
    check = [p for p in deals if not p.get("stock_verified") and any(p["sizes"].values())]
    ok = sum(1 for c in coverage if c["result"] == "ok")
    print(f"{ok}/{len(coverage)} pages ok | {len(products)} products | {len(deals)} >= {THRESH}% | "
          f"{len(live)} LIVE (verified) | {len(check)} check-stock")
    for c in coverage:
        print(f"  {c['result']:7} {c['http']} {c['items']:3} {c['source']:10} {c['url'][:80]} {c['note']}")
    for p in live:
        print("  LIVE ", p["source"], p["discount_pct"], p["price"], p["name"][:55], p["sizes"])
    for p in check:
        print("  CHECK", p["source"], p["discount_pct"], p["price"], p["name"][:55], p["sizes"])


if __name__ == "__main__":
    asyncio.run(main())

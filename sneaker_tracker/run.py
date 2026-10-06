"""Pilot runner: scrape sources, verify 8.5/9 stock on discounted items, write a snapshot.

Usage: python3.13 -m sneaker_tracker.run   (from repo root)
"""
import asyncio
import datetime
import json
import pathlib

from .scrapers import jdgroup
from .scrapers.common import browser_context

ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())


async def main():
    today = datetime.date.today().isoformat()
    coverage, products = [], {}
    async with browser_context() as ctx:
        for src, spec in CFG["sources"].items():
            for path in spec["lists"]:
                status, items = await jdgroup.scrape_list(ctx, spec["base"], path)
                coverage.append({"source": src, "url": spec["base"] + path,
                                 "http": status, "items": len(items),
                                 "result": "ok" if items else ("blocked" if status in (403, 429, None) else "empty")})
                for it in items:
                    it["source"] = src
                    products[it["url"]] = it
        # verify size stock only for items at/over the threshold (keeps requests low)
        for it in products.values():
            if it["discount_pct"] >= CFG["deal_threshold_pct"]:
                status, sizes = await jdgroup.check_sizes(ctx, it["url"])
                it["sizes"] = {s: sizes.get(s) for s in CFG["sizes"]}
                it["size_check_http"] = status
    snap = {"date": today, "coverage": coverage, "products": list(products.values())}
    (ROOT / "data" / f"{today}.json").write_text(json.dumps(snap, indent=1))
    (ROOT / "data" / "latest.json").write_text(json.dumps(snap, indent=1))
    deals = [p for p in snap["products"] if p["discount_pct"] >= CFG["deal_threshold_pct"]]
    live = [p for p in deals if any(p.get("sizes", {}).values())]
    print(f"{len(coverage)} pages, {len(products)} products, {len(deals)} >= threshold, {len(live)} live in size")
    for c in coverage:
        print(" ", c["result"], c["http"], c["items"], c["url"])
    for p in live:
        print("  LIVE", p["discount_pct"], p["price"], p["name"], p["sizes"])


if __name__ == "__main__":
    asyncio.run(main())

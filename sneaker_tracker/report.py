"""Turn data/latest.json into the artifact page.

  python3.13 -m sneaker_tracker.report prepare   # download images the page will show -> out/img/, out/upload_list.json
  python3.13 -m sneaker_tracker.report build     # render out/page.html (+ out/summary.json) using assets.json

Images are never hotlinked: the Claude run uploads out/img/* to the artifact's asset store and records
{filename: "/_blob/<id>"} in assets.json; build() only references uploaded files.

summary.json drives notifications:
  ping      live deals / Air Jordan 2 listings: any, or only new ones (config ping_on_live, ping_on_aj2 = "any"|"new")
  degraded  the tracker itself needs attention (health.py); health_msg says what, in one line
"""
import asyncio
import datetime
import hashlib
import html
import json
import subprocess
import sys

from . import health
from .rules import CFG, ROOT, SIZES, SOURCES, THRESH, has_size, label, lanes

OUT = ROOT / "out"
ORDER = ["Air Max 90/95/97", "Air Max", "Jordan", "Air Force 1", "Dunk", "Killshot", "Onitsuka Tiger"]
esc = html.escape


def stock_basis(src):
    spec = SOURCES.get(src, {})
    return spec.get("stock", "-") + (f" ({spec['stock_how']})" if spec.get("stock_how") else "")


def load():
    snap = json.loads((ROOT / "data" / "latest.json").read_text())
    prev = sorted((p for p in (ROOT / "data").glob("20*.json") if p.stem < snap["date"]), reverse=True)
    recent = [json.loads(p.read_text()) for p in prev[: CFG["new_window_days"]]]
    return snap, recent


def img_name(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def sniff(b):
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    return None


def selection(snap):
    live, check = lanes(snap["products"])
    check.sort(key=lambda g: -g[0]["eff_pct"])
    cards_live = sorted(live, key=lambda g: (ORDER.index(g[0]["line"]) if g[0]["line"] in ORDER else 99, -g[0]["eff_pct"]))
    cards_check = check[: CFG["max_check_cards"]]
    rows_check = check[CFG["max_check_cards"]:]
    resale = [p for p in snap["products"] if p.get("resale") and p["source"] == "vinted"]
    goat = sorted([p for p in snap["products"] if p["source"] == "goat"], key=lambda p: p["name"])
    aj2_retail = [p for p in snap["products"] if not p.get("resale") and p["line"] == "Air Jordan 2" and has_size(p)]
    return cards_live, cards_check, rows_check, aj2_retail, resale, goat


def shown_images(snap):
    cl, cc, _, aj, rs, _ = selection(snap)
    urls = [g[0].get("image") for g in cl + cc] + [p.get("image") for p in aj + rs]
    return [u for u in dict.fromkeys(urls) if u]


def thumb(url):
    """Ask the CDN for a small rendition: keeps assets light (cards show ~300px wide)."""
    if "amplience.net" in url and "?" not in url:
        return url + "?w=480&qlt=80"
    if "cdn.shopify.com" in url or "/cdn/shop/" in url:
        return url + ("&" if "?" in url else "?") + "width=480"
    if "media.endclothing.com" in url:
        return url.replace("w_1600", "w_480")
    return url


def _curl(url, dest):
    r = subprocess.run(["curl", "-s", "-m", "30", "-L", "-A", "Mozilla/5.0", "-o", str(dest), "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    b = dest.read_bytes() if dest.exists() else b""
    dest.unlink(missing_ok=True)
    return b if r.stdout.strip() == "200" else b""


async def _browser_fetch(urls):
    """Fallback for CDNs that reject curl (ASOS's hangs it, and 403s non-browser requests)."""
    from .scrapers.common import browser_context, fetch_image
    async with browser_context() as ctx:
        res = await asyncio.gather(*(fetch_image(ctx, u) for u in urls))
    return {u: (b if s == 200 else b"") for u, (s, b) in zip(urls, res)}


def prepare():
    snap, _ = load()
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    assets = json.loads((ROOT / "assets.json").read_text()) if (ROOT / "assets.json").exists() else {}
    todo = [u for u in shown_images(snap) if not any(k.startswith(img_name(u) + ".") for k in assets)]
    got = {u: _curl(thumb(u), OUT / "img" / (img_name(u) + ".tmp")) for u in todo}
    retry = [u for u, b in got.items() if not sniff(b)]
    if retry:
        fetched = asyncio.run(_browser_fetch([thumb(u) for u in retry]))
        got.update({u: fetched[thumb(u)] for u in retry})
    need, failed = [], []
    for u, b in got.items():
        ext = sniff(b)
        if ext:
            f = OUT / "img" / f"{img_name(u)}.{ext}"
            f.write_bytes(b)
            need.append(str(f))
        else:
            failed.append(u)
    (OUT / "upload_list.json").write_text(json.dumps({"files": need, "failed": failed}, indent=1))
    print(f"{len(need)} images to upload (batches of 25), {len(failed)} failed, "
          f"{len(shown_images(snap)) - len(todo)} already uploaded")


# ---------------------------------------------------------------- rendering
def asset_for(assets, url):
    if not url:
        return None
    base = img_name(url)
    for k, v in assets.items():
        if k.startswith(base + "."):
            return v
    return None


def money(x):
    return f"£{x:,.2f}" if x is not None else "-"


def photo(assets, url):
    a = asset_for(assets, url)
    return f'<img class="ph" src="{esc(a)}" alt="" loading="lazy">' if a else '<div class="ph none">no photo</div>'


def chips(p):
    out = []
    for s in SIZES:
        v = (p.get("sizes") or {}).get(s)
        if v is None:
            out.append(f'<span class="chip">UK {s} check</span>')
        elif p.get("stock_verified"):
            out.append(f'<span class="chip {"yes" if v else "no"}">UK {s} {"in stock" if v else "sold out"}</span>')
        else:
            out.append(f'<span class="chip {"yes" if v else "no"}">UK {s} {"listed" if v else "not listed"}</span>')
    return "".join(out)


def card_notes(p):
    notes = []
    if p["inflated"]:
        notes.append(f'{esc(label(p["source"]))} lists a was-price of {money(p["rrp"])}; typical RRP is about '
                     f'{money(p["ref_rrp"])}, so the discount is measured against that.')
    if p.get("vs_ref"):
        notes.append(f'{esc(label(p["source"]))} shows no was-price; the discount is against the typical RRP of {money(p["ref_rrp"])}.')
    if p.get("womens_sizing"):
        notes.append("Sold in women's sizing (UK 8.5 = W US 11): same length, usually a narrower fit.")
    return "".join(f'<p class="warn">{n}</p>' for n in notes)


def deal_card(g, assets, new_urls):
    p = g[0]
    is_new = p["url"] in new_urls
    new = '<span class="new">NEW</span>' if is_new else ""
    also = "".join(f'<li><a href="{esc(o["url"])}" target="_blank" rel="noopener">{esc(label(o["source"]))}</a> {money(o["price"])}</li>' for o in g[1:])
    return f"""<article class="card{' is-new' if is_new else ''}">{photo(assets, p.get("image"))}<div class="body">
<div class="row"><h3>{esc(p["name"])}</h3><span class="badge">-{p["eff_pct"]}%</span></div>{new}
<div class="price"><b>{money(p["price"])}</b><s>{money(p["eff_rrp"])}</s></div>
<div class="chips">{chips(p)}</div>{card_notes(p)}
<div class="src"><span>{esc(label(p["source"]))}</span><a href="{esc(p["url"])}" target="_blank" rel="noopener">View</a></div>
{('<ul class="also"><li class="lbl">Also at</li>' + also + '</ul>') if also else ''}
</div></article>"""


def seen_recently(recent):
    """URLs live, and Air Jordan 2 URLs listed in size, in any of the last new_window_days snapshots. A deal or listing is
    NEW only if absent from all of them, so a source that was down yesterday doesn't re-flag its items."""
    live = {p["url"] for s in recent for g in lanes(s["products"])[0] for p in g}
    listed = {p["url"] for s in recent for p in s["products"] if p.get("line") == "Air Jordan 2"
              and ((p.get("resale") and p["source"] == "vinted") or (not p.get("resale") and has_size(p)))}
    return live, listed


def coverage_rows(h):
    out = []
    for s, v in h["sources"].items():
        st = v["status"]
        cls = {"ok": "ok", "partial": "part", "expected": "bad", "down": "bad"}[st]
        text = {"ok": "ok", "partial": "partial", "expected": "blocked", "down": "down"}[st]
        why = v["why"] + (f", {v['days_down']} days" if v["days_down"] > 1 else "")
        note = "" if st == "ok" else (why or SOURCES.get(s, {}).get("note", ""))
        out.append(f'<tr><td>{esc(label(s))}</td><td class="n">{v["pages_ok"]}/{v["pages"]}</td><td class="n">{v["items"]}</td>'
                   f'<td>{esc(stock_basis(s))}</td><td><span class="st {cls}">{text}</span> {esc(note)}</td></tr>')
    return "".join(out)


def render(snap, recent, assets):
    cl, cc, rows, aj_retail, vinted, goat = selection(snap)
    h = health.assess(snap["date"], snap["coverage"], snap.get("stock_checks"))
    seen_live, seen_listed = seen_recently(recent)
    new_urls = ({g[0]["url"] for g in cl} - seen_live) if recent else set()
    new_aj2 = [p for p in vinted + aj_retail if p["url"] not in seen_listed] if recent else []
    date = datetime.date.fromisoformat(snap["date"])
    nice = f"{date.day} {date.strftime('%b %Y')}"
    verified = [label(s) for s, v in SOURCES.items() if v.get("stock") == "verified"]
    unverified = [label(s) for s, v in SOURCES.items() if v.get("stock") == "prices only"]

    def section_lines(groups):
        out = []
        lanes = []
        for line in ORDER:
            gs = [g for g in groups if g[0]["line"] == line or (line == "Jordan" and g[0]["line"] == "Air Jordan 2")]
            gs.sort(key=lambda g: g[0]["url"] not in new_urls)  # newest first, then biggest discount (stable)
            if gs:
                lanes.append((line, gs))
        lanes.sort(key=lambda l: not any(g[0]["url"] in new_urls for g in l[1]))  # lanes with new deals first
        for line, gs in lanes:
            if True:
                out.append(f'<h3 class="line">{esc(line)}</h3><div class="grid">' + "".join(deal_card(g, assets, new_urls) for g in gs) + "</div>")
        return "".join(out) or '<p class="empty">Nothing in this lane today.</p>'

    row_html = "".join(
        f'<tr><td>{esc(g[0]["name"])}</td><td class="n">{money(g[0]["price"])}</td><td class="n">-{g[0]["eff_pct"]}%</td>'
        f'<td>{esc(label(g[0]["source"]))}</td><td><a href="{esc(g[0]["url"])}" target="_blank" rel="noopener">View</a></td></tr>' for g in rows)

    def aj2_card(p, chip_html):
        new = '<span class="new">NEW</span>' if p in new_aj2 else ""
        return f"""<article class="card{' is-new' if new else ''}">{photo(assets, p.get("image"))}<div class="body"><h3>{esc(p["name"])}</h3>{new}
<div class="price"><b>{money(p["price"])}</b></div><div class="chips">{chip_html}</div>
<div class="src"><span>{esc(label(p["source"]))}</span><a href="{esc(p["url"])}" target="_blank" rel="noopener">View</a></div></div></article>"""

    vin = "".join(aj2_card(p, f'<span class="chip yes">UK {esc(p.get("size", "?"))}</span><span class="chip">{esc(p.get("condition", ""))}</span>') for p in sorted(vinted, key=lambda p: p not in new_aj2))
    ret = "".join(aj2_card(p, chips(p)) for p in aj_retail)
    goat_rows = "".join(
        f'<tr><td><a href="{esc(p["url"])}" target="_blank" rel="noopener">{esc(p["name"])}</a></td><td class="n">{("$%.0f" % p["price_usd"]) if p.get("price_usd") else "-"}</td><td class="n">{("$%.0f" % p["retail_usd"]) if p.get("retail_usd") else "-"}</td></tr>' for p in goat)

    aj_total = len(aj_retail) + len(vinted)
    live_ping = len(new_urls) if CFG.get("ping_on_live", "any") == "new" else len(cl)
    aj_ping = len(new_aj2) if CFG.get("ping_on_aj2", "any") == "new" else aj_total
    summary = {"date": snap["date"], "live": len(cl), "new_live": len(new_urls),
               "check": len(cc) + len(rows), "aj2_listings": aj_total, "new_aj2": len(new_aj2),
               "sources_ok": h["up"], "sources_total": h["counted"],
               "degraded": h["degraded"], "health_reasons": h["reasons"], "health_msg": h["msg"],
               "ping": live_ping > 0 or aj_ping > 0}
    banner = ""
    if h["degraded"]:
        banner = f'<p class="alert"><b>Tracker needs attention</b> ({esc(", ".join(h["reasons"]))}): {esc(h["msg"])}.</p>'
    elif h["down"]:
        banner = f'<p class="alert">{esc(h["msg"])}.</p>'
    css = (ROOT / "report.css").read_text()
    page = f"""<title>Sole Ticket</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>{css}</style>
<div class="wrap">
<header class="mast"><div><div class="eyebrow">UK sneaker deal tracker</div><h1>Sole&nbsp;Ticket</h1></div>
<div class="meta"><div><b>{nice}</b> · UK {SIZES[0]} / {SIZES[1]}</div><div>{len(cl)} live deals ({len(new_urls)} new) · {len(cc) + len(rows)} to check · {aj_total} Air Jordan 2</div><div>{h["up"]} of {h["counted"]} sources up</div></div></header>
{banner}
<section><div class="sh"><h2>Live deals</h2><span class="count">{len(cl)}</span></div>
<p class="note">At least {THRESH}% below typical RRP, with stock confirmed in UK {SIZES[0]} or {SIZES[1]}. Stock is read from each retailer's own stock data ({esc(", ".join(verified))}). Cards marked NEW were not live in the last {CFG["new_window_days"]} days. Where a retailer's was-price is above typical RRP, the discount is measured against typical RRP.</p>
{section_lines(cl)}</section>
<section><div class="sh"><h2>Check stock</h2><span class="count">{len(cc) + len(rows)}</span></div>
<p class="note">At least {THRESH}% below typical RRP, but stock could not be confirmed: {esc(", ".join(unverified))} show prices only, and a product-page check sometimes fails. Items confirmed sold out in both sizes are left out. Open the link to confirm UK {SIZES[0]} or {SIZES[1]}.</p>
{section_lines(cc)}
{('<div class="scroll"><table><thead><tr><th>More to check</th><th class="n">Price</th><th class="n">Off</th><th>Source</th><th></th></tr></thead><tbody>' + row_html + '</tbody></table></div>') if rows else ''}</section>
<section><div class="sh"><h2>Air Jordan 2 watch</h2><span class="count">{aj_total}</span></div>
<p class="note">Out of production, so every listing in UK {SIZES[0]} or {SIZES[1]} is shown whatever the price. Retailers first, then Vinted. NEW = not seen in the last {CFG["new_window_days"]} days. eBay UK is not covered yet: its API key is pending. GOAT is a reference price, not a listing in your size.</p>
{('<div class="grid">' + ret + vin + '</div>') if (ret or vin) else '<p class="empty">No Air Jordan 2 listings in UK 8.5 or 9 today.</p>'}
<div class="scroll"><table><thead><tr><th>GOAT reference</th><th class="n">Lowest ask (USD)</th><th class="n">Retail (USD)</th></tr></thead><tbody>{goat_rows}</tbody></table></div></section>
<section><div class="sh"><h2>Coverage</h2><span class="count">{h["up"]}/{h["counted"]}</span></div>
<div class="scroll"><table><thead><tr><th>Source</th><th class="n">Pages ok</th><th class="n">Items</th><th>Stock data</th><th>Status</th></tr></thead><tbody>{coverage_rows(h)}</tbody></table></div>
<p class="note">Schuh and StockX block automated browsers and are listed as blocked every day (not counted). Items are adult men's styles only.</p></section>
</div>"""
    return page, summary


def build():
    snap, recent = load()
    assets = json.loads((ROOT / "assets.json").read_text()) if (ROOT / "assets.json").exists() else {}
    page, summary = render(snap, recent, assets)
    OUT.mkdir(exist_ok=True)
    (OUT / "page.html").write_text(page)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    {"prepare": prepare, "build": build}[sys.argv[1]]()

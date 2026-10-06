"""Turn data/latest.json into the artifact page.

  python3.13 -m sneaker_tracker.report prepare   # download images the page will show -> out/img/, out/upload_list.json
  python3.13 -m sneaker_tracker.report build     # render out/page.html (+ out/summary.json) using assets.json

Images are never hotlinked: the Claude run uploads out/img/* to the artifact's asset store and records
{filename: "/_blob/<id>"} in assets.json; build() only references uploaded files.
"""
import datetime
import hashlib
import html
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
OUT = ROOT / "out"
SIZES, THRESH = CFG["sizes"], CFG["deal_threshold_pct"]
ORDER = ["Air Max 90/95/97", "Air Max", "Jordan", "Air Force 1", "Dunk", "Killshot", "Onitsuka Tiger"]
UNKNOWN_SIZE_SRC = {"asos", "very", "onitsuka"}  # prices only; sizes never fetched
STOCK_BASIS = {"size": "verified", "footpatrol": "verified", "jd": "verified", "nike": "listed", "end": "listed",
               "footlocker": "listed", "asos": "prices only", "very": "prices only", "onitsuka": "prices only",
               "vinted": "resale", "goat": "resale ref", "schuh": "-", "stockx": "-"}
LABEL = {"size": "size?", "footpatrol": "Footpatrol", "jd": "JD Sports", "nike": "Nike UK", "end": "END.",
         "footlocker": "Foot Locker UK", "asos": "ASOS", "very": "Very", "onitsuka": "Onitsuka Tiger UK",
         "vinted": "Vinted", "goat": "GOAT", "schuh": "Schuh", "stockx": "StockX"}
esc = html.escape


def load():
    snap = json.loads((ROOT / "data" / "latest.json").read_text())
    prev = sorted(p for p in (ROOT / "data").glob("20*.json") if p.stem < snap["date"])
    prev_snap = json.loads(prev[-1].read_text()) if prev else {"products": []}
    return snap, prev_snap


def ref_for(p):
    n = p["name"].lower()
    for key, v in CFG["ref_rrp"].items():
        if key.lower() in n:
            return v
    if p["line"] in CFG["ref_rrp"]:
        return CFG["ref_rrp"][p["line"]]
    return None


def enrich(p):
    """Add effective discount: the retailer's was-price is capped at ~typical RRP (stops inflated 'was' prices)."""
    rrp, price = p.get("rrp"), p.get("price")
    ref = ref_for(p)
    p["ref_rrp"] = ref
    eff = min(rrp, ref * CFG["rrp_tolerance"]) if (rrp and ref) else rrp
    p["eff_rrp"] = eff
    p["eff_pct"] = round((1 - price / eff) * 100) if (eff and price and eff > price) else 0
    p["inflated"] = bool(rrp and ref and rrp > ref * CFG["rrp_tolerance"])
    return p


def has_size(p):
    return any((p.get("sizes") or {}).values())


def key(p):
    k = re.sub(r"[^a-z0-9 ]", " ", p["name"].lower())
    k = re.sub(r"\b(nike|men|mens|shoes|shoe|trainers|trainer|sneaker|sneakers|the)\b", " ", k)
    return " ".join(k.split())


def lanes(products):
    live, check = {}, {}
    for p in map(enrich, [x for x in products if not x.get("resale")]):
        if p["eff_pct"] < THRESH or not p.get("price"):
            continue
        if p.get("stock_verified") and has_size(p):
            live.setdefault(key(p), []).append(p)
        elif not p.get("stock_verified") and (has_size(p) or p["source"] in UNKNOWN_SIZE_SRC):
            check.setdefault(key(p), []).append(p)
    live = [sorted(v, key=lambda x: x["price"]) for v in live.values()]
    live_keys = {key(v[0]) for v in live}
    check = [sorted(v, key=lambda x: x["price"]) for k, v in check.items() if k not in live_keys]
    return live, check


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
    if "cdn.shopify.com" in url:
        return url + ("&" if "?" in url else "?") + "width=480"
    if "media.endclothing.com" in url:
        return url.replace("w_1600", "w_480")
    return url


def prepare():
    snap, _ = load()
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    assets = json.loads((ROOT / "assets.json").read_text()) if (ROOT / "assets.json").exists() else {}
    need, failed = [], []
    for u in shown_images(snap):
        base = img_name(u)
        if any(k.startswith(base + ".") for k in assets):
            continue
        tmp = OUT / "img" / (base + ".tmp")
        r = subprocess.run(["curl", "-s", "-m", "30", "-L", "-A", "Mozilla/5.0", "-o", str(tmp), "-w", "%{http_code}", thumb(u)],
                           capture_output=True, text=True)
        b = tmp.read_bytes() if tmp.exists() else b""
        ext = sniff(b)
        if r.stdout.strip() == "200" and ext:
            f = OUT / "img" / f"{base}.{ext}"
            tmp.rename(f)
            need.append(str(f))
        else:
            failed.append(u)
            tmp.unlink(missing_ok=True)
    (OUT / "upload_list.json").write_text(json.dumps({"files": need, "failed": failed}, indent=1))
    print(f"{len(need)} images to upload (batches of 25), {len(failed)} failed, {len(shown_images(snap)) - len(need) - len(failed)} already uploaded")


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


def chips(p, live):
    out = []
    for s in SIZES:
        v = (p.get("sizes") or {}).get(s)
        if live:
            out.append(f'<span class="chip {"yes" if v else "no"}">UK {s} {"in stock" if v else "sold out"}</span>')
        elif p["source"] in UNKNOWN_SIZE_SRC:
            out.append(f'<span class="chip">UK {s} check</span>')
        else:
            out.append(f'<span class="chip {"yes" if v else "no"}">UK {s} {"listed" if v else "not listed"}</span>')
    return "".join(out)


def deal_card(g, assets, live, new_urls):
    p = g[0]
    badge = f'<span class="badge">-{p["eff_pct"]}%</span>'
    new = '<span class="new">NEW</span>' if p["url"] in new_urls else ""
    also = "".join(f'<li><a href="{esc(o["url"])}" target="_blank" rel="noopener">{esc(LABEL[o["source"]])}</a> {money(o["price"])}</li>' for o in g[1:])
    note = ""
    if p["inflated"]:
        note = f'<p class="warn">{esc(LABEL[p["source"]])} lists a was-price of {money(p["rrp"])}; typical RRP is about {money(p["ref_rrp"])}, so the discount is measured against that.</p>'
    elif p["eff_pct"] != p.get("discount_pct"):
        note = ""
    return f"""<article class="card">{photo(assets, p.get("image"))}<div class="body">
<div class="row"><h3>{esc(p["name"])}</h3>{badge}</div>{new}
<div class="price"><b>{money(p["price"])}</b><s>{money(p["eff_rrp"])}</s></div>
<div class="chips">{chips(p, live)}</div>{note}
<div class="src"><span>{esc(LABEL[p["source"]])}</span><a href="{esc(p["url"])}" target="_blank" rel="noopener">View</a></div>
{('<ul class="also"><li class="lbl">Also at</li>' + also + '</ul>') if also else ''}
</div></article>"""


def render(snap, prev, assets):
    cl, cc, rows, aj_retail, vinted, goat = selection(snap)
    prev_live = {g[0]["url"] for g in lanes(prev["products"])[0]} if prev["products"] else set()
    new_urls = {g[0]["url"] for g in cl} - prev_live if prev["products"] else set()
    cov = {}
    for c in snap["coverage"]:
        b = cov.setdefault(c["source"], {"ok": 0, "n": 0, "items": 0, "note": ""})
        b["n"] += 1
        b["ok"] += c["result"] == "ok"
        b["items"] += c["items"]
        b["note"] = b["note"] or c.get("note", "")
    src_ok = sum(1 for b in cov.values() if b["ok"])
    date = datetime.date.fromisoformat(snap["date"])
    nice = f"{date.day} {date.strftime('%b %Y')}"

    cov_rows = "".join(
        f'<tr><td>{esc(LABEL.get(s, s))}</td><td class="n">{b["ok"]}/{b["n"]}</td><td class="n">{b["items"]}</td>'
        f'<td>{esc(STOCK_BASIS.get(s, "-"))}</td>'
        f'<td><span class="st {"ok" if b["ok"] == b["n"] else "part" if b["ok"] else "bad"}">{"ok" if b["ok"] == b["n"] else "partial" if b["ok"] else "blocked"}</span> {esc(b["note"])}</td></tr>'
        for s, b in cov.items())

    def section_lines(groups, live):
        out = []
        for line in ORDER:
            gs = [g for g in groups if g[0]["line"] == line or (line == "Jordan" and g[0]["line"] == "Air Jordan 2")]
            if gs:
                out.append(f'<h3 class="line">{esc(line)}</h3><div class="grid">' + "".join(deal_card(g, assets, live, new_urls) for g in gs) + "</div>")
        return "".join(out) or '<p class="empty">Nothing in this lane today.</p>'

    row_html = "".join(
        f'<tr><td>{esc(g[0]["name"])}</td><td class="n">{money(g[0]["price"])}</td><td class="n">-{g[0]["eff_pct"]}%</td>'
        f'<td>{esc(LABEL[g[0]["source"]])}</td><td><a href="{esc(g[0]["url"])}" target="_blank" rel="noopener">View</a></td></tr>' for g in rows)

    vin = "".join(f"""<article class="card">{photo(assets, p.get("image"))}<div class="body"><h3>{esc(p["name"])}</h3>
<div class="price"><b>{money(p["price"])}</b></div><div class="chips"><span class="chip yes">UK {esc(p.get("size", "?"))}</span><span class="chip">{esc(p.get("condition", ""))}</span></div>
<div class="src"><span>Vinted</span><a href="{esc(p["url"])}" target="_blank" rel="noopener">View</a></div></div></article>""" for p in vinted)
    ret = "".join(f"""<article class="card">{photo(assets, p.get("image"))}<div class="body"><h3>{esc(p["name"])}</h3>
<div class="price"><b>{money(p["price"])}</b></div><div class="chips">{chips(p, p.get("stock_verified"))}</div>
<div class="src"><span>{esc(LABEL[p["source"]])}</span><a href="{esc(p["url"])}" target="_blank" rel="noopener">View</a></div></div></article>""" for p in aj_retail)
    goat_rows = "".join(
        f'<tr><td><a href="{esc(p["url"])}" target="_blank" rel="noopener">{esc(p["name"])}</a></td><td class="n">{("$%.0f" % p["price_usd"]) if p.get("price_usd") else "-"}</td><td class="n">{("$%.0f" % p["retail_usd"]) if p.get("retail_usd") else "-"}</td></tr>' for p in goat)

    aj_total = len(aj_retail) + len(vinted)
    degraded = src_ok < CFG["min_sources_ok"]
    summary = {"date": snap["date"], "live": len(cl), "new_live": len([g for g in cl if g[0]["url"] in new_urls]),
               "check": len(cc) + len(rows), "aj2_listings": aj_total, "sources_ok": src_ok, "sources_total": len(cov),
               "degraded": degraded, "ping": (len(cl) > 0 or aj_total > 0) and not degraded}
    banner = (f'<p class="alert">Degraded run: only {src_ok} of {len(cov)} sources returned data (minimum {CFG["min_sources_ok"]}). No alert sent.</p>' if degraded else "")
    css = (ROOT / "report.css").read_text()
    page = f"""<title>Sole Ticket</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>{css}</style>
<div class="wrap">
<header class="mast"><div><div class="eyebrow">UK sneaker deal tracker</div><h1>Sole&nbsp;Ticket</h1></div>
<div class="meta"><div><b>{nice}</b> · UK {SIZES[0]} / {SIZES[1]}</div><div>{len(cl)} live deals · {len(cc) + len(rows)} to check · {aj_total} Air Jordan 2</div><div>{src_ok} of {len(cov)} sources returned data</div></div></header>
{banner}
<section><div class="sh"><h2>Live deals</h2><span class="count">{len(cl)}</span></div>
<p class="note">At least {THRESH}% below typical RRP, with stock confirmed in UK {SIZES[0]} or {SIZES[1]}. Sources: size?, Footpatrol, JD Sports. Cards marked NEW were not live yesterday. Where a retailer's was-price is above typical RRP, the discount is measured against typical RRP.</p>
{section_lines(cl, True)}</section>
<section><div class="sh"><h2>Check stock</h2><span class="count">{len(cc) + len(rows)}</span></div>
<p class="note">At least {THRESH}% below typical RRP, but stock cannot be confirmed (END., Foot Locker, Nike list sizes without stock levels; ASOS, Very and Onitsuka Tiger are prices only). Open the link to confirm UK {SIZES[0]} or {SIZES[1]}.</p>
{section_lines(cc, False)}
{('<div class="scroll"><table><thead><tr><th>More to check</th><th class="n">Price</th><th class="n">Off</th><th>Source</th><th></th></tr></thead><tbody>' + row_html + '</tbody></table></div>') if rows else ''}</section>
<section><div class="sh"><h2>Air Jordan 2 watch</h2><span class="count">{aj_total}</span></div>
<p class="note">Out of production, so every listing in UK {SIZES[0]} or {SIZES[1]} is shown whatever the price. Retailers first, then Vinted (UK 8.5 or 9 only). eBay UK is not covered yet: its API key is pending. GOAT is a reference price, not a listing in your size.</p>
{('<div class="grid">' + ret + vin + '</div>') if (ret or vin) else '<p class="empty">No Air Jordan 2 listings in UK 8.5 or 9 today.</p>'}
<div class="scroll"><table><thead><tr><th>GOAT reference</th><th class="n">Lowest ask (USD)</th><th class="n">Retail (USD)</th></tr></thead><tbody>{goat_rows}</tbody></table></div></section>
<section><div class="sh"><h2>Coverage</h2><span class="count">{src_ok}/{len(cov)}</span></div>
<div class="scroll"><table><thead><tr><th>Source</th><th class="n">Pages ok</th><th class="n">Items</th><th>Stock data</th><th>Status</th></tr></thead><tbody>{cov_rows}</tbody></table></div>
<p class="note">Schuh and StockX block automated browsers and are reported as blocked each day. Items are adult men's styles only.</p></section>
</div>"""
    return page, summary


def build():
    snap, prev = load()
    assets = json.loads((ROOT / "assets.json").read_text()) if (ROOT / "assets.json").exists() else {}
    page, summary = render(snap, prev, assets)
    OUT.mkdir(exist_ok=True)
    (OUT / "page.html").write_text(page)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    {"prepare": prepare, "build": build}[sys.argv[1]]()

"""Source health from today's coverage plus the dated snapshots in data/.

Each page gets a state:
  ok       returned items
  quiet    HTTP 200, no items, and it normally returns few or none (e.g. a 'killshot' search)
  missed   HTTP 200, no items, on a page that normally has >= BROKEN_MIN, for the first run: usually a slow
           load; not alarming on its own
  blocked  403/429/timeout: bot protection or rate limiting (often transient)
  changed  404/410, or 'missed' two runs in a row: the site moved or its markup changed, so the scraper
           needs fixing (never self-heals)
Each source is up (some page ok), down (none), or expected (config `expected_blocked`, e.g. Schuh).
The run is degraded when a stock-verified source is down, any page looks changed, a retailer's product-page
stock check fails on every item, or fewer than `min_sources_ok` sources are up. The health push keys off that.
"""
import json
import statistics

from .rules import CFG, ROOT, SOURCES, label

HISTORY_DAYS = 60
BROKEN_MIN = 5  # median items on good days at or above which an empty 200 means "changed", not "quiet"


def history(before):
    """Coverage lists of up to HISTORY_DAYS snapshots dated before `before`, newest first."""
    files = sorted((p for p in (ROOT / "data").glob("20*.json") if p.stem < before), reverse=True)[:HISTORY_DAYS]
    return [(p.stem, json.loads(p.read_text())["coverage"]) for p in files]


def baselines(hist):
    """{(source, url): median items on the days that page returned any; 0 for pages seen but always empty}.
    Pages never seen (new URLs) are absent: callers treat them as expected to return items."""
    seen = {}
    for _, cov in hist:
        for c in cov:
            if c["items"] or c["http"] == 200:
                seen.setdefault((c["source"], c["url"]), []).append(c["items"])
    return {k: statistics.median([n for n in v if n] or [0]) for k, v in seen.items()}


def page_state(c, base, prev):
    """`prev`: {(source, url): items} from the previous run."""
    k = (c["source"], c["url"])
    if c["items"]:
        return "ok"
    if c["http"] in (404, 410):
        return "changed"
    if c["http"] == 200:
        if base.get(k, 0) < BROKEN_MIN:
            return "quiet"
        return "changed" if prev.get(k) == 0 else "missed"
    return "blocked"


def _up(cov):
    return {c["source"] for c in cov if c["items"]}


def assess(date, coverage, checks=None):
    """`checks`: {source: {"tried", "verified"}} product-page stock checks; all failing means the parser broke."""
    hist = history(date)
    base = baselines(hist)
    prev = {(c["source"], c["url"]): c["items"] for c in hist[0][1]} if hist else {}
    per = {}
    for c in coverage:
        s = per.setdefault(c["source"], {"pages": 0, "ok": 0, "items": 0, "states": [], "http": set()})
        st = page_state(c, base, prev)
        s["pages"] += 1
        s["ok"] += st == "ok"
        s["items"] += c["items"]
        s["states"].append(st)
        s["http"].add(c["http"])
        c["state"] = st
    sources = {}
    for src, s in per.items():
        spec = SOURCES.get(src, {})
        if spec.get("expected_blocked"):
            status = "expected"
        elif not s["ok"]:
            status = "down"
        elif s["ok"] < s["pages"] - s["states"].count("quiet"):
            status = "partial"
        else:
            status = "ok"
        days = 0
        if status == "down":
            days = 1
            for _, cov in hist:
                if src in _up(cov) or not any(c["source"] == src for c in cov):
                    break
                days += 1
        why = ("site changed" if "changed" in s["states"] else
               "blocked" if "blocked" in s["states"] else "returned nothing" if "missed" in s["states"] else "no items")
        sources[src] = {"status": status, "pages": s["pages"], "pages_ok": s["ok"], "items": s["items"],
                        "days_down": days, "why": why if status in ("down", "partial") else "",
                        "verified": spec.get("stock") == "verified", "changed_pages": s["states"].count("changed")}
    up = [s for s, v in sources.items() if v["status"] in ("ok", "partial")]
    counted = [s for s, v in sources.items() if v["status"] != "expected"]
    down = [s for s in counted if sources[s]["status"] == "down"]
    changed = [s for s in counted if sources[s]["changed_pages"]]
    verified_down = [s for s in down if sources[s]["verified"]]
    prev_up = _up(hist[0][1]) if hist else set()
    reasons = []
    if verified_down:
        reasons.append("stock-verified source down")
    if changed:
        reasons.append("site change needs a scraper fix")
    failing = [s for s, c in (checks or {}).items() if c["tried"] >= 3 and not c["verified"]]
    if failing:
        reasons.append("product-page stock check failing")
    if len(up) < CFG["min_sources_ok"]:
        reasons.append(f"only {len(up)} of {len(counted)} sources up (minimum {CFG['min_sources_ok']})")
    parts = []
    for s in sorted(set(down) | set(changed), key=lambda s: (s not in down, -sources[s]["days_down"])):
        v = sources[s]
        if s in down:
            d = v["days_down"]
            parts.append(f"{label(s)} down {'today' if d == 1 else f'{d} days'} ({v['why']})")
        else:
            parts.append(f"{label(s)}: {v['changed_pages']} page(s) look changed")
    parts += [f"{label(s)} stock check failing (0/{checks[s]['tried']} product pages)" for s in failing]
    return {
        "sources": sources, "up": len(up), "counted": len(counted),
        "down": down, "newly_down": [s for s in down if s in prev_up], "changed": changed, "checks_failing": failing,
        "degraded": bool(reasons), "reasons": reasons,
        "msg": "; ".join(parts) if parts else "all sources up",
    }

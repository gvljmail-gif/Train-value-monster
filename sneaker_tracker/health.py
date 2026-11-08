"""Source health from today's coverage plus the dated snapshots in data/.

Each page gets a state:
  ok       returned items
  quiet    HTTP 200, no items, and it normally returns few or none (e.g. a 'killshot' search)
  missed   HTTP 200, no items, on a page that normally has >= BROKEN_MIN (or has no history yet, e.g. a renamed
           URL), for the first run: usually a slow load; not alarming on its own. Also a page the scraper
           marked `unreadable` (loaded, but nothing it could parse) the first time.
  blocked  403/429/timeout: bot protection or rate limiting (often transient)
  changed  404/410, or 'missed' (or unreadable) two runs in a row: the site moved or its markup changed, so the scraper
           needs fixing (never self-heals)
A row marked `short` (results cut off mid-way, e.g. a later Shopify page 403'd) makes its source 'partial'.
Each source is up (some page ok), down (none), or expected (config `expected_blocked`, e.g. Schuh).
A problem is a stock-verified source down, a page that looks changed, a retailer's product-page stock check
failing on every item, or fewer than `min_sources_ok` sources up. Problems are always shown on the page, but the
run is `degraded` (the health push) only for a problem not already alerted in the last `alert_repeat_days`
(each snapshot records the problem keys it alerted in `alerts`): once when it starts, then weekly while it lasts.
"""
import datetime
import functools
import json
import statistics

from .rules import CFG, ROOT, SOURCES, label

HISTORY_DAYS = 60
BROKEN_MIN = 5  # median items on good days at or above which an empty 200 means "changed", not "quiet"


@functools.lru_cache(maxsize=4)
def _snapshots(before):
    """(date, coverage, alerts) of up to HISTORY_DAYS snapshots dated before `before`, newest first."""
    files = sorted((p for p in (ROOT / "data").glob("20*.json") if p.stem < before), reverse=True)[:HISTORY_DAYS]
    out = []
    for p in files:
        snap = json.loads(p.read_text())
        out.append((p.stem, snap["coverage"], snap.get("alerts", [])))
    return tuple(out)


def history(before):
    """Coverage lists of up to HISTORY_DAYS snapshots dated before `before`, newest first."""
    return [(d, cov) for d, cov, _ in _snapshots(before)]


def recent_alerts(before, days):
    """Problem keys already alerted in the `days` days before `before` (from each snapshot's `alerts`)."""
    start = datetime.date.fromisoformat(before) - datetime.timedelta(days=days)
    return {k for d, _, alerts in _snapshots(before) if datetime.date.fromisoformat(d) > start for k in alerts}


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
        if c.get("unreadable"):  # loaded, but no data the parser recognises: changed if it was empty last run too
            return "changed" if prev.get(k) == 0 else "missed"
        if k not in base:  # a page with no history (new or renamed URL): flag it rather than assume it's quiet
            return "missed"
        if base[k] < BROKEN_MIN:
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
        s = per.setdefault(c["source"], {"pages": 0, "ok": 0, "items": 0, "states": [], "http": set(), "short": 0})
        st = page_state(c, base, prev)
        s["short"] += bool(c.get("short"))
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
        elif s["ok"] < s["pages"] - s["states"].count("quiet") or s["short"]:
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
               "blocked" if "blocked" in s["states"] else "returned nothing" if "missed" in s["states"] else
               "results cut off" if s["short"] else "no items")
        sources[src] = {"status": status, "pages": s["pages"], "pages_ok": s["ok"], "items": s["items"],
                        "days_down": days, "why": why if status in ("down", "partial") else "",
                        "verified": spec.get("stock") == "verified", "changed_pages": s["states"].count("changed")}
    up = [s for s, v in sources.items() if v["status"] in ("ok", "partial")]
    counted = [s for s, v in sources.items() if v["status"] != "expected"]
    down = [s for s in counted if sources[s]["status"] == "down"]
    changed = [s for s in counted if sources[s]["changed_pages"]]
    verified_down = [s for s in down if sources[s]["verified"]]
    prev_up = _up(hist[0][1]) if hist else set()
    failing = [s for s, c in (checks or {}).items() if c["tried"] >= 3 and not c["verified"]]
    problems = []  # (alert key, reason, text): anything here is shown on the page every run
    def down_text(s):
        d = sources[s]["days_down"]
        return f"{label(s)} down {'today' if d == 1 else f'{d} days'} ({sources[s]['why']})"

    for s in verified_down:
        problems.append((f"down:{s}", "stock-verified source down", down_text(s)))
    for s in changed:
        problems.append((f"changed:{s}", "site change needs a scraper fix",
                         f"{label(s)}: {sources[s]['changed_pages']} page(s) look changed"))
    for s in failing:
        problems.append((f"checks:{s}", "product-page stock check failing",
                         f"{label(s)} stock check failing (0/{checks[s]['tried']} product pages)"))
    if len(up) < CFG["min_sources_ok"]:
        problems.append(("few-sources", f"only {len(up)} of {len(counted)} sources up (minimum {CFG['min_sources_ok']})",
                         f"only {len(up)} of {len(counted)} sources up"))
    # alert once, then again only every alert_repeat_days while it persists (size?/Footpatrol flap for days)
    seen = recent_alerts(date, CFG.get("alert_repeat_days", 7))
    fresh = [p for p in problems if p[0] not in seen]
    ongoing = [p for p in problems if p[0] in seen]
    other_down = [down_text(s) for s in down if s not in verified_down]  # e.g. Vinted: shown, never alerted
    parts = [p[2] for p in fresh] + [p[2] for p in ongoing] + other_down
    msg = "; ".join(p[2] for p in fresh) or "; ".join(parts)
    if fresh and (ongoing or other_down):
        msg += " (also ongoing: " + "; ".join([p[2] for p in ongoing] + other_down) + ")"
    return {
        "sources": sources, "up": len(up), "counted": len(counted),
        "down": down, "newly_down": [s for s in down if s in prev_up], "changed": changed, "checks_failing": failing,
        "degraded": bool(fresh), "alerts": [p[0] for p in fresh],
        "issues": bool(problems), "reasons": list(dict.fromkeys(p[1] for p in problems)),
        "msg": msg if parts else "all sources up",
    }

"""Shared browser helpers. Uses the preinstalled Chromium (no download)."""
import asyncio
import glob
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@asynccontextmanager
async def browser_context():
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        ctx = await b.new_context(locale="en-GB", user_agent=UA)
        try:
            yield ctx
        finally:
            await b.close()


_SEM = None


def sem():
    """Process-wide cap on simultaneously open pages (keeps memory and bot-detection risk down)."""
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(6)
    return _SEM


async def fetch_html(ctx, url, wait_ms=2500):
    """Return (status, html). Never raises: failures come back as (None, '')."""
    async with sem():
        return await _fetch_html(ctx, url, wait_ms)


async def _fetch_html(ctx, url, wait_ms):
    page = await ctx.new_page()
    try:
        r = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(wait_ms)
        return (r.status if r else None), await page.content()
    except Exception:
        return None, ""
    finally:
        await page.close()


import re

LINES = [  # first match wins; order matters (priority Air Max first)
    ("Air Max 90/95/97", re.compile(r"air\s*max\s*(90|95|97)\b", re.I)),
    ("Air Max", re.compile(r"air\s*max", re.I)),
    ("Air Jordan 2", re.compile(r"(air\s*)?jordan\s*(air\s*)?2(?![\d.])|aj\s*2(?![\d.])", re.I)),
    ("Jordan", re.compile(r"jordan", re.I)),
    ("Air Force 1", re.compile(r"air\s*force\s*1|\baf1\b", re.I)),
    ("Dunk", re.compile(r"dunk", re.I)),
    ("Killshot", re.compile(r"killshot", re.I)),
    ("Onitsuka Tiger", re.compile(r"onitsuka|mexico\s*66|moage|tokuten|edr\s*78|colorado\s*(eighty|85)", re.I)),
]


def classify(name):
    for label, rx in LINES:
        if rx.search(name):
            return label
    return None


def pct(rrp, price):
    return round((1 - price / rrp) * 100) if rrp and price and rrp > price else 0


def num(s):
    m = re.search(r"(\d[\d,]*\.?\d*)", (s or "").replace("£", ""))
    return float(m.group(1).replace(",", "")) if m else None


_NOT_ADULT = re.compile(r"hair band|women|wmns|\bgirls?\b|\bboys?\b|kids?\b|child|baby|babies|junior|grade school|preschool|toddler|infant|\bGS\b|\bPS\b|\bTD\b|\(W\)", re.I)


def adult_mens(name):
    """Drop women's/kids' items; the target size (UK 8.5/9) is a men's size."""
    return not _NOT_ADULT.search(name or "")


async def capture_json(ctx, url, match, wait_ms=7000):
    """Load a page and return (status, [json bodies]) for XHR responses whose URL satisfies match(url)."""
    async with sem():
        return await _capture_json(ctx, url, match, wait_ms)


async def _capture_json(ctx, url, match, wait_ms):
    page, bodies = await ctx.new_page(), []

    async def on(r):
        try:
            if match(r.url) and r.status == 200:
                bodies.append(await r.text())
        except Exception:
            pass

    page.on("response", lambda r: asyncio.ensure_future(on(r)))
    try:
        r = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(wait_ms)
        return (r.status if r else None), bodies
    except Exception:
        return None, bodies
    finally:
        await page.close()

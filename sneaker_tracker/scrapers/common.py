"""Shared browser helpers. Uses the preinstalled Chromium (no download)."""
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


async def fetch_html(ctx, url, wait_ms=2500):
    """Return (status, html). Never raises: failures come back as (None, '')."""
    page = await ctx.new_page()
    try:
        r = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(wait_ms)
        return (r.status if r else None), await page.content()
    except Exception:
        return None, ""
    finally:
        await page.close()

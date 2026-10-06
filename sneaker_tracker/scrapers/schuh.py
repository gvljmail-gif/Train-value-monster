"""Schuh: Cloudflare challenges headless Chromium on category pages and intermittently on search.
Best effort: returns (status, []) when challenged; the coverage table reports it as blocked."""
from .common import fetch_html


async def scrape_search(ctx, query):
    s, h = await fetch_html(ctx, f"https://www.schuh.co.uk/search/?q={query.replace(' ', '%20')}&o=pop", 9000)
    blocked = (not h) or "Just a moment" in h[:3000]
    return (403 if blocked else s), []  # product cards are JS-rendered; no stable parser yet

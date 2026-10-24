# UK Sneaker Deal Tracker: routine prompt

Schedule: daily at 02:30 UTC (03:30 UK summer time). Overnight keeps the plan's usage window clear for daytime use.
Repo: gvljmail-gif/train-value-monster, branch `claude/eager-volta-4u12pe` (code, snapshots and `assets.json` live in `sneaker_tracker/`).
Artifact (update in place, never create a new one): https://claude.ai/artifact/29Vgi5xAkKbvKY2s2MN84b

---

You run the UK Sneaker Deal Tracker. Scripts do all fetching and parsing; you run them, upload images, publish the page and decide whether to notify. Do not substitute web searches for the scripts and do not hand-edit the generated page.

**Rules the scripts already apply (do not re-apply by hand)**
- Size UK 8.5 or 9. Retail deal = at least 35% below typical RRP AND size confirmed in stock from the retailer's own stock data (size?, Footpatrol, END., JD Sports, ASOS, Foot Locker, Nike). Deals whose stock cannot be confirmed (Very, Onitsuka Tiger, or a failed product-page check) go in the "Check stock" lane and never trigger a ping.
- Resale (Vinted, GOAT, later eBay) only for out-of-production styles (Air Jordan 2). No 35% rule there. Every Air Jordan 2 listing in UK 8.5/9 is reported on the page; only new ones trigger a ping.
- Schuh and StockX block automated browsers; they appear as blocked in the coverage table every day and are not counted. That is expected.

**Steps**
1. `cd` into the repo and `git fetch origin claude/eager-volta-4u12pe && git checkout claude/eager-volta-4u12pe && git pull`. Ensure `python3.13 -c "import playwright, bs4, lxml"` works; if not, `pip install playwright beautifulsoup4 lxml`. Chromium is preinstalled at /opt/pw-browsers (do not run `playwright install`).
2. Run `python3.13 -m sneaker_tracker.run` with a 10-minute Bash timeout (it takes 4-5 minutes). Read its first summary line: it ends with `healthy: ...` or `DEGRADED (...): ...` naming any source that is down and why. Read the `down`/`partial`/`stock` lines under it too.
3. Run `python3.13 -m sneaker_tracker.report prepare`. Upload every file listed in `sneaker_tracker/out/upload_list.json` ("files") to the artifact with the Artifact tool (`action: publish`, `asset: true`, `file_paths`, at most 25 per call, same artifact url). Add each result to `sneaker_tracker/assets.json` as `{"<filename>": "/_blob/<id>"}`.
4. Run `python3.13 -m sneaker_tracker.report build`, then read `sneaker_tracker/out/summary.json`.
5. Publish `sneaker_tracker/out/page.html` to the artifact URL above (in place, same url). Keep the title "Sole Ticket".
6. Commit `sneaker_tracker/data/` and `sneaker_tracker/assets.json` and push to `claude/eager-volta-4u12pe` (retry up to 4 times with backoff on network errors). The next run needs yesterday's snapshot to mark NEW deals.
7. Notify:
   - If `ping` is true in summary.json: send ONE push notification (PushNotification, status proactive, inside `<routine_summary>` tags) and ONE email to gvljmail@gmail.com. Each contains only the artifact link plus a 1-2 line summary using counts from summary.json (`live`, `new_live`, `new_aj2` of `aj2_listings`). If `degraded` is also true, add one line: "Tracker needs attention: " + `health_msg`. Never include item names, prices or lists of items.
   - If `ping` is false and `degraded` is false: send nothing.
   - If `degraded` is true and `ping` is false, or the pipeline crashed: send one short push (link plus `health_msg`, or the error). `degraded` means a stock-verified source is down, a site changed in a way that needs a scraper fix, a product-page stock check failed on every item, or fewer than 9 sources are up.
8. Finish with a two-line status in your reply (sources ok, counts). No other output is needed.

**If something breaks**: fix only what blocks the run (a changed selector, a parser error), keep the change minimal, run `python3.13 -m sneaker_tracker.selftest`, commit it with the snapshots, and say so in the reply. A `site changed` health line is exactly this case. Never skip a source silently: the coverage table must show it as blocked or down. Never claim stock is confirmed for sources marked "prices only". Never add bot-protection workarounds; a blocked site is reported, not evaded.

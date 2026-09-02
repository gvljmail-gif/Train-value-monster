# Train Value Monster — GWR Rewards journey-alert helper

A small toolkit to make GWR ("Great Western Railway") loyalty **reward journeys**
easy to use well: it explains how the scheme actually works, tracks a shortlist
of candidate trips (starting from Reading), and computes exactly *when* to go
book each one so you don't miss the best-value window — plus a scheduled
reminder so you get pinged at the right moment instead of having to remember.

## Why this exists

GWR Rewards gives you a **free reward journey** (Standard or First class,
depending on tier), redeemed as a promo code against **Advance Single**
fares. That's the part that makes it confusing:

- Advance fares are **dynamically priced** and released in **limited
  allocation** — cheap price bands have very few seats, and prices generally
  rise as the travel date approaches or as the cheap allocation sells out.
- Because the reward is free regardless of what the underlying fare would
  have cost you, **the value you extract = the price of the fare you'd
  otherwise have paid.** A short hop and a 4-hour intercity trip cost GWR
  the same "one reward," but are worth wildly different amounts to you.
- Advance tickets go on sale **up to 24 weeks before travel for weekday
  journeys, 12 weeks before travel for weekend journeys** — and not sooner.
  Trying to redeem before that window opens simply won't work, because
  there's no Advance fare to apply the code to yet.

So the strategy is: **pick the highest-value route/class you can realistically
travel, then be ready to book the moment its booking window opens** — not
before (nothing to book) and ideally not much after (the best-value seats/
price bands in that Advance allocation are the ones GWR releases first, and
they thin out or reprice upward over time).

> **A limitation, up front:** this tool cannot watch gwr.com or your GWR
> Rewards account for you — this project intentionally does not scrape or
> log in to gwr.com. What it *can* do reliably is the **calendar math** (when
> does a given trip's booking window open, given GWR's published windows)
> and **rank your candidate trips by likely value**, then remind you to go
> check/book at exactly the right moment. The actual price-check and click
> is still a manual step on gwr.com or the GWR app.

## How GWR Rewards actually works (researched summary)

Sourced from GWR's own site plus public write-ups (RailUK Forums,
Head for Points) — worth a quick sanity check against your own account,
since the scheme has been rolling out through 2025/2026 and specifics can
shift. See citations at the bottom.

**Tiers** (points from £30+ ticket spend via gwr.com/app, resets yearly on
your enrolment anniversary):
- **Bronze** (everyone, on signup): 40% off your next return, valid 90 days.
- **Silver** (50 points): a free **Standard class return**, valid 365 days
  from activation, + one-time First lounge access.
- **Gold** (120 points, capped): a free **First class return**, unlimited
  lounge access, 20% off food/drink.

If you're holding one reward of each class, you're most likely Gold (which
carries both the Silver-tier Standard reward you picked up on the way, and
the Gold-tier First reward) — worth confirming in *My Account → Rewards* on
gwr.com, since exact expiry dates and terms live there, not here.

**Redemption mechanics:**
- The reward is a **promo code**, entered *before* you search for a journey
  (the "have a promo code" link under passenger numbers on gwr.com's
  homepage) — not applied at checkout.
- It's redeemed as **two Advance Singles** (one each way) rather than a
  single "return" product.
- Advance Singles are tied to a specific train/date — no changing without a
  fee, so pick real dates you can commit to.
- **Both singles (outbound + return) must be booked together in one gwr.com
  session** — the code+PIN is consumed across that single booking, not
  reusable across two separate transactions. Confirmed via GWR support and
  forum reports for the Silver/Gold free-return rewards specifically. This
  matters a lot in practice: you can't lock in an easy outbound leg early
  and defer the harder return leg — you have to know (and book) both before
  you start, which for an event-day trip means waiting until the real
  post-event train times are published.

**Booking windows (the part that matters for timing):**
- Weekday travel: Advance fares open **up to 24 weeks** before travel.
- Weekend travel: Advance fares open **up to 12 weeks** before travel.
- These are GWR's stated *outer* limits — some routes/trains release later
  in practice, and cheap-band allocation can be as few as ~2 seats per
  train, so "the window opened" doesn't guarantee the best price is still
  there by the time you look. Booking on or near the opening date maximizes
  your shot at the best available fare in that class.

Sources:
[RailUK Forums – GWR Rewards](https://www.railforums.co.uk/threads/gwr-rewards.284091/) ·
[Head for Points – GWR Rewards](https://www.headforpoints.com/2025/04/23/gwr-rewards/) ·
[RailUK Forums – GWR Advance dynamic pricing](https://www.railforums.co.uk/threads/gwr-advance-tickets-dynamic-pricing.286248/) ·
[GWR – Advance tickets](https://www.gwr.com/your-tickets/choosing-your-ticket/advance-tickets)

## What's in here

- `gwr_rewards/routes.yaml` — your candidate trips (all starting from
  Reading, per your preferences: Cardiff for rugby, Bath, Exeter,
  Devon/Cornwall), each with a rough estimated fare range and day-type.
- `gwr_rewards/calculator.py` — computes each trip's booking-window-open
  date, days remaining, and ranks trips by estimated value per class.
- `gwr_rewards/rewards.yaml` — **fill this in**: your two rewards' class,
  activation/expiry dates, and status. This drives which trips are even
  eligible in time.

## Usage

```bash
cd gwr_rewards
python3 calculator.py                 # full table, soonest window first
python3 calculator.py --class first   # only First-class-reward candidates
python3 calculator.py --upcoming 30   # only windows opening in the next 30 days
```

## Reminders

Once `rewards.yaml` has real expiry dates, ask Claude to set up a scheduled
push-notification reminder (a Routine) for each trip's booking-window-open
date — and, for the Cardiff rugby fixtures especially, a reminder a few
days *before* the window opens too, since match-day Advance allocation is
expected to be highly contested.

#!/usr/bin/env python3
"""
GWR Rewards journey-value calculator.

Reads routes.yaml (candidate trips) and rewards.yaml (your actual reward
balance/expiry), computes when each trip's Advance booking window opens
per GWR's published rules, and ranks trips by estimated value so you know
where to spend each reward.

This does NOT fetch live fares or check gwr.com — it only does the
calendar math and ranks by the researched fare estimates in routes.yaml.
Always verify the real price on gwr.com when the window opens.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# GWR's published outer limits for when Advance fares go on sale.
WEEKDAY_WINDOW_DAYS = 24 * 7  # 168 days
WEEKEND_WINDOW_DAYS = 12 * 7  # 84 days


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def booking_window_opens(travel_date: dt.date, day_type: str) -> dt.date:
    window_days = WEEKEND_WINDOW_DAYS if day_type == "weekend" else WEEKDAY_WINDOW_DAYS
    return travel_date - dt.timedelta(days=window_days)


def load_reward_expiries(rewards: list[dict]) -> dict[str, dt.date | None]:
    """Map reward class -> expiry date (None if unknown/unset)."""
    expiries: dict[str, dt.date | None] = {}
    for r in rewards:
        exp = r.get("expiry_date")
        expiries[r["class"]] = parse_date(exp) if exp else None
    return expiries


def eligible_classes(trip_class: str) -> list[str]:
    if trip_class == "either":
        return ["standard", "first"]
    return [trip_class]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--class", dest="cls", choices=["standard", "first"],
                     help="Only show trips eligible for this reward class.")
    ap.add_argument("--upcoming", type=int, default=None,
                     help="Only show trips whose booking window opens within N days.")
    ap.add_argument("--routes", default=str(HERE / "routes.yaml"))
    ap.add_argument("--rewards", default=str(HERE / "rewards.yaml"))
    args = ap.parse_args()

    routes_data = load_yaml(Path(args.routes))
    rewards_data = load_yaml(Path(args.rewards))
    expiries = load_reward_expiries(rewards_data.get("rewards", []))

    today = dt.date.today()
    rows = []
    for trip in routes_data.get("trips", []):
        travel_date = parse_date(trip["travel_date"])
        opens = booking_window_opens(travel_date, trip["day_type"])
        days_until_open = (opens - today).days
        avg_fare = (trip["fare_low_gbp"] + trip["fare_high_gbp"]) / 2

        for cls in eligible_classes(trip["class"]):
            if args.cls and cls != args.cls:
                continue
            expiry = expiries.get(cls)
            expired_warning = ""
            if expiry and travel_date > expiry:
                expired_warning = f"  [WARNING: travel date is after your {cls} reward expires {expiry}]"
            elif expiry is None:
                expired_warning = f"  [reward expiry unknown — set it in rewards.yaml]"

            rows.append({
                "trip": trip["name"],
                "class": cls,
                "travel_date": travel_date,
                "day_type": trip["day_type"],
                "opens": opens,
                "days_until_open": days_until_open,
                "avg_fare": avg_fare,
                "fare_range": f"£{trip['fare_low_gbp']}-{trip['fare_high_gbp']}",
                "notes": trip.get("notes", "").strip(),
                "warning": expired_warning,
                "confirmed": trip.get("confirmed", True),
                "recommended_for": trip.get("recommended_for"),
            })

    if args.upcoming is not None:
        rows = [r for r in rows if 0 <= r["days_until_open"] <= args.upcoming]

    # Soonest booking window first; ties broken by highest estimated value.
    rows.sort(key=lambda r: (r["days_until_open"], -r["avg_fare"]))

    if not rows:
        print("No trips match the given filters.")
        return 0

    print(f"{'Trip':45} {'Class':8} {'Travel':10} {'Opens':10} {'In (d)':7} {'Est value':10}")
    print("-" * 100)
    for r in rows:
        status = "OPEN NOW" if r["days_until_open"] <= 0 else str(r["days_until_open"])
        placeholder = "" if r["confirmed"] else "  [placeholder date — not a real plan yet]"
        print(f"{r['trip'][:45]:45} {r['class']:8} {str(r['travel_date']):10} "
              f"{str(r['opens']):10} {status:7} {r['fare_range']:10}{r['warning']}{placeholder}")

    print()
    print("Recommended allocation (explicit picks in routes.yaml, factoring expiry margin —")
    print("not just raw fare — see notes per trip):")
    any_recommended = False
    for cls in ("standard", "first"):
        picks = [r for r in rows if r["class"] == cls and r["recommended_for"] == cls]
        if not picks:
            continue
        any_recommended = True
        for r in picks:
            print(f"  {cls:8} -> {r['trip']} ({r['fare_range']}, "
                  f"window opens {r['opens']}, travel {r['travel_date']})")
    if not any_recommended:
        print("  (none marked yet — set recommended_for on a trip in routes.yaml)")

    print()
    print("For reference, highest estimated fare among CONFIRMED trips (ignores expiry margin):")
    for cls in ("standard", "first"):
        candidates = [r for r in rows if r["class"] == cls and r["confirmed"]]
        if not candidates:
            print(f"  {cls:8} -> no confirmed trips yet — see placeholder rows above")
            continue
        best = max(candidates, key=lambda r: r["avg_fare"])
        print(f"  {cls:8} -> {best['trip']} ({best['fare_range']}, "
              f"window opens {best['opens']}, travel {best['travel_date']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
monthly_sold_refresh.py — monthly incremental refresh of core-suburb SOLD data
==============================================================================
Runs in the last week of each month (cron). Purpose: keep a RELIABLE, enumerable,
quarter-bucketable HOUSE sales-volume sample for the market-intelligence pages and
articles — because PropRadar only gives a single trailing-12mo aggregate (no series)
and our nightly orchestrator under-captured sold listings over the last 6 months.

Pipeline (each phase independently skippable):
  1. SCRAPE   — Domain sold-listings (houses, include price-withheld) for the core
                suburbs, back to the last successful run (12mo on first run). Marks
                listing_status=sold in the Gold_Coast per-suburb collections.
                (scrape_recent_sold.RecentSoldScraper, house_only=True)
  2. RECONCILE— count our fresh trailing-12mo HOUSE sold total per suburb, compare to
                the PropRadar aggregate (propradar_suburb_stats.house_sales_12mo) and
                the prior stored count. Writes a history row to
                system_monitor.sold_volume_reconciliation (this is also the running
                "capture-rate stability" record).
  3. TIMELINES— pull Domain property-profile timelines for the newly-sold houses
                (DOM, leased events, days-to-sell, deep history) into
                scraped_data.property_timeline. (refresh_property_timelines)
  4. HYGIENE  — correct lease-as-sale / sold_date drift using the fresh timelines
                (reconcile_sold_against_timeline --apply). Non-fatal.

Self-reports to system_monitor.job_runs via job_run() → renders automatically on the
Fields Systems Health sheet (Process Registry). CLAUDE.md Rule 7.

Usage:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    python3 scripts/monthly_sold_refresh.py                 # auto window, all phases
    python3 scripts/monthly_sold_refresh.py --skip-timelines --skip-hygiene   # fast scrape+reconcile
    python3 scripts/monthly_sold_refresh.py --window-days 365 --max-pages 40   # explicit 12mo backfill
    python3 scripts/monthly_sold_refresh.py --dry-run
"""
import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta, timezone

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _ROOT)

from pymongo import MongoClient  # noqa: E402
from job_status import job_run  # noqa: E402
from scrape_recent_sold import RecentSoldScraper  # noqa: E402
from refresh_property_timelines import refresh_suburb  # noqa: E402

JOB = "monthly_sold_refresh"
CADENCE_HOURS = 24 * 31  # monthly (STALE on the health sheet after ~46 days)

# Core market — the three target suburbs (scraper record format).
CORE = [
    {"name": "Robina", "postcode": "4226", "collection": "robina"},
    {"name": "Varsity Lakes", "postcode": "4227", "collection": "varsity_lakes"},
    {"name": "Burleigh Waters", "postcode": "4220", "collection": "burleigh_waters"},
]

HOUSE_Q = {"$regex": "^house$", "$options": "i"}


def _client() -> MongoClient:
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("ERROR: COSMOS_CONNECTION_STRING not set", file=sys.stderr)
        sys.exit(1)
    return MongoClient(conn)


def compute_window_days(sm, override=None):
    """Days to scrape back to. First run → 365 (12mo backfill). Otherwise since the
    last successful reconciliation + a 10-day overlap buffer (settlement/scrape lag)."""
    if override:
        return int(override), f"explicit --window-days {override}"
    last = sm["sold_volume_reconciliation"].find_one(sort=[("run_at", -1)])
    if not last or not last.get("run_at"):
        return 365, "first run — 12-month backfill"
    run_at = last["run_at"]
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - run_at).days + 10
    days = min(max(days, 35), 400)
    return days, f"incremental since {run_at.date()} (+10d overlap buffer)"


def count_house_sold_12mo(gc_db, collection):
    """Distinct houses in this collection with a sold_date inside the trailing 12 months."""
    cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    return gc_db[collection].count_documents({
        "listing_status": "sold",
        "property_type": HOUSE_Q,
        "sold_date": {"$gte": cutoff},
    })


def phase_scrape(window_days, max_pages, dry_run, verbose):
    scraper = RecentSoldScraper(dry_run=dry_run, verbose=verbose,
                                max_pages=max_pages, house_only=True)
    stats = scraper.run(CORE, window_days)
    try:
        scraper.mongo_client.close()
    except Exception:
        pass
    return stats


def phase_reconcile(sm, gc_db, window_days, window_desc, dry_run):
    """Count fresh house volume per suburb, compare to PropRadar, persist a history row."""
    # propradar_suburb_stats lives in the Gold_Coast DB (not system_monitor)
    pr_stats = {d["_id"]: (d.get("market_dynamics") or {}).get("house_sales_12mo")
                for d in gc_db["propradar_suburb_stats"].find({})}
    prior = sm["sold_volume_reconciliation"].find_one(sort=[("run_at", -1)]) or {}
    prior_counts = (prior.get("suburbs") or {})

    suburbs = {}
    print("\n" + "=" * 70)
    print("  RECONCILE — fresh Domain house volume vs PropRadar aggregate")
    print("=" * 70)
    print(f"  {'suburb':16} {'ours(12mo)':>11} {'propradar':>10} {'capture':>8} {'Δ vs last':>10}")
    for s in CORE:
        coll = s["collection"]
        ours = count_house_sold_12mo(gc_db, coll)
        pr = pr_stats.get(coll)
        capture = round(ours / pr * 100, 1) if pr else None
        delta = ours - prior_counts.get(coll, {}).get("ours_12mo", ours) if prior_counts else 0
        suburbs[coll] = {"ours_12mo": ours, "propradar_12mo": pr, "capture_pct": capture}
        cap_s = f"{capture}%" if capture is not None else "n/a"
        print(f"  {coll:16} {ours:>11} {str(pr):>10} {cap_s:>8} {delta:>+10}")

    doc = {
        "run_at": datetime.now(timezone.utc),
        "window_days": window_days,
        "window_desc": window_desc,
        "suburbs": suburbs,
        "source": "monthly_sold_refresh",
    }
    if not dry_run:
        sm["sold_volume_reconciliation"].insert_one(dict(doc))
        print("  → wrote reconciliation row to system_monitor.sold_volume_reconciliation")
    else:
        print("  (dry-run — reconciliation row not written)")
    return suburbs


def phase_timelines(gc_db, window_days, limit, dry_run):
    print("\n" + "=" * 70)
    print(f"  TIMELINES — refresh property-profile timelines for houses sold in last {window_days}d")
    print("=" * 70)
    total = 0
    for s in CORE:
        updated = refresh_suburb(
            gc_db, s["collection"],
            limit=limit, dry_run=dry_run,
            sold_since_days=window_days, houses_only=True,
        )
        total += updated or 0
    return total


def phase_hygiene(dry_run):
    """Correct lease-as-sale / sold_date drift using the fresh timelines. Non-fatal."""
    print("\n" + "=" * 70)
    print("  HYGIENE — reconcile_sold_against_timeline (lease/date corrections)")
    print("=" * 70)
    corrected = 0
    for s in CORE:
        cmd = [sys.executable, os.path.join(_SCRIPTS, "reconcile_sold_against_timeline.py"),
               "--suburb", s["collection"]]
        if not dry_run:
            cmd.append("--apply")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            tail = (r.stdout or "").strip().splitlines()[-3:]
            for ln in tail:
                print("    " + ln)
        except Exception as e:  # non-fatal: hygiene must never fail the data job
            print(f"    ⚠️  hygiene skipped for {s['collection']}: {e}")
    return corrected


def main():
    ap = argparse.ArgumentParser(description="Monthly incremental refresh of core-suburb sold data")
    ap.add_argument("--window-days", type=int, help="Override scrape window (default: auto since last run)")
    ap.add_argument("--max-pages", type=int, default=40, help="Max sold-listings pages per suburb (default 40)")
    ap.add_argument("--timeline-limit", type=int, help="Cap timeline fetches per suburb (for testing)")
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-reconcile", action="store_true")
    ap.add_argument("--skip-timelines", action="store_true")
    ap.add_argument("--skip-hygiene", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="No DB writes / no reconciliation row")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    client = _client()
    sm = client["system_monitor"]
    gc_db = client["Gold_Coast"]

    with job_run(JOB, cadence_hours=CADENCE_HOURS,
                 title="Monthly Sold-Data Refresh (core suburbs)") as beat:
        window_days, window_desc = compute_window_days(sm, args.window_days)
        print(f"Window: {window_days} days — {window_desc}")

        scrape_stats = {}
        if not args.skip_scrape:
            scrape_stats = phase_scrape(window_days, args.max_pages, args.dry_run, args.verbose)

        suburbs = {}
        if not args.skip_reconcile:
            suburbs = phase_reconcile(sm, gc_db, window_days, window_desc, args.dry_run)

        timelines_updated = 0
        if not args.skip_timelines:
            timelines_updated = phase_timelines(gc_db, window_days, args.timeline_limit, args.dry_run)

        if not args.skip_hygiene:
            phase_hygiene(args.dry_run)

        # ---- health-sheet heartbeat: detail + metrics ----
        # Always report the latest reconciliation counts, even on a timeline-only run.
        latest = sm["sold_volume_reconciliation"].find_one(sort=[("run_at", -1)]) or {}
        rec = suburbs or (latest.get("suburbs") or {})
        metrics = {"window_days": window_days, "timelines_updated": timelines_updated}
        if scrape_stats:
            metrics["scraped_updated"] = scrape_stats.get("updated", 0)
            metrics["scraped_inserted"] = scrape_stats.get("inserted", 0)
        parts = []
        for coll, v in rec.items():
            metrics[f"{coll}_house_12mo"] = v.get("ours_12mo")
            metrics[f"{coll}_capture_pct"] = v.get("capture_pct")
            parts.append(f"{coll} {v.get('ours_12mo')}/{v.get('propradar_12mo')} ({v.get('capture_pct')}%)")
        beat.metrics = metrics
        beat.detail = ("volume vs PropRadar — " + "; ".join(parts)) if parts else \
                      f"timelines_updated={timelines_updated}"
        print("\n✓ monthly_sold_refresh complete — " + (beat.detail or ""))

    client.close()


if __name__ == "__main__":
    main()

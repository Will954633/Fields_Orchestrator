#!/usr/bin/env python3
"""
Withdrawn Property Detector
============================
Detects properties that have been withdrawn/delisted from Domain.com.au.

Detection method:
  - For each property with listing_status="for_sale", send a HEAD request
    to the listing URL with allow_redirects=False.
  - HTTP 200 = still active on Domain.
  - HTTP 301 redirect to /property-profile/ = listing removed (withdrawn/off-market).
  - HTTP 404 = listing no longer exists (also treat as withdrawn).

Runs after sold detection (steps 103/104) so sold properties are already
flagged and won't be checked here.

Usage:
    python3 scripts/detect_withdrawn.py                          # Target market (3 suburbs)
    python3 scripts/detect_withdrawn.py --all                    # All suburbs
    python3 scripts/detect_withdrawn.py --dry-run                # Preview only
    python3 scripts/detect_withdrawn.py --report                 # Show current withdrawn counts

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from shared.env import load_env  # type: ignore
from shared.db import get_client, get_db  # type: ignore

load_env()

try:
    from curl_cffi.requests import Session
except ImportError:
    print("ERROR: curl_cffi not installed. Install with: pip install curl_cffi")
    sys.exit(1)

try:
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False

# Bright Data Web Unlocker (bypasses Akamai on individual listing URLs)
from shared.domain_fetch import fetch_with_status as _domain_fetch_with_status

# Configuration
DATABASE_NAME = 'Gold_Coast'
TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
REQUEST_DELAY = 0.3          # seconds between requests (Web Unlocker has its own rate-limiting; was 1.5)
REQUEST_TIMEOUT = 60         # seconds per request (Web Unlocker can be slow under load; was 15)
MAX_RETRIES = 5              # retry failed requests (Bright Data unlocker ~30% min_size flakiness on Domain)
RETRY_DELAY = 3              # seconds between retries
COSMOS_RETRY_ATTEMPTS = 3    # DB write retries

# Step-level safety limits (2026-06-15): BrightData Web Unlocker is reliable but
# flaky/slow per-request on Domain. Without a ceiling, a degraded BD night made this
# step grind ~6h (retries x 60s x ~150 listings) before the orchestrator killed it.
MAX_RUNTIME_MIN = int(os.environ.get("WITHDRAWN_MAX_RUNTIME_MIN", "40"))      # global wall-clock budget
CIRCUIT_BREAKER_ERRORS = int(os.environ.get("WITHDRAWN_CIRCUIT_BREAKER", "15"))  # consecutive errors -> abort

# This step is a ROLLING sweep, not a nightly full sweep. At ~24s/listing (Web
# Unlocker round-trip) a 40-min budget covers ~35-50 of a ~200-listing book, and the
# rotation cursor (withdrawn_last_checked_at) means the rest are picked up on
# subsequent nights — full coverage lands in ~2-3 days by design. So "aborted early"
# is the NORMAL end state and alerting on it fired a warning every single night
# (2026-08-03 .. 2026-08-09 inclusive) for healthy operation.
# The thing actually worth alerting on is COVERAGE: has any live listing gone
# unchecked for longer than the rotation should take? That is the assertion this
# step owes (CLAUDE.md Rule 7b) — an outcome, not merely "nothing threw".
COVERAGE_STALE_DAYS = float(os.environ.get("WITHDRAWN_COVERAGE_STALE_DAYS", "3"))


def get_aest_now():
    """Get current time in AEST (UTC+10)."""
    return datetime.now(timezone.utc) + timedelta(hours=10)


def retry_db(fn, max_retries=COSMOS_RETRY_ATTEMPTS):
    """Retry a DB operation on Cosmos 429 errors."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err = str(e)
            if "16500" in err or "429" in err or "RequestRateTooLarge" in err:
                m = re.search(r'RetryAfterMs=(\d+)', err)
                wait = int(m.group(1)) / 1000.0 if m else (1.0 * (attempt + 1))
                time.sleep(min(wait, 5.0))
                continue
            raise
    return fn()


_TITLE_RE = re.compile(r'<title[^>]*>([^<]+)</title>', re.IGNORECASE)

# Domain listing URLs end in a numeric listing id (e.g. .../93-burleigh-street-...-2020668300).
# Used to confirm the page we landed on is still the listing we asked for — see the
# identity check in check_listing_status().
_LISTING_ID_RE = re.compile(r'-(\d{7,})/?$')


def check_listing_status(session, listing_url):
    """Check if a listing URL is still active on Domain.

    Routes through Bright Data Web Unlocker (bypasses Akamai).

    Returns:
        "active"    — listing still live on Domain
        "withdrawn" — listing removed (404, /property-profile/ redirect, or "off the market" body)
        "sold"      — Domain still serves the page but title shows "Sold ..." — step 103 should
                       have already caught this; we return "active" here to avoid stomping its work
        "error"     — fetch failed
    """
    result = _domain_fetch_with_status(listing_url, retries=MAX_RETRIES, timeout=REQUEST_TIMEOUT)
    if not result:
        return "error"

    status = result.get('status', 0)
    final_url = result.get('url', '') or ''
    body = result.get('body', '') or ''

    if status == 404:
        return "withdrawn"

    # Domain redirects withdrawn listings to /property-profile/<slug>
    if '/property-profile/' in final_url:
        return "withdrawn"

    if status != 200:
        return "error"

    # Identity check (2026-08-19). Only HOUSES get redirected to /property-profile/ when
    # withdrawn — units have no property-profile page, so Domain 301s them to the suburb
    # search page instead, or occasionally to a DIFFERENT live listing. Both land here as
    # status 200 with no withdrawn marker and were scored "active", so every withdrawn unit
    # stayed for_sale indefinitely (units are 41-58% of the live book). Anchor on the listing
    # id in the URL we requested: if the page we landed on doesn't carry it, this is no
    # longer that listing. See logs/fix-history/2026-08-19.md [WITHDRAWN-UNIT-REDIRECT-MISS].
    requested_id = _LISTING_ID_RE.search(listing_url.rstrip('/'))
    if requested_id and requested_id.group(1) not in final_url:
        return "withdrawn"

    # Re-addressed listing (2026-08-19). The id check above is necessary but not sufficient:
    # when Domain CORRECTS the address on an existing listing it keeps the id and changes
    # only the slug, so the id still matches and we scored "active". Our document then holds
    # an address that is not on the market, while a second document gets created under the
    # corrected address — one live listing counted twice, once under a phantom address.
    # Seen on 2/2 Warbler Parade -> 2/249 Christine Avenue, and 5 Peppertree Circut ->
    # 5 Peppertree Circuit (a typo fix). Compare the slug, not just the id.
    if requested_id:
        requested_slug = listing_url.rstrip('/').rsplit('/', 1)[-1].rsplit('-', 1)[0]
        final_slug = final_url.rstrip('/').rsplit('/', 1)[-1].rsplit('-', 1)[0]
        if final_slug and requested_slug and final_slug != requested_slug:
            return "withdrawn"

    # Status 200 but title may reflect terminal state. Domain serves the listing page
    # for sold properties with title "Sold <address> on <date> ...".
    title_match = _TITLE_RE.search(body)
    title = title_match.group(1).strip() if title_match else ''
    title_lower = title.lower()

    if title_lower.startswith('sold '):
        # Step 103 owns sold detection — don't touch from here
        return "active"

    # Explicit withdrawn markers in Domain copy
    body_lower = body.lower()
    if 'no longer for sale' in body_lower or 'off the market' in body_lower:
        return "withdrawn"

    return "active"


def run_withdrawn_detection(suburbs, dry_run=False):
    """Main detection loop."""
    client = get_client()
    db = get_db(DATABASE_NAME)
    client.admin.command("ping")
    print(f"  MongoDB connected — {DATABASE_NAME}")

    session = Session(impersonate="chrome120")
    print(f"  curl_cffi session ready (chrome120 impersonation)")

    now_iso = datetime.utcnow().isoformat()
    today_aest = get_aest_now().strftime("%Y-%m-%d")

    totals = {"checked": 0, "withdrawn": 0, "active": 0, "errors": 0, "skipped": 0}

    deadline = time.monotonic() + MAX_RUNTIME_MIN * 60
    consecutive_errors = 0
    aborted = None  # reason string if we stop early (deadline or circuit breaker)
    circuit_broken = False        # True only for the BrightData-degraded abort, not the budget one
    coverage_age_days = {}        # suburb -> age in days of the OLDEST rotation cursor
    never_checked = {}            # suburb -> count of live listings with no cursor at all

    # ---- Round-robin ordering across suburbs (2026-07-16) ----
    # Previously we processed suburbs strictly sequentially. Combined with the 40-min
    # runtime budget, the first suburb (robina, ~98 listings) consumed the entire window,
    # so burleigh_waters — and often varsity_lakes — were never reached. Their withdrawals
    # went undetected indefinitely (e.g. 12 Beaconsfield Drive sat as for_sale for weeks).
    # Interleaving listings round-robin spreads a tight budget evenly across every suburb.
    # ---- Persisted rotation cursor (2026-07-21) ----
    # The round-robin interleaving above only fixed cross-suburb fairness. Within
    # each suburb, the query had no sort order and nothing recorded which
    # properties were actually checked last time — so with ~235 for_sale listings
    # and a ~36/run budget, the same front-of-query subset won every single run
    # while the rest (e.g. 14 Julatten Drive, withdrawn since 2025) could go
    # unchecked indefinitely. Sorting oldest-checked-first (never-checked treated
    # as oldest of all, via the "" sentinel) guarantees full rotation over time —
    # whatever a night's budget covers, next night starts from where it left off.
    per_suburb = []          # list of (suburb, collection, [props])
    for suburb in suburbs:
        collection = db[suburb]
        props = list(retry_db(lambda collection=collection: list(collection.find(
            {"listing_status": "for_sale", "listing_url": {"$exists": True, "$ne": None}},
            {"address": 1, "listing_url": 1, "listing_status": 1, "withdrawn_last_checked_at": 1}
        ))))
        props.sort(key=lambda p: p.get("withdrawn_last_checked_at") or "")
        per_suburb.append((suburb, collection, props))
        print(f"  {suburb}: {len(props)} for_sale properties")

    # Interleave: suburb0[0], suburb1[0], suburb2[0], suburb0[1], ... so if the budget
    # runs out early, coverage is proportional across suburbs rather than front-loaded.
    worklist = []
    maxlen = max((len(p) for _, _, p in per_suburb), default=0)
    for i in range(maxlen):
        for suburb, collection, props in per_suburb:
            if i < len(props):
                worklist.append((suburb, collection, props[i]))

    per_suburb_checked = {s: 0 for s, _, _ in per_suburb}
    print(f"\n--- checking {len(worklist)} listings round-robin across {len(per_suburb)} suburb(s) ---")

    try:
        for suburb, collection, prop in worklist:
            # Global wall-clock budget — never let BrightData slowness eat the pipeline window
            if time.monotonic() > deadline:
                aborted = f"runtime budget exceeded ({MAX_RUNTIME_MIN} min)"
                break

            listing_url = prop.get("listing_url", "")
            address = prop.get("address", "unknown")

            if not listing_url or not listing_url.startswith("http"):
                totals["skipped"] += 1
                continue

            totals["checked"] += 1
            per_suburb_checked[suburb] += 1
            status = check_listing_status(session, listing_url)

            if status == "withdrawn":
                totals["withdrawn"] += 1
                print(f"  WITHDRAWN: {address}")
                if not dry_run:
                    # Fetch full doc to capture asking price before status change
                    full_doc = retry_db(lambda collection=collection, prop=prop: collection.find_one({"_id": prop["_id"]}))
                    listing_price = full_doc.get("price") if full_doc else None
                    price_history = full_doc.get("price_history", []) if full_doc else []

                    update_fields = {
                        "listing_status": "withdrawn",
                        "withdrawn_date": today_aest,
                        "withdrawn_detected_at": now_iso,
                        "detection_method": "listing_url_redirect_check",
                        "last_updated": now_iso,
                        "listing_price": listing_price,
                        "withdrawn_last_checked_at": now_iso,
                    }

                    # EDITORIAL HANDOVER (2026-08-05) — same reasoning as sold
                    # detection. A withdrawn listing is no longer on the market,
                    # so its on-market editorial ("the asking price picks the
                    # lower half") stops being true the moment it comes down.
                    # Unlike a sale there is no sold_analysis to replace it, so
                    # the page falls back to its data-driven content — and because
                    # the website's noindex gate keys off `has_ai_analysis`, these
                    # pages also stop inviting indexation, which is right: they are
                    # in no sitemap and describe a listing that no longer exists.
                    # Guarded on "published" so the dotted $set can't fabricate an
                    # ai_analysis sub-document on homes that never had one.
                    if ((full_doc or {}).get("ai_analysis") or {}).get("status") == "published":
                        update_fields["ai_analysis.status"] = "archived_on_withdrawal"
                        update_fields["ai_analysis.archived_at"] = now_iso
                        update_fields["ai_analysis.archived_reason"] = "listing withdrawn"

                    # Append final "withdrawn" entry to price_history
                    if listing_price:
                        sys.path.insert(0, '/home/fields/Fields_Orchestrator/scripts')
                        from track_price_changes import parse_price_numeric
                        price_history.append({
                            "price_text": listing_price,
                            "price_numeric": parse_price_numeric(listing_price),
                            "recorded_at": now_iso,
                            "run_id": today_aest,
                            "event": "withdrawn"
                        })
                        update_fields["price_history"] = price_history

                    retry_db(lambda collection=collection, prop=prop, update_fields=update_fields: collection.update_one(
                        {"_id": prop["_id"]},
                        {"$set": update_fields}
                    ))
                consecutive_errors = 0
            elif status == "active":
                totals["active"] += 1
                consecutive_errors = 0
                if not dry_run:
                    # Stamp so this property moves to the back of next run's
                    # rotation — without this, a confirmed-active property with
                    # an old/missing timestamp would keep winning the sort every
                    # night, starving properties that have never been checked.
                    retry_db(lambda collection=collection, prop=prop: collection.update_one(
                        {"_id": prop["_id"]},
                        {"$set": {"withdrawn_last_checked_at": now_iso}}
                    ))
            else:
                totals["errors"] += 1
                consecutive_errors += 1
                print(f"  ERROR: {address} — could not determine status")
                if not dry_run:
                    # Stamp on the error path too. Without this a listing that fails
                    # every time (dead URL, permanent 403) keeps its old/missing
                    # timestamp, wins the sort every single night, and consumes budget
                    # ahead of listings that have never been checked at all — one bad
                    # listing could starve the whole rotation indefinitely. It is
                    # retried on the next pass round, ~2-3 days later.
                    retry_db(lambda collection=collection, prop=prop: collection.update_one(
                        {"_id": prop["_id"]},
                        {"$set": {"withdrawn_last_checked_at": now_iso}}
                    ))
                # Circuit breaker — BrightData clearly degraded; stop instead of grinding for hours
                if consecutive_errors >= CIRCUIT_BREAKER_ERRORS:
                    aborted = (f"circuit breaker tripped after {consecutive_errors} consecutive "
                               f"fetch errors (BrightData Web Unlocker degraded)")
                    circuit_broken = True
                    break

            time.sleep(REQUEST_DELAY)

        # --- coverage assertion (Rule 7b) — must run before the client is closed ---
        # Oldest rotation cursor across the live book. If the sweep is keeping up this
        # is < COVERAGE_STALE_DAYS regardless of how many any single night got through.
        for suburb, collection, _props in per_suburb:
            oldest = retry_db(lambda collection=collection: list(collection.find(
                {"listing_status": "for_sale", "listing_url": {"$exists": True, "$ne": None}},
                {"withdrawn_last_checked_at": 1}
            ).sort("withdrawn_last_checked_at", 1).limit(1)))
            if not oldest:
                continue
            stamp = oldest[0].get("withdrawn_last_checked_at")
            if not stamp:
                never_checked[suburb] = retry_db(lambda collection=collection: collection.count_documents(
                    {"listing_status": "for_sale", "listing_url": {"$exists": True, "$ne": None},
                     "withdrawn_last_checked_at": {"$exists": False}}))
                continue
            try:
                # now_iso is written by datetime.utcnow() -> NAIVE, already UTC. Calling
                # .astimezone() on it would have Python assume LOCAL (AEST) and silently
                # shift it 10 hours, which is the exact off-by-ten class that produced a
                # bogus "swallowed heartbeat" diagnosis in [WTA-OPS-011]. Attach UTC
                # explicitly instead of converting.
                dt = datetime.fromisoformat(stamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                coverage_age_days[suburb] = (
                    datetime.now(timezone.utc) - dt).total_seconds() / 86400
            except Exception:
                pass

    finally:
        session.close()
        client.close()

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"  Checked:   {totals['checked']}")
    print(f"  Active:    {totals['active']}")
    print(f"  Withdrawn: {totals['withdrawn']}")
    print(f"  Errors:    {totals['errors']}")
    print(f"  Skipped:   {totals['skipped']} (no listing URL)")
    print(f"  Per-suburb checked: " + ", ".join(
        f"{s}={per_suburb_checked.get(s, 0)}/{len(p)}" for s, _, p in per_suburb))
    if aborted:
        # Report which suburbs were left short so a silent budget-abort can't rot again.
        unfinished = [f"{s} ({per_suburb_checked.get(s, 0)}/{len(p)})"
                      for s, _, p in per_suburb if per_suburb_checked.get(s, 0) < len(p)]
        print(f"  ⚠ ABORTED EARLY: {aborted}")
        print(f"     Suburbs left incomplete: {', '.join(unfinished) if unfinished else 'none'}")
        print(f"     Remaining for_sale listings left unchecked — will retry next run.")

    # --- coverage verdict: this, not the early abort, decides whether Will hears ---
    stale_cov = {s: a for s, a in coverage_age_days.items() if a > COVERAGE_STALE_DAYS}
    print(f"  Rotation coverage (oldest cursor per suburb): " + (", ".join(
        f"{s}={a:.1f}d" for s, a in sorted(coverage_age_days.items())) or "n/a"))
    if never_checked:
        print(f"  Never checked: " + ", ".join(f"{s}={n}" for s, n in never_checked.items()))

    # Machine-readable verdict for the Systems Health board's step-113 outcome check.
    # The board must judge COVERAGE, not the early abort — an abort with healthy
    # coverage is normal (see COVERAGE_STALE_DAYS above), so asserting on "aborted"
    # made the row permanently STALE for correct behaviour [WTA-OPS-020].
    if stale_cov or circuit_broken:
        print(f"  ⚠ COVERAGE BEHIND: " + (", ".join(
            f"{s}={a:.1f}d" for s, a in sorted(stale_cov.items())) or "brightdata degraded"))
    else:
        print(f"  ✅ COVERAGE OK: rolling sweep within {COVERAGE_STALE_DAYS:g}d on all suburbs")

    if not dry_run and (circuit_broken or stale_cov):
        # Alert ONLY on a genuine failure: BrightData degraded (circuit breaker), or the
        # rolling sweep has fallen behind so a live listing may have been withdrawn days
        # ago without us noticing. A plain budget abort with healthy coverage is the
        # designed steady state and is deliberately silent.
        try:
            sys.path.insert(0, '/home/fields/Fields_Orchestrator/scripts')
            from telegram_notify import send_message
            if circuit_broken:
                head = ("⚠️ Withdrawn detection (step 113): BrightData Web Unlocker degraded\n"
                        f"{aborted}")
            else:
                head = ("⚠️ Withdrawn detection (step 113): rolling sweep has fallen behind\n"
                        f"Listings unchecked for >{COVERAGE_STALE_DAYS:g}d: " + ", ".join(
                            f"{s} {a:.1f}d" for s, a in sorted(stale_cov.items())))
            send_message(
                f"{head}\n"
                f"Checked {totals['checked']}, withdrawn {totals['withdrawn']}, "
                f"errors {totals['errors']}.",
                parse_mode="")
        except Exception as e:
            print(f"     (telegram alert failed: {e})")
    if dry_run:
        print(f"  (DRY RUN — no DB changes made)")
    print(f"{'='*60}")

    return totals


def show_report():
    """Show current withdrawn property counts across all suburbs."""
    client = get_client()
    db = get_db(DATABASE_NAME)

    print(f"\n{'='*60}")
    print(f"  WITHDRAWN PROPERTIES REPORT")
    print(f"{'='*60}")

    collections = [c for c in db.list_collection_names()
                   if not c.startswith('system.') and c not in (
                       'suburb_median_prices', 'suburb_statistics',
                       'change_detection_snapshots', 'address_search_index')]
    total = 0
    for coll_name in sorted(collections):
        count = db[coll_name].count_documents({"listing_status": "withdrawn"})
        if count > 0:
            print(f"  {coll_name:30s}  {count} withdrawn")
            total += count
        time.sleep(0.3)  # gentle on Cosmos

    print(f"\n  Total withdrawn: {total}")
    print(f"{'='*60}")
    client.close()


def main():
    parser = argparse.ArgumentParser(description="Detect withdrawn/delisted properties")
    parser.add_argument('--all', action='store_true', help='Check all suburbs (not just target market)')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB changes')
    parser.add_argument('--report', action='store_true', help='Show current withdrawn counts')
    parser.add_argument('--suburbs', nargs='+', help='Specific suburb collection names')
    parser.add_argument('--no-fail', action='store_true', help='Exit 0 even on errors')
    args = parser.parse_args()

    if args.report:
        show_report()
        return

    # Monitor client for ops dashboard
    monitor = MonitorClient(
        system="orchestrator", pipeline="orchestrator_daily",
        process_id="113", process_name="Detect Withdrawn Properties"
    ) if _MONITOR_AVAILABLE else None
    if monitor:
        monitor.start()

    if args.suburbs:
        suburbs = args.suburbs
    elif args.all:
        db = get_db(DATABASE_NAME)
        suburbs = [c for c in db.list_collection_names()
                   if not c.startswith('system.') and c not in (
                       'suburb_median_prices', 'suburb_statistics',
                       'change_detection_snapshots', 'address_search_index')]
    else:
        suburbs = TARGET_SUBURBS

    print(f"\nWithdrawn Property Detector")
    print(f"  Suburbs: {len(suburbs)}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Time: {get_aest_now().strftime('%Y-%m-%d %H:%M')} AEST")

    try:
        totals = run_withdrawn_detection(suburbs, dry_run=args.dry_run)

        if monitor:
            monitor.finish(status="success")
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        if monitor:
            monitor.finish(status="error")
        if not args.no_fail:
            sys.exit(1)


if __name__ == "__main__":
    main()

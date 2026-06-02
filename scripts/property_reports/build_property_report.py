"""
build_property_report — CLI orchestrator for one or many property_reports docs.

Reads a stub `property_reports` doc (state == "stub"), calls SlotResolver,
writes back the resolved fields, transitions state to "under_review",
prepends an activity-feed item.

Usage:
    # Process one slug
    python3 -m scripts.property_reports.build_property_report --slug 13-terrace-court-merrimac

    # Process all stub docs (older than 10s, to avoid racing the submit)
    python3 -m scripts.property_reports.build_property_report --all-stubs

    # Re-resolve a non-stub doc (idempotent — doesn't change state)
    python3 -m scripts.property_reports.build_property_report --slug X --force

Exit codes:
    0 = success (one or more docs processed)
    1 = no docs found
    2 = error during processing
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Allow running as a module from any cwd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.db import get_client, get_gold_coast_db  # noqa: E402
from shared.ru_guard import cosmos_retry  # noqa: E402

from scripts.property_reports.slot_resolver import SlotResolver  # noqa: E402
from scripts.property_reports.build_events import BuildEventEmitter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("build_property_report")


def get_system_monitor_db():
    return get_client()["system_monitor"]


def resolve_one(report_doc: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    """Resolve slots for one doc. Returns the update dict that was applied."""
    slug = report_doc["slug"]
    state = report_doc.get("state", "stub")

    if state != "stub" and not force:
        logger.info(f"  {slug}: state={state}, skipping (use --force to re-resolve)")
        return {}

    gc_db = get_gold_coast_db()
    sm = get_system_monitor_db()
    coll = sm["property_reports"]

    # Reset build_events for this run so a re-resolve doesn't accumulate stale
    # events from previous attempts. Stamp the start time and live-build state
    # so the frontend can tell the difference between "not started yet" and
    # "actively building".
    now_start = datetime.utcnow()
    cosmos_retry(
        lambda: coll.update_one(
            {"slug": slug},
            {
                "$set": {
                    "build_events": [
                        {
                            "step": "address_resolved",
                            "label": "We've got your address",
                            "phase": "done",
                            "at": now_start,
                        }
                    ],
                    "build_state": "building",
                    "build_started_at": now_start,
                    "last_build_event_at": now_start,
                },
                "$unset": {"build_completed_at": ""},
            },
        ),
        label=f"property_reports.build_start.{slug}",
    )

    emitter = BuildEventEmitter(coll, slug, cosmos_retry)
    resolver = SlotResolver(report_doc, gc_db, emitter=emitter)

    updates = resolver.resolve_all()

    # Build the activity feed item for state-transition
    now = datetime.utcnow()
    n_comps = len(updates.get("slots.recent_comps", []) or [])
    best_comp = updates.get("slots.best_comp")
    comp_summary = (
        f"closest match: {best_comp['address']} (sold {best_comp['sale_date']}"
        f" for ${best_comp['sale_price']:,})"
        if best_comp and best_comp.get("sale_price")
        else "no recent close comparable yet"
    )
    activity_items = [
        {
            "date": now.strftime("%Y-%m-%d"),
            "kind": "data_resolved",
            "headline": "We pulled your property's data and the closest comparable sales.",
            "detail": (
                f"Reviewed the suburb cohort for {report_doc.get('suburb', 'your suburb')} and "
                f"selected {n_comps} recent comparable sales — {comp_summary}. "
                "A property consultant will refine these into the final valuation range."
            ),
            "source": None,
        },
    ]

    # Day 3: emit a separate comps_resolved event when the valuation engine has
    # produced per-comp adjustments (process 301 output). This is the moment
    # the seller can see line-itemised comp cards in the Valuation tab.
    engine_comps = updates.get("valuation.comps")
    if engine_comps:
        model_range = updates.get("valuation.model_range") or {}
        low, high = model_range.get("low"), model_range.get("high")
        range_str = (
            f"working range ${low:,}–${high:,}"
            if low and high
            else "working range pending"
        )
        activity_items.append({
            "date": now.strftime("%Y-%m-%d"),
            "kind": "valuation",
            "headline": f"Comparable sales computed — {len(engine_comps)} comps, {range_str}.",
            "detail": (
                f"The valuation engine selected {len(engine_comps)} recent comparable sales from "
                f"{report_doc.get('suburb', 'your suburb')} and adjusted each for land area, "
                f"floor area, bedrooms, bathrooms, condition, and time-to-today. The line-itemised "
                f"adjustments are now visible on the Valuation tab. A property consultant will review "
                f"the comp selection before the final figure is finalised."
            ),
            "source": None,
        })

    # Photos-pulled event when at least 3 photos came through
    photo_count = len((updates.get("property") or {}).get("photos") or [])
    if photo_count >= 3:
        activity_items.append({
            "date": now.strftime("%Y-%m-%d"),
            "kind": "market_state",  # reuse a registered kind; "photos" kind not in mini-site enum yet
            "headline": f"We pulled {photo_count} photos and the satellite view of your home.",
            "detail": (
                "Photos and the satellite imagery feed the visual analysis pass — what your home "
                "shows from the street, the layout the floor plan reveals, the bushland/water/road "
                "context the aerial confirms."
            ),
            "source": None,
        })

    # Transition state to under_review unless we're force-re-resolving
    if state == "stub":
        updates["state"] = "under_review"
        updates["state_transitioned_at.under_review"] = now
        updates["activity_refreshed_at"] = now

    # Push activity items using $push, not $set (preserves existing items).
    # Newest-first by reversing so the most recent event ends up at position 0.
    set_payload = {k: v for k, v in updates.items()}

    # Final build event — the house website is ready for review. This is the
    # signal the frontend polls for to auto-navigate to /your-home/<slug>.
    emitter.done(
        "analyst_handoff",
        "Sent to a property consultant for final review",
    )
    set_payload["build_state"] = "complete"
    set_payload["build_completed_at"] = now

    def _apply():
        return coll.update_one(
            {"slug": slug},
            {
                "$set": {**set_payload, "updated_at": now},
                "$push": {"activity": {"$each": list(reversed(activity_items)), "$position": 0}},
            },
        )

    cosmos_retry(_apply, label=f"property_reports.resolve.{slug}")

    # Messages tab (Phase 3.1) — rebuild the advisory timeline from the now-current
    # doc (welcome + valuation state + market-change events), preserving any human
    # notes a consultant posted. Best-effort: a failure here must not fail the build.
    try:
        from scripts.property_reports.messages import refresh_messages
        refresh_messages(slug, sm)
    except Exception as e:
        logger.warning(f"  {slug}: messages refresh failed: {e}")

    return updates


def find_stub_slugs(min_age_seconds: int = 5) -> List[str]:
    """All stub-state slugs older than min_age_seconds (avoid racing the submit)."""
    sm = get_system_monitor_db()
    coll = sm["property_reports"]
    cutoff = datetime.utcnow() - timedelta(seconds=min_age_seconds)
    return [
        d["slug"]
        for d in coll.find(
            {
                "state": "stub",
                "$or": [
                    {"state_transitioned_at.stub": {"$lte": cutoff}},
                    {"state_transitioned_at.stub": {"$exists": False}},
                    {"created_at": {"$lte": cutoff}},
                ],
            },
            {"slug": 1, "_id": 0},
        )
    ]


def fetch_one(slug: str) -> Optional[Dict[str, Any]]:
    sm = get_system_monitor_db()
    return sm["property_reports"].find_one({"slug": slug})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="Process this single slug")
    g.add_argument("--all-stubs", action="store_true", help="Process all stub docs")
    parser.add_argument("--force", action="store_true", help="Re-resolve even non-stub docs")
    parser.add_argument("--dry-run", action="store_true", help="Resolve but do not write")
    args = parser.parse_args()

    if args.slug:
        slugs = [args.slug]
    else:
        slugs = find_stub_slugs()
        logger.info(f"Found {len(slugs)} stub doc(s) to process")
        if not slugs:
            return 1

    processed = 0
    errors = 0
    for slug in slugs:
        doc = fetch_one(slug)
        if not doc:
            logger.warning(f"  {slug}: not found, skipping")
            continue
        logger.info(f"Processing {slug} (state={doc.get('state')})")
        try:
            if args.dry_run:
                gc_db = get_gold_coast_db()
                resolver = SlotResolver(doc, gc_db)
                updates = resolver.resolve_all()
                logger.info(f"  [DRY] would $set: {list(updates.keys())}")
                processed += 1
            else:
                updates = resolve_one(doc, force=args.force)
                if updates:
                    logger.info(f"  → done. Applied {len(updates)} field updates")
                    processed += 1
        except Exception as e:
            logger.exception(f"  → ERROR processing {slug}: {e}")
            errors += 1

    logger.info(f"Processed: {processed}, Errors: {errors}")
    return 0 if processed > 0 and errors == 0 else (2 if errors else 1)


if __name__ == "__main__":
    sys.exit(main())

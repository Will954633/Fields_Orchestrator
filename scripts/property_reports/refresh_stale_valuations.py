#!/usr/bin/env python3
"""
refresh_stale_valuations.py — give a report the valuation that already exists for it.

WHY
───────────────────────────────────────────────────────────────────────────────
A report is resolved once, at build time, and then only its COMPETITOR slots are
ever refreshed — `refresh_property_reports.py:1043` calls
`SlotResolver(doc, gc_db).refresh_competitor_slots()` and nothing else. So a
report built in June is frozen against June's data.

Meanwhile the valuation engine keeps working: `batch_value_offmarket.py` (cron
02:10) writes `valuation_data` onto Gold_Coast property docs, and the unit engine
writes `unit_valuations` (cron 04:30). When a property is valued AFTER its report
was built, the report never finds out.

Measured 2026-08-14: of 44 live reports showing no working range, **25 had a
usable engine range sitting on the property document** — e.g. 25-ballyliffen-
court-robina, built 14 June, valued 8 August. Not broken; stale by two months.

WHAT IT DOES
───────────────────────────────────────────────────────────────────────────────
For each non-stub report, re-runs ONLY the already-computed valuation tiers via
the resolver itself, so units and houses get the same treatment they would in a
build:

    Tier 0  attached dwelling -> unit engine (`Gold_Coast.unit_valuations`)
    Tier 1  house -> `valuation_data.confidence.range` on the property doc

⚠ DELIBERATELY DOES NOT run Tier 1b (the ~22 s on-demand engine), Tier 2
(exterior evidence) or Tier 3 (suburb median). Those SYNTHESISE a range. This
job's job is to deliver a valuation we already computed — not to manufacture one
for a report that legitimately has none. A report with nothing computed keeps
showing "Working range being prepared", which is the honest state.

    python3 -m scripts.property_reports.refresh_stale_valuations --dry-run
    python3 -m scripts.property_reports.refresh_stale_valuations --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.db import get_client                                    # noqa: E402
from scripts.property_reports.slot_resolver import SlotResolver     # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("refresh_stale_valuations")


def _subject_for(gc, rep):
    sub = (rep.get("suburb_key") or "").lower()
    if not sub:
        return None
    coll = gc[sub]
    pid = rep.get("property_id")
    if pid:
        try:
            from bson import ObjectId
            doc = coll.find_one({"_id": ObjectId(str(pid))})
            if doc:
                return doc
        except Exception:
            pass
        doc = coll.find_one({"_id": pid})
        if doc:
            return doc
    doc = coll.find_one({"url_slug": rep.get("slug")})
    if doc:
        return doc
    addr = rep.get("address")
    if addr:
        return coll.find_one({"$or": [{"address": addr}, {"complete_address": addr},
                                      {"street_address": addr}]})
    return None


def computed_range(gc, rep, subject):
    """Tier 0 / Tier 1 only — never synthesise."""
    r = SlotResolver({"suburb_key": (rep.get("suburb_key") or "").lower(),
                      "suburb": rep.get("suburb") or "",
                      "address": rep.get("address") or ""}, gc)
    r._subject = subject
    if r._is_attached_dwelling():
        return r._unit_valuation_range(), "unit_engine"
    return r._engine_valuation_range(), "engine"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--only-missing", action="store_true", default=True,
                    help="Only touch reports with no current range (default).")
    args = ap.parse_args()

    client = get_client()
    reports = client["system_monitor"].property_reports
    gc = client["Gold_Coast"]

    scanned = candidates = repaired = skipped_no_subject = skipped_nothing = 0
    retracted = 0
    for rep in reports.find({"state": {"$ne": "stub"}},
                            {"slug": 1, "address": 1, "suburb": 1, "suburb_key": 1,
                             "property_id": 1, "valuation": 1}):
        scanned += 1
        current = (rep.get("valuation") or {}).get("model_range")
        has_range = bool(current and current.get("low"))

        # ⚠ Do NOT short-circuit on --only-missing before checking for a refusal.
        # A report that already shows a figure is exactly the case that needs
        # RETRACTING when the engine has since declined the home. Skipping it is
        # why 11-orr-place and 157-christine-avenue kept July figures against
        # subjects suppressed in August. Load the subject first, decide after.
        subject = _subject_for(gc, rep)
        if not subject:
            if not (args.only_missing and has_range):
                candidates += 1
                skipped_no_subject += 1
            continue

        probe = SlotResolver({"suburb_key": (rep.get("suburb_key") or "").lower(),
                              "suburb": rep.get("suburb") or "",
                              "address": rep.get("address") or ""}, gc)
        probe._subject = subject
        probe.report = rep
        declined = (None if probe._is_attached_dwelling()
                    else probe._engine_declined())

        # Also retract a PUBLISHED point outside the envelope even when there is
        # no engine verdict to read. A home the engine never valued cannot be
        # "declined", but the fallback tier that priced it has never been
        # backtested at any band — 136-harrier-drive-burleigh-waters reached
        # $2,809,000 off 4 comps this way. Mirrors the Tier 2/3 output check in
        # SlotResolver.working_valuation_range().
        if not declined and not probe._is_attached_dwelling() and has_range:
            pt = (current or {}).get("point") or 0
            if pt and not (SlotResolver._ENVELOPE_MIN <= pt < SlotResolver._ENVELOPE_MAX):
                declined = ("above_design_ceiling"
                            if pt >= SlotResolver._ENVELOPE_MAX else "below_design_floor")

        if declined:
            if not has_range:
                continue  # already carries no figure — nothing to retract
            candidates += 1
            retracted += 1
            logger.info("%-46s RETRACT     was $%s-%s (%s)", rep["slug"][:46],
                        f"{current.get('low'):,}", f"{current.get('high'):,}", declined)
            if args.apply:
                reports.update_one(
                    {"slug": rep["slug"]},
                    {"$set": {
                        "valuation.model_range": None,
                        "valuation.no_figure": {
                            "reason": declined,
                            "dwelling_class": "house",
                            "decided_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }},
                )
            continue

        if args.only_missing and has_range:
            continue
        candidates += 1
        rng, kind = computed_range(gc, rep, subject)
        if not rng:
            skipped_nothing += 1
            continue
        repaired += 1
        logger.info("%-46s <- %-11s $%s-%s", rep["slug"][:46], kind,
                    f"{rng['low']:,}", f"{rng['high']:,}")
        if args.apply:
            reports.update_one(
                {"slug": rep["slug"]},
                {"$set": {"valuation.model_range": rng, "valuation.no_figure": None}},
            )

    logger.info("")
    logger.info("scanned=%d candidates=%d | repaired=%d retracted=%d no-subject=%d nothing-computed=%d",
                scanned, candidates, repaired, retracted, skipped_no_subject, skipped_nothing)
    if args.dry_run:
        logger.info("DRY RUN — nothing written.")

    # Rule 7b: assert an outcome. Finding no candidates at all means the query is
    # wrong, not that every report is healthy.
    if candidates == 0:
        raise RuntimeError("no reports without a working range — query is wrong, not the data")
    return 0


if __name__ == "__main__":
    sys.exit(main())

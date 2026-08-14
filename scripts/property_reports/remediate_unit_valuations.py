#!/usr/bin/env python3
"""
remediate_unit_valuations.py — remove house-comp valuations from attached-dwelling reports.

WHY
───────────────────────────────────────────────────────────────────────────────
Until 2026-08-14 `/your-home` had no dwelling-class gate. An attached dwelling
(unit, townhouse, duplex) fell through the house tiers to
`SlotResolver.valuation_model_range()`, whose query filtered on `bedrooms` and
NOT on property type — so a 3-bedroom unit was valued against 3-bedroom HOUSES.

Measured on sold stock, 3-bed house median vs 3-bed unit median, 2026-08-14:

    Robina           $1,300,000 vs $1,020,000   +27%
    Burleigh Waters  $1,475,000 vs $1,170,000   +26%
    Varsity Lakes    $1,200,000 vs   $995,000   +21%

The tell is that several unrelated units share one range — it is the suburb's
house median band, not a valuation of their home.

The resolver is fixed. This script repairs the documents already written, which
a fix alone does not touch: `build_property_report` only ever `$set`s, so a
stale range survives until something overwrites it.

WHAT IT DOES
───────────────────────────────────────────────────────────────────────────────
For every non-stub report whose address classifies as `attached`:
  1. If the unit engine has a PUBLISHABLE valuation -> write that range.
  2. Otherwise -> clear the range to None and record `valuation.no_figure`
     with the real reason.

Never widens the net to keep a number. A unit with no defensible figure shows
none — the page already supports "pending, a consultant will finalise", which is
honest, where the house-comp figure was not.

    python3 -m scripts.property_reports.remediate_unit_valuations --dry-run
    python3 -m scripts.property_reports.remediate_unit_valuations --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.db import get_client                      # noqa: E402
from shared.dwelling_type import classify_dwelling    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("remediate_unit_valuations")

# Methods that can only have come from the house tiers.
_HOUSE_TIER_METHODS = {"thin", "exterior_evidence", "engine"}


def _subject_for(gc, report):
    """Best-effort subject lookup: property_id, then url_slug, then address."""
    sub = (report.get("suburb_key") or "").lower()
    if not sub:
        return None
    coll = gc[sub]
    pid = report.get("property_id")
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
    for key in ("url_slug", "slug"):
        doc = coll.find_one({key: report.get("slug")})
        if doc:
            return doc
    addr = report.get("address")
    if addr:
        return coll.find_one({"$or": [{"address": addr}, {"complete_address": addr},
                                      {"street_address": addr}]})
    return None


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = get_client()
    reports = client["system_monitor"].property_reports
    gc = client["Gold_Coast"]
    uv = gc["unit_valuations"]

    scanned = attached = repaired = cleared = kept = 0
    for rep in reports.find({"state": {"$ne": "stub"}},
                            {"slug": 1, "address": 1, "suburb_key": 1,
                             "property_id": 1, "valuation": 1}):
        scanned += 1
        if classify_dwelling({"street_address": rep.get("address") or ""}) != "attached":
            continue
        attached += 1
        mr = (rep.get("valuation") or {}).get("model_range") or {}
        method = mr.get("method")

        subject = _subject_for(gc, rep)
        slug = (subject or {}).get("url_slug") or rep.get("slug")
        rec = uv.find_one({"_id": slug}) if slug else None

        publishable = bool(rec and rec.get("publishable") and rec.get("point")
                           and rec.get("method") != "declined")

        if publishable:
            new_range = {
                "low": int(rec["low"]), "high": int(rec["high"]), "point": int(rec["point"]),
                "method": "unit_engine", "tier": rec.get("tier"),
                "band_pct": rec.get("band_pct"), "n_comps": rec.get("n_comps"),
                "accuracy": rec.get("accuracy"),
                "adjusted_low": rec.get("adjusted_low"), "adjusted_high": rec.get("adjusted_high"),
            }
            action = "REPLACE with unit engine"
            update = {"$set": {"valuation.model_range": new_range,
                               "valuation.no_figure": None}}
            repaired += 1
        else:
            reason = ("unit_not_yet_valued" if not rec
                      else (rec.get("decline_reason") or
                            ("unit_accuracy_below_threshold" if not rec.get("publishable")
                             else "unit_declined")))
            if not mr.get("low") and method not in _HOUSE_TIER_METHODS:
                kept += 1
                continue  # already showing no figure — nothing to repair
            action = f"CLEAR ({reason})"
            update = {"$set": {
                "valuation.model_range": None,
                "valuation.no_figure": {
                    "reason": reason, "dwelling_class": "attached",
                    "decided_at": datetime.now(timezone.utc).isoformat(),
                    "remediated_from": {"method": method, "low": mr.get("low"),
                                        "high": mr.get("high")},
                },
            }}
            cleared += 1

        logger.info("%-46s %-18s -> %s", rep["slug"], method, action)
        if args.apply:
            reports.update_one({"slug": rep["slug"]}, update)

    logger.info("")
    logger.info("scanned=%d attached=%d | repaired=%d cleared=%d already-clean=%d",
                scanned, attached, repaired, cleared, kept)
    if args.dry_run:
        logger.info("DRY RUN — nothing written. Re-run with --apply.")

    # Rule 7b: this is a one-shot repair, not a scheduled job, but it must still
    # assert an outcome rather than reporting success for doing nothing.
    if attached == 0:
        raise RuntimeError("no attached-dwelling reports found — the classifier or the "
                           "query is wrong, not the data")
    return 0


if __name__ == "__main__":
    sys.exit(main())

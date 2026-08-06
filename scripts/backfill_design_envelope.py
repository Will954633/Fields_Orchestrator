#!/usr/bin/env python3
"""
backfill_design_envelope.py — apply the $1M-$2M design envelope to valuations
already stored.

WHY A BACKFILL AND NOT A RECOMPUTE (2026-08-06)
  `precompute_valuations.py` now suppresses the point estimate and the range
  outside `_ENVELOPE_MIN.._ENVELOPE_MAX`, but that only fires when a property is
  re-valued. 1,115 homes were valued minutes before the change and carry a full
  range they should not have.

  The envelope decision depends on ONE already-stored number — the reconciled
  valuation — so re-running the whole comparable pipeline would burn hours to
  reach a conclusion we can read straight off the document. This applies the
  same rule to what is already there.

  It writes exactly what the engine writes, so a later recompute is a no-op
  rather than a conflict.

    python3 scripts/backfill_design_envelope.py --dry-run
    python3 scripts/backfill_design_envelope.py
"""
import argparse
import os
import sys

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv
from src.mongo_client_factory import get_mongo_client

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv(os.path.join(ORCH, ".env"))
    # Single source of truth for the bounds — never re-declare them here.
    from precompute_valuations import _ENVELOPE_MIN, _ENVELOPE_MAX
    gc = get_mongo_client()["Gold_Coast"]
    print(f"envelope: ${_ENVELOPE_MIN:,} - ${_ENVELOPE_MAX:,}\n")

    above = below = ok = already = 0
    for s in SUBURBS:
        for d in gc[s].find(
                {"property_type": "House",
                 "valuation_data.confidence.reconciled_valuation": {"$gt": 0}},
                {"valuation_data.confidence.reconciled_valuation": 1,
                 "valuation_data.confidence.directional_only": 1}):
            conf = (d.get("valuation_data") or {}).get("confidence") or {}
            rv = conf.get("reconciled_valuation")
            if rv is None:
                continue
            if _ENVELOPE_MIN <= rv < _ENVELOPE_MAX:
                ok += 1
                continue
            if conf.get("directional_only"):
                already += 1
                continue
            reason = ("above_design_ceiling" if rv >= _ENVELOPE_MAX
                      else "below_design_floor")
            if reason == "above_design_ceiling":
                above += 1
            else:
                below += 1
            if not args.dry_run:
                gc[s].update_one({"_id": d["_id"]}, {"$set": {
                    "valuation_data.confidence.directional_only": True,
                    "valuation_data.confidence.directional_reason": reason,
                    # Both go. A flat +/-12% band around a figure we have just
                    # declared unusable looks identical to one built on solid
                    # ground, which is the whole problem.
                    "valuation_data.confidence.reconciled_valuation": None,
                    "valuation_data.confidence.range": None,
                    "valuation_data.confidence.confidence": "directional",
                    "valuation_data.summary.directional_only": True,
                }})

    # ⚠ Second pass, and the reason it exists. The scan above filters on
    # `reconciled_valuation > 0`, so it CANNOT see homes that were already
    # directional — their point estimate is already null. Those were flagged by
    # the old $2.5M listing-price guard, which deliberately KEPT the range
    # ("for the agents and Valuation Guide"). That is the behaviour we just
    # reversed, so they need the range removed too. Without this pass the
    # backfill silently leaves the exact defect it was written to fix, on the
    # homes that had it longest.
    legacy = 0
    for s in SUBURBS:
        for d in gc[s].find(
                {"property_type": "House",
                 "valuation_data.confidence.directional_only": True,
                 "valuation_data.confidence.range": {"$ne": None}},
                {"_id": 1}):
            legacy += 1
            if not args.dry_run:
                gc[s].update_one({"_id": d["_id"]}, {"$set": {
                    "valuation_data.confidence.range": None}})

    verb = "would suppress" if args.dry_run else "suppressed"
    print(f"  legacy directional, range stripped {legacy:,}")
    print(f"  inside envelope, untouched   {ok:,}")
    print(f"  already directional          {already:,}")
    print(f"  {verb} (above ceiling)  {above:,}")
    print(f"  {verb} (below floor)    {below:,}")
    print(f"\n  total affected               {above + below:,}")
    return 0


if __name__ == "__main__":
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and "--dry-run" not in sys.argv:
        # Rule 7 — re-runs whenever the envelope or the valuations move.
        with job_run("backfill_design_envelope", cadence_hours=168,
                     title="Design envelope backfill") as beat:
            rc = main()
            beat.detail = "envelope applied to stored valuations"
        sys.exit(rc)
    sys.exit(main())

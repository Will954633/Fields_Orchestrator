#!/usr/bin/env python3
"""Run the valuation engine on a single subject — on-demand wrapper around
the batch precompute_valuations.py.

Used by the appraisal pipeline so that homeowner-submitted leads (whose
properties have never been on the for-sale list and therefore have no
pre-computed valuation) get a comp set + adjusted range computed before
the V4 report renders. Without this, §03 receipts (page 10) renders the
"Analyst review required" placeholder forever.

USAGE
    python3 scripts/run_subject_valuation.py --subject-id <ObjectId>
    python3 scripts/run_subject_valuation.py --pipeline-id <ObjectId>

What it does
    1. Loads the subject doc from Gold_Coast.<suburb>
    2. Loads the sold catchment + builds median/street-premium caches
       (this is the slowest step — ~10-20s for the catchment)
    3. Calls precompute_property_valuation() — the per-subject engine entry
       from /home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py
    4. Writes the returned valuation_data to Gold_Coast.<suburb>.<subject_id>
    5. The next V4 render reads valuation_data.comparables[] and populates
       §03 receipts automatically

Triggered by process 301 (config/process_commands.yaml), which the bridge
sync fires before process 300 (V4 render) for any new pipeline record whose
subject lacks valuation_data.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Import the batch script so we can re-use its loaders + per-subject function
COMPS_DIR = Path("/home/fields/Feilds_Website/07_Valuation_Comps")
sys.path.insert(0, str(COMPS_DIR))

from bson import ObjectId  # type: ignore
from shared.db import get_client  # type: ignore


def _load_engine():
    """Import the comps engine. Deferred so the import noise + matplotlib/
    pandas overhead only fires when actually invoked."""
    from precompute_valuations import (  # type: ignore
        precompute_property_valuation,
        _load_sold_comparables,
        _preload_gc_coordinates,
        _preload_gc_timelines,
        _build_suburb_median_cache,
        _build_street_premium_cache,
    )
    return {
        "precompute_property_valuation": precompute_property_valuation,
        "_load_sold_comparables": _load_sold_comparables,
        "_preload_gc_coordinates": _preload_gc_coordinates,
        "_preload_gc_timelines": _preload_gc_timelines,
        "_build_suburb_median_cache": _build_suburb_median_cache,
        "_build_street_premium_cache": _build_street_premium_cache,
    }


def _find_subject(client, subject_id: str) -> dict | None:
    """Locate the subject doc in Gold_Coast.<suburb>. Returns the doc with
    `_collection` set so the engine knows where to write back."""
    db = client["Gold_Coast"]
    target_suburbs = [
        "robina", "burleigh_waters", "varsity_lakes", "merrimac",
        "burleigh_heads", "mudgeeraba", "reedy_creek", "worongary", "carrara",
    ]
    for suburb in target_suburbs:
        doc = db[suburb].find_one({"_id": ObjectId(subject_id)})
        if doc:
            doc["_collection"] = suburb
            return doc
    return None


def run_subject_valuation(subject_id: str, *, verbose: bool = True) -> dict:
    """Run the valuation engine on one subject. Returns a result dict with
    status + summary fields, including the engine's `summary.exclusion_reason`
    if the engine couldn't produce a valuation (e.g. insufficient comparables).
    """
    client = get_client()
    db = client["Gold_Coast"]

    subject = _find_subject(client, subject_id)
    if subject is None:
        return {"ok": False, "error": f"subject {subject_id} not found in any target suburb"}

    if verbose:
        print(f"Subject: {subject.get('complete_address') or subject.get('street_address')} "
              f"({subject.get('_collection')}/{subject_id})")
        print(f"  bedrooms={subject.get('bedrooms')} bathrooms={subject.get('bathrooms')} "
              f"listing_status={subject.get('listing_status')}")

    engine = _load_engine()

    # Catchment used for both comparable search and coord/timeline preload.
    # Limiting to the southern-GC premium target catchment (rather than all 54
    # suburbs of sold data) drops preload time from ~130s → ~15s. Adequate
    # because comps almost always come from within these suburbs.
    CATCHMENT_SUBURBS = {
        "robina", "burleigh_waters", "varsity_lakes", "merrimac",
        "burleigh_heads", "mudgeeraba", "reedy_creek", "worongary", "carrara",
    }
    # Always include the subject's suburb even if not in the catchment default.
    subj_suburb = subject["_collection"]
    catchment = CATCHMENT_SUBURBS | {subj_suburb}

    if verbose:
        print(f"Loading sold comparables across catchment ({len(catchment)} suburbs)...")
    t0 = time.time()
    sold_by_suburb_all = engine["_load_sold_comparables"](client)
    # Filter to catchment only
    sold_by_suburb = {k: v for k, v in sold_by_suburb_all.items() if k in catchment}
    total_sold = sum(len(v) for v in sold_by_suburb.values())
    if verbose:
        print(f"  {total_sold} sold records across {len(sold_by_suburb)} catchment suburbs "
              f"({time.time() - t0:.1f}s)")

    suburb_keys = list(sold_by_suburb.keys())
    t0 = time.time()
    gc_coords = engine["_preload_gc_coordinates"](client, suburb_keys)
    gc_timelines = engine["_preload_gc_timelines"](client, suburb_keys)
    if verbose:
        print(f"  loaded coordinates + timelines ({time.time() - t0:.1f}s)")

    median_cache = engine["_build_suburb_median_cache"](sold_by_suburb)
    street_premium_cache = engine["_build_street_premium_cache"](sold_by_suburb, median_cache)

    # Run the per-subject valuation
    if verbose:
        print("Computing valuation...")
    t0 = time.time()
    valuation_data = engine["precompute_property_valuation"](
        db, subject, None, sold_by_suburb,
        gc_coords, gc_timelines, median_cache, street_premium_cache,
    )
    compute_ms = int((time.time() - t0) * 1000)

    if not valuation_data:
        return {
            "ok": False,
            "subject_id": subject_id,
            "suburb": subject.get("_collection"),
            "error": "engine returned no valuation_data (insufficient comparables or excluded subject)",
            "compute_ms": compute_ms,
        }

    # Annotate + write
    valuation_data.setdefault("metadata", {})
    valuation_data["metadata"]["computation_time_ms"] = compute_ms
    valuation_data["metadata"]["computed_at"] = datetime.now(timezone.utc).isoformat()
    valuation_data["metadata"]["computed_by"] = "run_subject_valuation.py"

    col_name = subject["_collection"]
    db[col_name].update_one(
        {"_id": ObjectId(subject_id)},
        {"$set": {"valuation_data": valuation_data}},
    )

    summary = valuation_data.get("summary") or {}
    confidence = (valuation_data.get("confidence") or {})
    rng = confidence.get("range") or {}
    # Engine schema: recent_sales[] = sold comps (primary), comparables[] = current listings used as comps
    all_comps = (valuation_data.get("recent_sales") or []) + (valuation_data.get("comparables") or [])
    n_total = len(all_comps)
    n_included = summary.get("n_included_in_valuation") or len([
        c for c in all_comps if c.get("included_in_valuation")
    ])
    exclusion = summary.get("exclusion_reason")

    if verbose:
        print(f"  computed in {compute_ms}ms")
        print(f"  comparables: {n_total} total · {n_included} included in valuation")
        print(f"  reconciled range: ${rng.get('low')} – ${rng.get('high')} "
              f"(confidence: {confidence.get('confidence', '—')})")
        if exclusion:
            print(f"  ⚠  exclusion: {exclusion}")
        print(f"  written to Gold_Coast.{col_name}._id={subject_id}.valuation_data")

    return {
        "ok": True,
        "subject_id": subject_id,
        "suburb": col_name,
        "compute_ms": compute_ms,
        "n_comparables_total": n_total,
        "n_comparables_included": n_included,
        "range_low": rng.get("low"),
        "range_high": rng.get("high"),
        "confidence": confidence.get("confidence"),
        "exclusion_reason": exclusion,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--subject-id", help="Subject property ObjectId (Gold_Coast.<suburb>._id)")
    g.add_argument("--pipeline-id", help="appraisal_pipeline ObjectId — resolves to subject_property_id")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-step logging")
    args = parser.parse_args()

    if args.pipeline_id:
        sm = get_client()["system_monitor"]
        pipe = sm.appraisal_pipeline.find_one({"_id": ObjectId(args.pipeline_id)})
        if not pipe:
            raise SystemExit(f"pipeline {args.pipeline_id} not found")
        subject_id = pipe.get("subject_property_id")
        if not subject_id:
            raise SystemExit(f"pipeline {args.pipeline_id} has no subject_property_id")
    else:
        subject_id = args.subject_id

    result = run_subject_valuation(subject_id, verbose=not args.quiet)
    if not result.get("ok"):
        print(f"\n✗ FAILED: {result.get('error')}")
        raise SystemExit(1)
    print(f"\n✓ Valuation written for {subject_id}")


if __name__ == "__main__":
    main()

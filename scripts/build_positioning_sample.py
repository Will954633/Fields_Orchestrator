#!/usr/bin/env python3
"""
build_positioning_sample.py — draw a reproducible, representative sample of
sold properties for the positioning / scarcity evidence base.

We have never had a census of all sold homes — only what we could scrape from
Domain. So the evidence base is, and is labelled as, an *indicative sample*.
This script draws ~N properties per core suburb over a trailing window, using a
fixed seed + stable ordering so the selection is deterministic and auditable,
and records the chosen ids (plus the query, window, seed) in a manifest so the
sample can be reproduced or re-drawn on request.

Selection is representative — NO cherry-picking of well-documented homes (that
would bias the sample). Vacant land is excluded by default because you cannot
make "hard-to-replace home" statements about a parcel with no building.

Outputs:
  - system_monitor.sample_manifest  (one doc per sample build)
  - a representativeness report (sample vs full scraped sold set) to stdout

Usage:
  python3 scripts/build_positioning_sample.py --dry-run
  python3 scripts/build_positioning_sample.py --confirm
  python3 scripts/build_positioning_sample.py --suburb robina --per-suburb 67 --confirm
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.db import get_client, get_gold_coast_db  # noqa: E402

CORE_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
EXCLUDE_TYPES_DEFAULT = ["Land", "Vacant land"]
DEFAULT_SEED = 1337
DEFAULT_PER_SUBURB = 67
DEFAULT_WINDOW_DAYS = 365
# Today is fixed via --as-of for reproducibility; defaults to script run date.
SAMPLE_SCHEMA_VERSION = 1


def _window_start(as_of: dt.date, window_days: int) -> str:
    return (as_of - dt.timedelta(days=window_days)).isoformat()


def _candidates(coll, window_start: str, exclude_types: List[str]) -> List[Dict[str, Any]]:
    """Sold-in-window docs, excluding the excluded property types. Sorted by
    (sold_date, _id) for a stable, temporally-spread ordering."""
    q = {
        "listing_status": "sold",
        "sold_date": {"$gte": window_start},
        "property_type": {"$nin": exclude_types},
    }
    proj = {"_id": 1, "address": 1, "url_slug": 1, "sold_date": 1,
            "property_type": 1, "bedrooms": 1, "bathrooms": 1,
            "sale_price": 1, "land_size_sqm": 1, "lot_size_sqm": 1}
    docs = list(coll.find(q, proj))
    docs.sort(key=lambda d: (str(d.get("sold_date") or ""), str(d.get("_id"))))
    return docs


def _draw(docs: List[Dict[str, Any]], n: int, seed: int) -> List[Dict[str, Any]]:
    """Deterministic representative draw: seed a PRNG off the (stable) candidate
    ordering and sample without replacement. Same inputs → same sample."""
    if len(docs) <= n:
        return docs
    rng = random.Random(seed)
    idx = sorted(rng.sample(range(len(docs)), n))
    return [docs[i] for i in idx]


def _dist(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarise a cohort for the representativeness report."""
    types = Counter((d.get("property_type") or "Unknown") for d in docs)
    beds = Counter(str(d.get("bedrooms")) for d in docs if d.get("bedrooms") is not None)
    return {
        "n": len(docs),
        "property_type": dict(types.most_common()),
        "bedrooms": dict(sorted(beds.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburb", help="Limit to one core suburb (default: all 3)")
    ap.add_argument("--per-suburb", type=int, default=DEFAULT_PER_SUBURB)
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--as-of", help="ISO date the window ends (default: today)")
    ap.add_argument("--exclude-types", default=",".join(EXCLUDE_TYPES_DEFAULT),
                    help="Comma-separated property_type values to exclude")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show selection + report, do NOT write the manifest")
    ap.add_argument("--confirm", action="store_true",
                    help="Write the manifest to system_monitor.sample_manifest")
    args = ap.parse_args()

    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    window_start = _window_start(as_of, args.window_days)
    exclude_types = [t.strip() for t in args.exclude_types.split(",") if t.strip()]
    suburbs = [args.suburb] if args.suburb else CORE_SUBURBS

    db = get_gold_coast_db()

    selected: Dict[str, List[Dict[str, Any]]] = {}
    pop: Dict[str, List[Dict[str, Any]]] = {}
    print(f"Window: {window_start} → {as_of.isoformat()}  | seed={args.seed} "
          f"| per_suburb={args.per_suburb} | exclude={exclude_types}\n")
    for s in suburbs:
        cands = _candidates(db[s], window_start, exclude_types)
        pick = _draw(cands, args.per_suburb, args.seed)
        pop[s] = cands
        selected[s] = pick
        print(f"  {s:18} population={len(cands):4}  sampled={len(pick):4}")

    total = sum(len(v) for v in selected.values())
    print(f"\nTotal sampled: {total}")

    # Representativeness report — sample vs population per suburb
    print("\n=== Representativeness (sample vs full scraped sold set) ===")
    for s in suburbs:
        ps, ss = _dist(pop[s]), _dist(selected[s])
        print(f"\n{s}  (pop n={ps['n']}, sample n={ss['n']})")
        print(f"  type  pop: {ps['property_type']}")
        print(f"  type  smp: {ss['property_type']}")
        print(f"  beds  pop: {ps['bedrooms']}")
        print(f"  beds  smp: {ss['bedrooms']}")

    # Build manifest
    sample_basis = f"{args.seed}|{window_start}|{as_of.isoformat()}|{args.per_suburb}|{','.join(suburbs)}"
    sample_id = "sample_" + hashlib.sha256(sample_basis.encode()).hexdigest()[:12]
    manifest = {
        "sample_id": sample_id,
        "schema_version": SAMPLE_SCHEMA_VERSION,
        "created_at": dt.datetime.utcnow().isoformat() + "Z",
        "as_of": as_of.isoformat(),
        "window_start": window_start,
        "window_days": args.window_days,
        "seed": args.seed,
        "per_suburb": args.per_suburb,
        "suburbs": suburbs,
        "exclude_types": exclude_types,
        "source": "Domain-scraped sold set (not a census)",
        "query": {"listing_status": "sold", "sold_date": {"$gte": window_start},
                  "property_type": {"$nin": exclude_types}},
        "members": {s: [str(d["_id"]) for d in selected[s]] for s in suburbs},
        "member_count": total,
        "population_count": {s: len(pop[s]) for s in suburbs},
        "representativeness": {s: {"population": _dist(pop[s]), "sample": _dist(selected[s])}
                               for s in suburbs},
    }

    print(f"\nManifest sample_id: {sample_id}")
    if args.dry_run or not args.confirm:
        print("\n(dry-run — manifest NOT written. Re-run with --confirm to persist.)")
        return 0

    client = get_client()
    coll = client["system_monitor"]["sample_manifest"]
    coll.replace_one({"sample_id": sample_id}, manifest, upsert=True)
    print(f"\n✓ Manifest written to system_monitor.sample_manifest ({total} members)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

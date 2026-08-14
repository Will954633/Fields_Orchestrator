#!/usr/bin/env python3
"""
build_typical_attributes.py — median physical attributes per
(suburb, property_type, bedrooms), for the "use typical figures" offer on the
V4 /off-market/:slug correction panel.

WHY THIS TABLE EXISTS
    When we decline to value a home for a missing floor area, the reader may
    simply not know it. Offering the typical figure for their kind of home in
    their suburb lets them get an indicative answer anyway, and lets them
    correct it from a sensible starting point instead of a blank box.

⚠ WHAT A "TYPICAL" VALUATION IS AND IS NOT
    Floor area is the single largest adjustment the method makes, and the
    interquartile spread inside these buckets is real — a 3-bedroom Robina house
    runs 133-176 m² across the middle half. So a valuation built on the median
    is a valuation of a TYPICAL home of this shape, not of the reader's home.
    The UI must say so, and `p25`/`p75`/`n` are published here precisely so it
    can show the spread rather than implying a precision the median does not
    have. Never present a typical-input figure as the reader's home's value.

⚠ ATTRIBUTES ARE RESOLVED WITH THE ENGINE'S OWN RESOLVERS, imported rather than
    reimplemented. Two separate defects on 2026-08-14 came from a second reader
    of floor area / land size that did not share the engine's rules
    (`[SUB40-FLOOR-AREA-CONTRADICTION]`, `[LOADER-LAND-SIZE-CHAIN]`). A third
    definition here would be the same bug again.

Writes system_monitor.typical_attributes, one doc per bucket. Nightly.
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median, quantiles
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from shared.db import get_client  # noqa: E402
from scripts.job_status import job_run  # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
TYPES = ["House", "Townhouse"]

# Below this the median is not a fact about the suburb, it is a fact about a
# handful of homes. Burleigh Waters 3-bed townhouses have n=23 — reported, but
# not offered as a starting point.
MIN_SAMPLE = 30


def build():
    client = get_client()
    gc = client["Gold_Coast"]
    import precompute_valuations as pv

    buckets = defaultdict(lambda: {"floor": [], "land": [], "bath": [], "car": []})
    scanned = 0
    for suburb in SUBURBS:
        for doc in gc[suburb].find({"property_type": {"$in": TYPES}}):
            scanned += 1
            beds = doc.get("bedrooms")
            floor = pv.resolve_floor_area(doc)
            if not beds or not floor:
                continue
            key = (suburb, doc.get("property_type"), int(beds))
            b = buckets[key]
            b["floor"].append(floor)
            land = pv.resolve_land_size(doc)
            if land:
                b["land"].append(land)
            for field, slot in (("bathrooms", "bath"), ("car_spaces", "car")):
                v = doc.get(field)
                if isinstance(v, (int, float)) and v > 0:
                    b[slot].append(float(v))

    coll = client["system_monitor"]["typical_attributes"]
    written = 0
    for (suburb, ptype, beds), b in sorted(buckets.items()):
        n = len(b["floor"])
        if n < MIN_SAMPLE:
            continue
        q = quantiles(b["floor"], n=4) if n >= 4 else [None, None, None]
        coll.update_one(
            {"suburb": suburb, "property_type": ptype, "bedrooms": beds},
            {"$set": {
                "n": n,
                "floor_area_sqm": round(median(b["floor"])),
                "floor_p25": round(q[0]) if q[0] else None,
                "floor_p75": round(q[2]) if q[2] else None,
                "land_size_sqm": round(median(b["land"])) if b["land"] else None,
                "land_n": len(b["land"]),
                "bathrooms": round(median(b["bath"])) if b["bath"] else None,
                "car_spaces": round(median(b["car"])) if b["car"] else None,
                "computed_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        written += 1

    return {"scanned": scanned, "buckets": len(buckets), "written": written}


if __name__ == "__main__":
    with job_run("build_typical_attributes", cadence_hours=24,
                 title="Typical attributes by suburb/type/beds") as beat:
        res = build()
        beat.metrics = res
        # Rule 7b — the suburbs and their documents always exist, so a run that
        # wrote no buckets means the resolvers or the query broke, never that
        # there was nothing to do. Reporting success there would leave the
        # "typical figures" offer silently serving whatever it wrote last.
        if not res["written"]:
            raise RuntimeError(
                f"scanned {res['scanned']} docs and wrote 0 buckets — "
                "resolver or query is broken, not the data empty")
        beat.detail = f"{res['written']} buckets from {res['scanned']:,} docs"

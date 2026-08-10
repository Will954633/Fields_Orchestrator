#!/usr/bin/env python3
"""
Render a boundary-marked aerial for every off-market house and publish it.

WHAT THIS PRODUCES
───────────────────────────────────────────────────────────────────────────────
The image at the top of the V4 private report: a Google Static Maps aerial with
the property's TITLE BOUNDARY drawn on in Fields sun (#fec66f) and the Fields
icon stamped top-left. Exactly what `render_property_aerial.py` already makes for
the prototype — this runs it across the book and puts the result somewhere the
website can load.

WHY IT IS NEEDED
───────────────────────────────────────────────────────────────────────────────
14,531 documents already carry a RAW aerial (`cadastral_photos_dir`). None of
them carry the boundary, and the boundary is the point: it is what turns "a
photo of some roofs" into "this is your block, and here is its shape". The
polygon comes from the QLD cadastre by lotplan, which is free; the base image is
a Static Maps call, which is not.

⚠ THIS SPENDS MONEY. One Static Maps request per property. 12,316 renderable
houses at US$2/1,000 is roughly US$25 for a full pass. `--limit` and `--dry-run`
exist so a batch can be sized before it is paid for, and completed renders are
skipped on re-run so a retry costs nothing for work already done.

WHERE THE OUTPUT GOES
───────────────────────────────────────────────────────────────────────────────
/data/blobs/property-images/aerial/<suburb>/<id>/boundary.png
→ served at https://blobs.fieldsestate.com.au/property-images/aerial/...
and the URL is written to `aerial_boundary_url` on the document, which is what
the route loader reads.

    python3 scripts/batch_render_aerials.py --dry-run
    python3 scripts/batch_render_aerials.py --limit 25
    python3 scripts/batch_render_aerials.py                 # the whole book
"""

import argparse
import os
import sys
import time
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root, for shared.*
sys.path.insert(0, _HERE)                    # scripts/, for job_status
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from shared.env import load_env
from shared.db import get_gold_coast_db
from job_status import job_run

load_env()

import render_property_aerial as ra  # noqa: E402  (needs load_env first)

SUBURBS = ("robina", "varsity_lakes", "burleigh_waters")
BLOB_ROOT = Path("/data/blobs/property-images/aerial")
PUBLIC_ROOT = "https://blobs.fieldsestate.com.au/property-images/aerial"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true", help="re-render even if one exists")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_gold_coast_db()
    suburbs = [args.suburb] if args.suburb else list(SUBURBS)

    if args.dry_run:
        total = 0
        for s in suburbs:
            q = {"listing_status": {"$nin": ["sold", "for_sale"]}, "property_type": "House",
                 "LOT": {"$nin": [None, ""]}, "PLAN": {"$nin": [None, ""]}}
            if not args.force:
                q["aerial_boundary_url"] = {"$exists": False}
            n = db[s].count_documents(q)
            total += n
            print(f"  {s:<18}{n:>7,} to render")
        print(f"  {'TOTAL':<18}{total:>7,}   ~US${total / 1000 * 2:.0f} in Static Maps calls")
        return

    with job_run("batch_render_aerials", cadence_hours=168,
                 title="Boundary Aerial Render") as beat:
        rendered = skipped = failed = 0
        eligible = 0

        for suburb in suburbs:
            q = {"listing_status": {"$nin": ["sold", "for_sale"]}, "property_type": "House",
                 "LOT": {"$nin": [None, ""]}, "PLAN": {"$nin": [None, ""]}}
            if not args.force:
                q["aerial_boundary_url"] = {"$exists": False}
            cursor = db[suburb].find(q, {"address": 1, "LOT": 1, "PLAN": 1,
                                         "LATITUDE": 1, "LONGITUDE": 1})
            if args.limit:
                cursor = cursor.limit(args.limit)

            for doc in cursor:
                eligible += 1
                out_dir = BLOB_ROOT / suburb / str(doc["_id"])
                final = out_dir / "boundary.png"
                if final.exists() and not args.force:
                    skipped += 1
                    continue
                try:
                    path, note = ra.render(db, suburb, doc, "sun", str(out_dir))
                except Exception as exc:                      # noqa: BLE001
                    failed += 1
                    print(f"    {doc.get('address')}: ERROR {type(exc).__name__}: {exc}")
                    continue
                if not path:
                    # No parcel on file — a real outcome, not an error. Recorded so
                    # a later pass does not keep paying for the same lookup.
                    failed += 1
                    db[suburb].update_one({"_id": doc["_id"]},
                                          {"$set": {"aerial_boundary_failed": note}})
                    continue
                Path(path).rename(final)
                url = f"{PUBLIC_ROOT}/{suburb}/{doc['_id']}/boundary.png"
                db[suburb].update_one({"_id": doc["_id"]},
                                      {"$set": {"aerial_boundary_url": url,
                                                "aerial_boundary_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                       "$unset": {"aerial_boundary_failed": ""}})
                rendered += 1
                if rendered % 50 == 0:
                    print(f"    {suburb}: {rendered} rendered")

        beat.metrics = {"rendered": rendered, "skipped": skipped,
                        "failed": failed, "eligible": eligible}

        # Rule 7b — an empty queue is success; eligible-but-nothing-rendered is not.
        if eligible and not rendered and not skipped:
            raise RuntimeError(
                f"{eligible} properties eligible but 0 rendered and 0 skipped "
                f"({failed} failed) — the cadastre lookup or the Static Maps key is broken")

        beat.detail = f"{rendered} rendered, {skipped} already present, {failed} without a parcel"
        print(f"\n  rendered {rendered} · skipped {skipped} · failed {failed}")


if __name__ == "__main__":
    main()

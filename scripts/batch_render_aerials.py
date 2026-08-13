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



def build_query(args):
    """The set of dwellings this pass will render.

    ⚠ ONE DEFINITION, USED BY BOTH THE COST ESTIMATE AND THE RUN. It was written out
    twice, identically, which is how an estimate quietly stops describing the job it is
    estimating — the same duplicated-policy shape as the sitemap/robots divergence.
    """
    q = {"listing_status": {"$nin": ["sold", "for_sale"]},
         "LOT": {"$nin": [None, ""]}, "PLAN": {"$nin": [None, ""]}}
    # ⚠ `--for-sale` INVERTS the default exclusion rather than relaxing it: the V2
    # listing page (15_On_Market) uses the same boundary hero as the off-market
    # report, and those listings are precisely the ones the default query drops.
    # Kept as an explicit opt-in so a normal off-market pass can never silently
    # start spending Static Maps calls on live listings.
    if getattr(args, "for_sale", False):
        q["listing_status"] = "for_sale"
    if not args.attached:
        q["property_type"] = "House"
    # INDEXED PAGES FIRST. The aerial is the hero — the first thing on the page and the
    # reason a reader recognises their own home. 4,980 unit URLs entered the index on
    # 2026-08-13, and a broad pass over all 13,329 attached dwellings reached only 7% of
    # them in the first hours because it walks the collection in natural order.
    if args.indexable_only:
        q["unit_indexable"] = True
        # ⚠ AND DROP THE listing_status EXCLUSION, WHICH CONTRADICTS THE FLAG.
        # The default query skips `sold` because a sold HOUSE belongs to the
        # recently-sold surface, not the off-market one. `flag_unit_indexable`
        # deliberately ALLOWS sold dwellings — a sale history is what earns an
        # off-market page at all; only `for_sale`/`under_contract` are declined.
        # Leaving the exclusion in meant 110 live indexed unit pages could never
        # receive an aerial: the flag said "publish this" and the renderer said "not
        # eligible". `unit_indexable` is the single definition of what is published
        # (flag_unit_indexable.py); it must not be intersected with an older rule
        # that disagrees with it.
        q.pop("listing_status", None)
    if not args.force:
        q["aerial_boundary_url"] = {"$exists": False}
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--for-sale", dest="for_sale", action="store_true",
                    help="render live for-sale listings instead of off-market stock "
                         "(the V2 listing-page hero)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--indexable-only", action="store_true",
                    help="only dwellings flagged unit_indexable — the pages that are live")
    ap.add_argument("--attached", action="store_true",
                    help="render attached dwellings (units/townhouses) instead of houses only")
    ap.add_argument("--force", action="store_true", help="re-render even if one exists")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_gold_coast_db()
    suburbs = [args.suburb] if args.suburb else list(SUBURBS)

    if args.dry_run:
        total = 0
        for s in suburbs:
            # ⚠ `property_type: "House"` here is why 86.7% of houses carry an aerial and
            # 0.4% of attached dwellings do — despite 94.9% of them holding the LAT/PLAN
            # needed to render one. Units get the same treatment under --attached:
            # a townhouse resolves its OWN lot (1GTP3941 -> 195 m²), and an apartment,
            # which owns no land and has no polygon of its own, falls back to the scheme
            # parcel (0SP197709 -> 3,582 m²). See polygon_for()/scheme_lotplan_for().
            q = build_query(args)
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
            # ⚠ `property_type: "House"` here is why 86.7% of houses carry an aerial and
            # 0.4% of attached dwellings do — despite 94.9% of them holding the LAT/PLAN
            # needed to render one. Units get the same treatment under --attached:
            # a townhouse resolves its OWN lot (1GTP3941 -> 195 m²), and an apartment,
            # which owns no land and has no polygon of its own, falls back to the scheme
            # parcel (0SP197709 -> 3,582 m²). See polygon_for()/scheme_lotplan_for().
            q = build_query(args)
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
                # ⚠ SCOPE TRAVELS WITH THE IMAGE. For a house and for a townhouse the
                # outline is the dwelling's own lot; for an apartment it is the SCHEME's
                # parcel, because an apartment owns no land and has no polygon. The page
                # caption must say "your home" or "your building" accordingly — an
                # outline around forty neighbours captioned "this is your block" is the
                # exact defect this whole feature exists to avoid.
                fresh = db[suburb].find_one({"_id": doc["_id"]}, {"cadastral_polygon": 1})
                scope = ((fresh or {}).get("cadastral_polygon") or {}).get("boundary_scope") or "lot"
                db[suburb].update_one({"_id": doc["_id"]},
                                      {"$set": {"aerial_boundary_url": url,
                                                "aerial_boundary_scope": scope,
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

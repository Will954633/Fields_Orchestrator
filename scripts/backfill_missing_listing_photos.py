#!/usr/bin/env python3
"""
backfill_missing_listing_photos.py — re-fetch photos for listings we don't hold.

WHY (2026-08-07). After `repoint_listing_images.py` pointed 2,013 listings at
photos already on disk, ~300 active listings were left whose image URLs we cannot
serve AND whose photos are not in `/data/blobs/`:

    bucket-api.domain.com.au, no local copy    266
    dead Azure URL, no local copy               34
    no property_images at all                   17

These are invisible to step 110 (`download_images_to_blob.py`). Its selection
query skips anything with `images_uploaded_to_blob: True`, and on these documents
that flag is wrongly True — the upload was recorded against the Azure account
that was cancelled on 2026-05-28, or the listing appeared and went before a
Sunday run. `property_images` is non-empty, so the 2026-07-30 gap-fix branch does
not catch them either.

WHAT THIS DOES — deliberately NOT a second downloader. It clears the stale flag
so the tested pipeline collects them on its next pass, and can run that pass
immediately. Reimplementing the download would mean two code paths writing the
same blob layout, which is how the layout drifts.

    python3 scripts/backfill_missing_listing_photos.py --dry-run
    python3 scripts/backfill_missing_listing_photos.py --apply
    python3 scripts/backfill_missing_listing_photos.py --apply --run-download
"""
import argparse
import glob
import os
import subprocess
import sys
from collections import Counter

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from dotenv import load_dotenv                          # noqa: E402
from src.mongo_client_factory import get_mongo_client   # noqa: E402

BLOB_ROOT = "/data/blobs/property-images/for_sale"


def has_local(suburb, doc_id):
    return bool(glob.glob(f"{BLOB_ROOT}/{suburb}/{doc_id}/photos/**/*.jpg", recursive=True))


def source_urls(doc):
    """Anywhere an original, re-downloadable URL might live.

    `bucket-api.domain.com.au` is included on purpose: it is blocked in a BROWSER
    (hotlink/ORB) but returns 200 to a server, which is exactly the case where a
    server-side fetch is the fix. The dead Azure host is excluded — that account
    is gone and nothing will come back from it.
    """
    for key in ("scraped_property_images", "domain_image_urls", "property_images"):
        v = doc.get(key)
        if isinstance(v, list) and v and isinstance(v[0], str):
            usable = [u for u in v
                      if isinstance(u, str)
                      and "fieldspropertyimages.blob.core.windows.net" not in u
                      and "blobs.fieldsestate.com.au" not in u]
            if usable:
                return key, usable
    return None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-download", action="store_true",
                    help="invoke step 110 immediately after clearing the flags")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    load_dotenv(os.path.join(ORCH, ".env"))
    gc = get_mongo_client()["Gold_Coast"]
    out = Counter()
    touched_suburbs = set()

    for suburb in gc.list_collection_names():
        for d in gc[suburb].find({"listing_status": "for_sale"},
                                 {"property_images": 1, "scraped_property_images": 1,
                                  "domain_image_urls": 1, "images_uploaded_to_blob": 1,
                                  "address": 1}):
            if has_local(suburb, d["_id"]):
                out["already have the photos"] += 1
                continue
            key, urls = source_urls(d)
            if not urls:
                # Nothing to fetch from. Usually a malformed scrape (an "address"
                # like "Coomera, QLD 4209 house for Sale, $1,202...") — flagged,
                # not silently counted as done.
                out["NO source URL — unrecoverable"] += 1
                continue
            out[f"queued (source: {key})"] += 1
            touched_suburbs.add(suburb)
            if apply:
                gc[suburb].update_one({"_id": d["_id"]},
                                      {"$set": {"images_uploaded_to_blob": False}})

    print(f"\n  {'APPLIED' if apply else 'DRY RUN'}\n")
    for k, v in out.most_common():
        print(f"    {k:<40} {v:,}")
    queued = sum(v for k, v in out.items() if k.startswith("queued"))
    print(f"\n  {queued:,} listing(s) {'flagged for' if apply else 'would be flagged for'} re-download"
          f" across {len(touched_suburbs)} suburb(s)")

    if apply and args.run_download and queued:
        print("\n  running step 110 …")
        # ⚠ NO --suburbs. That flag expects "Name:postcode" (e.g. "Robina:4226"),
        # not collection names — passing collection names silently matches
        # nothing and reports "Properties found: 0", which looks like success.
        # Unfiltered is both correct and safe here: step 110's own query selects
        # on `images_uploaded_to_blob != True`, which is exactly the set this
        # script just flagged (measured: 299 docs total, 296 of them ours).
        cmd = [sys.executable, os.path.join(ORCH, "scripts", "download_images_to_blob.py"),
               "--no-fail"]
        subprocess.run(cmd, cwd=ORCH, check=False)
    elif not apply:
        print("  nothing written. re-run with --apply.")
    return 0


if __name__ == "__main__":
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and "--apply" in sys.argv and "--dry-run" not in sys.argv:
        # Rule 7 — new listings can always arrive without photos, so this is a
        # recurring reconciliation, not a one-shot.
        with job_run("backfill_missing_listing_photos", cadence_hours=168,
                     title="Backfill missing listing photos") as beat:
            rc = main()
            beat.detail = "listings without local photos re-queued for download"
        sys.exit(rc)
    sys.exit(main())

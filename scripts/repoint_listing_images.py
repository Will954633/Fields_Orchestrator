#!/usr/bin/env python3
"""
repoint_listing_images.py — point `property_images` at photos we actually hold.

WHY (2026-08-07). 2,013 of 2,822 active listings (71%) carry image URLs that no
browser can render, while the photograph itself sits on this VM:

    fieldspropertyimages.blob.core.windows.net   1,568   Azure account CANCELLED
                                                         2026-05-28. Connection
                                                         error, not a 404.
    bucket-api.domain.com.au                       445   HTTP 200 server-side but
                                                         0/3 render in a browser
                                                         (hotlink/ORB blocked).

`/data/blobs/property-images/` (296 GB) is served at `blobs.fieldsestate.com.au`,
mirrored nightly to `gs://fields-blob-backup`. The nightly (step 110) has already
been migrated and writes CDN URLs — the newest 60 listings are all correct. These
are LEGACY rows the migration never rewrote.

So this is a data cleanup, not a fetch. Nothing is downloaded.

    python3 scripts/repoint_listing_images.py --dry-run
    python3 scripts/repoint_listing_images.py --apply
    python3 scripts/repoint_listing_images.py --apply --revert     # undo

SAFETY
  * A URL is only written when the local file EXISTS. We never publish a link we
    cannot serve — that is the defect being fixed, and re-committing it in a
    different form would be worse than leaving it alone.
  * The original array is preserved at `property_images_pre_repoint`, so --revert
    is exact rather than reconstructed.
  * Idempotent: a second run finds nothing to do.
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from dotenv import load_dotenv                          # noqa: E402
from src.mongo_client_factory import get_mongo_client   # noqa: E402

BLOB_ROOT = "/data/blobs"
CDN = "https://blobs.fieldsestate.com.au"
DEAD_HOSTS = ("fieldspropertyimages.blob.core.windows.net", "bucket-api.domain.com.au")


def local_photos(suburb, doc_id):
    """Every photo we hold for a listing, in filename order.

    Layout: /data/blobs/property-images/for_sale/<suburb>/<_id>/photos/[<date>/]NN.jpg
    The date directory is present on newer captures and absent on older ones, so
    the glob has to tolerate both.
    """
    base = f"{BLOB_ROOT}/property-images/for_sale/{suburb}/{doc_id}/photos"
    files = sorted(glob.glob(f"{base}/**/*.jpg", recursive=True))
    # Numeric order (00, 01, ... 10) — lexical order is already correct for
    # zero-padded names, but a stray unpadded file would sort wrongly.
    def key(p):
        m = re.search(r"(\d+)\.jpg$", p)
        return (os.path.dirname(p), int(m.group(1)) if m else 0)
    return sorted(files, key=key)


def to_cdn(path):
    assert path.startswith(BLOB_ROOT + "/")
    return CDN + path[len(BLOB_ROOT):]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    load_dotenv(os.path.join(ORCH, ".env"))
    gc = get_mongo_client()["Gold_Coast"]
    out = Counter()

    for suburb in gc.list_collection_names():
        if args.revert:
            cur = gc[suburb].find({"property_images_pre_repoint": {"$exists": True}},
                                  {"property_images_pre_repoint": 1})
            for d in cur:
                out["reverted"] += 1
                if apply:
                    gc[suburb].update_one({"_id": d["_id"]}, {
                        "$set": {"property_images": d["property_images_pre_repoint"]},
                        "$unset": {"property_images_pre_repoint": "", "images_repointed_at": ""}})
            continue

        cur = gc[suburb].find({"listing_status": "for_sale", "property_images.0": {"$exists": True}},
                              {"property_images": 1})
        for d in cur:
            imgs = d.get("property_images") or []
            first = imgs[0] if isinstance(imgs[0], str) else None
            if not first or not any(h in first for h in DEAD_HOSTS):
                out["already ok"] += 1
                continue
            files = local_photos(suburb, d["_id"])
            if not files:
                out["no local copy — needs backfill"] += 1
                continue
            new = [to_cdn(f) for f in files]
            if new == imgs:
                out["already ok"] += 1
                continue
            out["repointed"] += 1
            out[f"  from {'azure' if DEAD_HOSTS[0] in first else 'domain'}"] += 1
            if apply:
                from datetime import datetime, timezone
                gc[suburb].update_one({"_id": d["_id"]}, {"$set": {
                    "property_images_pre_repoint": imgs,
                    "property_images": new,
                    "images_repointed_at": datetime.now(timezone.utc)}})
            if args.limit and out["repointed"] >= args.limit:
                break

    verb = "would " if not apply else ""
    print(f"\n  mode: {'REVERT' if args.revert else 'repoint'}  "
          f"{'APPLIED' if apply else 'DRY RUN'}\n")
    for k, v in out.most_common():
        print(f"    {k:<38} {v:,}")
    if not apply:
        print(f"\n  nothing written. re-run with --apply to {verb}commit.")
    return 0


if __name__ == "__main__":
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and "--apply" in sys.argv and "--dry-run" not in sys.argv:
        # Rule 7 — legacy rows can reappear if an old migration re-runs, so this
        # is re-run on a cadence rather than being a one-shot.
        with job_run("repoint_listing_images", cadence_hours=168,
                     title="Repoint listing images to the CDN") as beat:
            rc = main()
            beat.detail = "property_images pointed at photos we hold"
        sys.exit(rc)
    sys.exit(main())

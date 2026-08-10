#!/usr/bin/env python3
"""
Record the REAL first cadastral photo for each property, instead of guessing it.

THE BUG THIS FIXES
───────────────────────────────────────────────────────────────────────────────
`aerialUrl()` in the website route built the fallback hero image by string
concatenation:

    https://blobs.fieldsestate.com.au/<dir>/0001.jpg

Two of those assumptions are wrong. The scraped photos are saved as **.png** far
more often than .jpg, and a directory does not necessarily start at 0001 — some
begin at 0003, 0014, even 0205. Measured 2026-08-10 across the three V4
suburbs: of 3,583 properties relying on this fallback, **2,733 (76%) were
serving a 404** — a visibly broken image at the top of a live report page.

Nothing in the database recorded the filename, so the website could not have
known. `cadastral_photos_count` says how MANY photos exist, never WHICH.

WHAT IT WRITES
───────────────────────────────────────────────────────────────────────────────
`cadastral_photo_url` — the complete, verified public URL of the first photo,
or unset when the directory is missing/empty. The route reads this field and
concatenates nothing, so the class of defect cannot recur: a URL either exists
because a file was seen on disk, or there is no URL and the page omits the
image (which is honest) rather than showing a broken one (which is not).

    python3 scripts/backfill_cadastral_photo_urls.py --dry-run
    python3 scripts/backfill_cadastral_photo_urls.py
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from shared.env import load_env
from shared.db import get_gold_coast_db
from job_status import job_run

load_env()

SUBURBS = ("robina", "varsity_lakes", "burleigh_waters")
BLOB_PREFIX = "/data/blobs/"
PUBLIC_ROOT = "https://blobs.fieldsestate.com.au/"
# Only what a browser will actually render as an <img>.
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


def first_photo(dir_path: str) -> str | None:
    """The lexically-first real image file in the directory, or None.

    Returns a NAME, never a guess — the caller only builds a URL for a file
    that was observed on disk.
    """
    try:
        names = sorted(
            n for n in os.listdir(dir_path)
            if n.lower().endswith(IMAGE_EXT) and os.path.isfile(os.path.join(dir_path, n))
        )
    except OSError:
        return None
    return names[0] if names else None


def public_url(dir_path: str, name: str) -> str | None:
    if not dir_path.startswith(BLOB_PREFIX):
        return None          # unexpected path shape — do not guess
    return PUBLIC_ROOT + dir_path[len(BLOB_PREFIX):].strip("/") + "/" + name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_gold_coast_db()
    suburbs = [args.suburb] if args.suburb else list(SUBURBS)

    with job_run("backfill_cadastral_photo_urls", cadence_hours=168,
                 title="Cadastral Photo URL Backfill") as beat:
        eligible = written = cleared = unchanged = no_dir = 0
        ext_mix: dict[str, int] = {}

        for suburb in suburbs:
            q = {"cadastral_photos_dir": {"$exists": True, "$ne": None},
                 "cadastral_photos_count": {"$gt": 0}}
            for doc in db[suburb].find(q, {"cadastral_photos_dir": 1, "cadastral_photo_url": 1}):
                eligible += 1
                d = str(doc["cadastral_photos_dir"])
                name = first_photo(d)
                url = public_url(d, name) if name else None
                if url:
                    ext = os.path.splitext(name)[1].lower()
                    ext_mix[ext] = ext_mix.get(ext, 0) + 1
                current = doc.get("cadastral_photo_url")
                if url == current:
                    unchanged += 1
                    continue
                if args.dry_run:
                    if url:
                        written += 1
                    else:
                        cleared += 1
                    continue
                if url:
                    db[suburb].update_one({"_id": doc["_id"]},
                                          {"$set": {"cadastral_photo_url": url}})
                    written += 1
                else:
                    # The directory is gone or holds no image. Removing the field
                    # is the honest outcome: the page then shows no photo rather
                    # than a broken one.
                    db[suburb].update_one({"_id": doc["_id"]},
                                          {"$unset": {"cadastral_photo_url": ""}})
                    cleared += 1
                    no_dir += 1

        beat.metrics = {"eligible": eligible, "written": written, "cleared": cleared,
                        "unchanged": unchanged, "extensions": ext_mix}
        beat.detail = (f"{written} urls written, {cleared} cleared, "
                       f"{unchanged} already correct ({eligible} eligible)")
        print("  " + beat.detail)
        print(f"  extensions actually on disk: {ext_mix}")

        # Rule 7b — an empty queue is success; a queue that produced nothing is not.
        if eligible and not (written or unchanged):
            raise RuntimeError(
                f"{eligible} properties have cadastral photo directories but not one "
                f"usable image was found — the blob mount is probably not present, "
                f"which is a different failure from 'no photos exist'"
            )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
backfill_sold_fullres_photos.py — localise full-resolution photos for SOLD homes
so the mini-site can serve comparable galleries from our own blob store
(blobs.fieldsestate.com.au) instead of Domain's CDN.

Why: sold homes were only ever archived locally as 150px cadastral thumbnails.
The full-res versions live only on Domain's CDN (rotation/404 risk). This pulls
the full-res images from each home's `property_images_original` field (Domain
bucket-api → b.domainstatic, full-res JPEG) and writes, per image, BOTH:

    property-images/sold/<suburb>/<id>/photos/<NN>.jpg   (full-res, lightbox)
    property-images/sold/<suburb>/<id>/thumbs/<NN>.jpg   (~320px, card strip)

keyed by the home's Mongo _id (== the engine comp `id`), so the resolver can
build URLs deterministically. Idempotent: skips homes already localised.

Usage:
  python3 scripts/backfill_sold_fullres_photos.py --dry-run
  python3 scripts/backfill_sold_fullres_photos.py --ids <id1>,<id2> --suburbs robina   # targeted
  python3 scripts/backfill_sold_fullres_photos.py --suburbs robina,burleigh_waters,varsity_lakes,merrimac
  python3 scripts/backfill_sold_fullres_photos.py --limit 5            # smoke test
"""
from __future__ import annotations
import os
import sys
import io
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from PIL import Image
from bson import ObjectId

from shared.env import load_env
from shared.db import get_gold_coast_db
from shared import blob_storage

load_env()

CONTAINER = "property-images"
CORE_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes", "merrimac"]
DEFAULT_CAP = 15          # images per home (matches the resolver's display cap)
THUMB_WIDTH = 320         # px — small enough for the card strip, crisp at 2x
HTTP_TIMEOUT = 30
PHOTO_WORKERS = 12        # concurrent image downloads within one home

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/home/fields/Fields_Orchestrator/logs/backfill_sold_photos.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("backfill_sold_fullres")

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (FieldsEstate photo backfill)"})
_adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _fetch(url: str) -> bytes | None:
    try:
        r = _session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and r.content:
            return r.content
        log.warning(f"    fetch {r.status_code}: {url[:90]}")
    except Exception as e:
        log.warning(f"    fetch error ({e}): {url[:90]}")
    return None


def _make_thumb(data: bytes, width: int = THUMB_WIDTH) -> bytes | None:
    try:
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGB")
        if im.width > width:
            h = int(im.height * (width / im.width))
            im = im.resize((width, h), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=78, optimize=True)
        return out.getvalue()
    except Exception as e:
        log.warning(f"    thumb error: {e}")
        return None


def _localise_one(suburb: str, doc_id: str, idx: int, url: str) -> bool:
    """Download one full-res image and write photos/<NN>.jpg + thumbs/<NN>.jpg."""
    data = _fetch(url)
    if not data:
        return False
    nn = f"{idx:02d}"
    full_name = f"sold/{suburb}/{doc_id}/photos/{nn}.jpg"
    ok_full = blob_storage.upload(CONTAINER, full_name, data, content_type="image/jpeg")
    thumb = _make_thumb(data)
    if thumb:
        blob_storage.upload(CONTAINER, f"sold/{suburb}/{doc_id}/thumbs/{nn}.jpg",
                            thumb, content_type="image/jpeg")
    return bool(ok_full)


def _already_done(suburb: str, doc_id: str) -> int:
    """How many full-res images are already localised on disk for this home."""
    root = blob_storage._local_root() / CONTAINER / "sold" / suburb / doc_id / "photos"
    try:
        return len([p for p in root.iterdir() if p.is_file()]) if root.exists() else 0
    except Exception:
        return 0


def process_home(db, suburb: str, doc: dict, cap: int, dry_run: bool) -> dict:
    doc_id = str(doc["_id"])
    urls = [u for u in (doc.get("property_images_original") or []) if isinstance(u, str) and u.strip()][:cap]
    if not urls:
        return {"id": doc_id, "status": "no_source"}
    have = _already_done(suburb, doc_id)
    if have >= len(urls):
        return {"id": doc_id, "status": "skip", "n": have}
    if dry_run:
        return {"id": doc_id, "status": "would_do", "n": len(urls)}

    done = 0
    with ThreadPoolExecutor(max_workers=PHOTO_WORKERS) as ex:
        futs = {ex.submit(_localise_one, suburb, doc_id, i, u): i for i, u in enumerate(urls)}
        for f in as_completed(futs):
            if f.result():
                done += 1
    if done:
        db[suburb].update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "sold_fullres_localized": True,
                "sold_fullres_count": done,
                "sold_fullres_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    return {"id": doc_id, "status": "done", "n": done, "of": len(urls)}


def main():
    ap = argparse.ArgumentParser(description="Backfill full-res SOLD photos into local blob store")
    ap.add_argument("--suburbs", default=",".join(CORE_SUBURBS),
                    help="comma-separated suburb collection keys")
    ap.add_argument("--ids", default="", help="comma-separated Mongo _ids to target (subset)")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="max images per home")
    ap.add_argument("--limit", type=int, default=0, help="max homes per suburb (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_gold_coast_db()
    suburbs = [s.strip().lower() for s in args.suburbs.split(",") if s.strip()]
    id_filter = [i.strip() for i in args.ids.split(",") if i.strip()]

    log.info(f"=== backfill start: suburbs={suburbs} cap={args.cap} "
             f"ids={len(id_filter) or 'all'} dry_run={args.dry_run} ===")
    totals = {"done": 0, "skip": 0, "no_source": 0, "would_do": 0, "images": 0}
    for suburb in suburbs:
        q = {"listing_status": "sold", "property_images_original": {"$exists": True, "$ne": []}}
        if id_filter:
            q["_id"] = {"$in": [ObjectId(i) for i in id_filter]}
        proj = {"property_images_original": 1}
        cur = db[suburb].find(q, proj)
        if args.limit:
            cur = cur.limit(args.limit)
        homes = list(cur)
        log.info(f"[{suburb}] {len(homes)} sold homes to consider")
        for n, doc in enumerate(homes, 1):
            r = process_home(db, suburb, doc, args.cap, args.dry_run)
            totals[r["status"]] = totals.get(r["status"], 0) + 1
            totals["images"] += r.get("n", 0) if r["status"] == "done" else 0
            if r["status"] in ("done", "would_do") or n % 50 == 0:
                log.info(f"  [{suburb} {n}/{len(homes)}] {r}")
    log.info(f"=== backfill complete: {totals} ===")


if __name__ == "__main__":
    main()

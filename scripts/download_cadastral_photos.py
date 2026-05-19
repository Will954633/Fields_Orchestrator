#!/usr/bin/env python3
"""Download Domain CDN photos for v2-scraped cadastral records to local disk.

Scope: every record in the named suburb collection with
`scraped_data_v2.image_urls` set, no UNIT_NUMBER restriction.

Storage layout:
    /data/blobs/property-images/cadastral/<suburb>/<oid>/photos/<N>.<ext>

Marker fields written to Mongo:
    cadastral_photos_downloaded_at: ISO datetime
    cadastral_photos_count: int (successful downloads)
    cadastral_photos_failed: int (HTTP/IO failures, skipped)
    cadastral_photos_total_bytes: int (sum of bytes written)

Idempotent: skips records that have `cadastral_photos_downloaded_at` already.
Re-run with --redownload to force.

Run:
    python3 scripts/download_cadastral_photos.py --suburb robina --limit 50
    python3 scripts/download_cadastral_photos.py --suburb burleigh_waters
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bson import ObjectId

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore

load_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("download_cadastral_photos")

BLOB_ROOT = Path(os.getenv("BLOB_LOCAL_ROOT", "/data/blobs"))
PHOTO_BASE = BLOB_ROOT / "property-images" / "cadastral"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Fields/1.0"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 2


def url_extension(url: str) -> str:
    """Infer file extension from a Domain CDN URL."""
    # rimh2 URLs end with things like `...061814-w800-h600` (no extension) or `...jpg`.
    tail = url.rsplit("/", 1)[-1].split("?", 1)[0]
    m = re.search(r"\.(jpe?g|png|webp|gif)$", tail, re.I)
    if m:
        return m.group(1).lower().replace("jpeg", "jpg")
    # Default: Domain rimh2 serves JPEG (or PNG when filters:format(png) is in URL)
    if "format(png)" in url:
        return "png"
    return "jpg"


def download_one(url: str, dest: Path, session: requests.Session) -> int | None:
    """Download a single image. Returns bytes-written on success, None on failure."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT, stream=True,
                            headers={"User-Agent": UA})
            if r.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                total = 0
                tmp = dest.with_suffix(dest.suffix + ".tmp")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(64 * 1024):
                        f.write(chunk)
                        total += len(chunk)
                tmp.rename(dest)
                return total
            elif r.status_code in (429, 503):
                time.sleep(2 + attempt * 2)
                continue
            else:
                return None
        except (requests.RequestException, OSError):
            if attempt < MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            return None
    return None


def process_record(suburb: str, doc: dict, db, session: requests.Session,
                   force: bool) -> dict:
    """Download all photos for one record, write marker to Mongo. Returns stats."""
    oid = str(doc["_id"])
    sv2 = doc.get("scraped_data_v2") or {}
    urls = sv2.get("image_urls") or []

    if not urls:
        return {"oid": oid, "status": "no_urls", "n": 0, "bytes": 0}
    if doc.get("cadastral_photos_downloaded_at") and not force:
        return {"oid": oid, "status": "already_done", "n": doc.get("cadastral_photos_count", 0), "bytes": 0}

    dest_dir = PHOTO_BASE / suburb / oid / "photos"
    n_ok = 0
    n_fail = 0
    total_bytes = 0
    for i, url in enumerate(urls, 1):
        ext = url_extension(url)
        fname = f"{i:04d}.{ext}"
        dest = dest_dir / fname
        if dest.exists() and not force:
            # already downloaded — count its bytes for total
            try:
                total_bytes += dest.stat().st_size
                n_ok += 1
            except OSError:
                pass
            continue
        size = download_one(url, dest, session)
        if size is None:
            n_fail += 1
        else:
            n_ok += 1
            total_bytes += size

    coll = db[suburb]
    coll.update_one(
        {"_id": ObjectId(oid)},
        {"$set": {
            "cadastral_photos_downloaded_at": dt.datetime.utcnow(),
            "cadastral_photos_count": n_ok,
            "cadastral_photos_failed": n_fail,
            "cadastral_photos_total_bytes": total_bytes,
            "cadastral_photos_dir": str(dest_dir),
        }},
    )
    return {"oid": oid, "status": "done", "n": n_ok, "fail": n_fail, "bytes": total_bytes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suburb", required=True,
                    help="Collection name (e.g. robina, burleigh_waters, varsity_lakes)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=16,
                    help="Concurrent records (default 16; each downloads its own photos sequentially)")
    ap.add_argument("--redownload", action="store_true",
                    help="Force re-download records already marked done")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = get_client()
    db = client["Gold_Coast"]
    coll = db[args.suburb]

    query: dict = {"scraped_data_v2.image_urls": {"$exists": True, "$ne": []}}
    if not args.redownload:
        query["cadastral_photos_downloaded_at"] = {"$exists": False}
    total = coll.count_documents(query)
    log.info("Suburb: %s — eligible records: %d", args.suburb, total)

    if args.dry_run:
        sample = list(coll.find(query, {"_id": 1, "scraped_data_v2.image_urls": 1}).limit(5))
        for d in sample:
            n_urls = len(d.get("scraped_data_v2", {}).get("image_urls") or [])
            log.info("  sample %s: %d URLs", d["_id"], n_urls)
        log.info("(dry run — no downloads)")
        return 0

    cursor = coll.find(query, {"_id": 1, "scraped_data_v2.image_urls": 1, "cadastral_photos_downloaded_at": 1})
    if args.limit:
        cursor = cursor.limit(args.limit)

    docs = list(cursor)
    log.info("Loaded %d records to process. Starting %d workers.", len(docs), args.workers)

    counter_lock = threading.Lock()
    counters = {"done": 0, "no_urls": 0, "already_done": 0, "records": 0,
                "photos_ok": 0, "photos_fail": 0, "total_bytes": 0}
    t0 = time.time()

    session_local = threading.local()

    def get_session():
        if not hasattr(session_local, "s"):
            session_local.s = requests.Session()
        return session_local.s

    def worker(doc):
        s = get_session()
        try:
            r = process_record(args.suburb, doc, db, s, args.redownload)
        except Exception as e:
            log.error("EXCEPTION %s: %s", doc.get("_id"), e)
            return None
        with counter_lock:
            counters["records"] += 1
            counters[r["status"]] = counters.get(r["status"], 0) + 1
            if r.get("n"):
                counters["photos_ok"] += r["n"]
            if r.get("fail"):
                counters["photos_fail"] += r.get("fail", 0)
            counters["total_bytes"] += r.get("bytes", 0)
            if counters["records"] % 25 == 0:
                elapsed = time.time() - t0
                rate = counters["records"] / max(elapsed, 1)
                eta_min = (len(docs) - counters["records"]) / max(rate, 0.01) / 60
                gb = counters["total_bytes"] / 1024**3
                log.info("progress: records=%d/%d photos_ok=%d photos_fail=%d disk=%.2fGB rate=%.1f/s ETA=%.0fmin",
                         counters["records"], len(docs), counters["photos_ok"],
                         counters["photos_fail"], gb, rate, eta_min)
        return r

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(worker, d) for d in docs]
        for _ in as_completed(futures):
            pass

    elapsed = time.time() - t0
    gb = counters["total_bytes"] / 1024**3
    log.info("DONE in %.0fs", elapsed)
    log.info("FINAL records=%d done=%d already=%d no_urls=%d photos_ok=%d photos_fail=%d disk=%.2fGB",
             counters["records"], counters.get("done", 0), counters.get("already_done", 0),
             counters.get("no_urls", 0), counters["photos_ok"], counters["photos_fail"], gb)
    if counters["photos_ok"]:
        log.info("Avg per record: %.1f photos, %.1f MB",
                 counters["photos_ok"] / max(counters.get("done", 1), 1),
                 gb * 1024 / max(counters.get("done", 1), 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

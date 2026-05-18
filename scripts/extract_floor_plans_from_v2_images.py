#!/usr/bin/env python3
"""Extract floor plans from v2 image arrays via GPT-4o-mini vision classification.

Context: scraped_data_v2.image_urls contains all images Domain holds for a
property — including floor plans, which Domain doesn't tag separately. Floor
plans are most often near the end but can be buried deeper in multi-listing
aggregations (Domain stacks all historical media). Per-image classification
with gpt-4o-mini vision (low detail) gets 100% precision in spot-checks.

Per record:
  - By default: classify last N images (--tail, default 3)
  - With --all-images: classify every unique image URL in the record
  - Each image: "Is this an architectural floor plan?" → YES / NO
  - YES URLs → doc.floor_plans_v2_extracted (deduped, position-ordered)

Idempotent: skips records that already have floor_plans_v2_extracted_at
(use --force to re-classify).

Run:
    # Smoke test
    python3 scripts/extract_floor_plans_from_v2_images.py --limit 20

    # Full Robina pass, every image, concurrent
    python3 scripts/extract_floor_plans_from_v2_images.py --all --all-images --workers 20
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore

load_env()

import requests
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
    sys.exit(1)

client_oai = OpenAI(api_key=OPENAI_API_KEY)

MODEL = "gpt-4o-mini"
CLASSIFIER_VERSION = "v1-2026-05-18"

PROMPT = (
    "You are classifying property listing images. "
    "Is this image an architectural floor plan (a top-down 2D diagram of room "
    "layouts, walls, and dimensions)? "
    "Answer with exactly one word: YES or NO."
)


_CACHE: dict[str, tuple[str, str]] = {}
_CACHE_LOCK = threading.Lock()


def classify_image(url: str) -> tuple[str, str]:
    """Returns (verdict, raw_response). Verdict ∈ {YES, NO, ERROR}.
    URL-keyed cache avoids duplicate API calls for shared images across records."""
    with _CACHE_LOCK:
        if url in _CACHE:
            return _CACHE[url]
    try:
        resp = client_oai.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": url, "detail": "low"}},
                ],
            }],
            max_tokens=4,
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip().upper()
        if "YES" in raw:
            result = ("YES", raw)
        elif "NO" in raw:
            result = ("NO", raw)
        else:
            result = ("ERROR", raw or "(empty)")
    except Exception as e:
        result = ("ERROR", f"{type(e).__name__}: {e}")
    # Only cache deterministic results (don't cache transient errors)
    if result[0] != "ERROR":
        with _CACHE_LOCK:
            _CACHE[url] = result
    return result


def collect_all_image_urls(doc: dict) -> list[str]:
    """Union of every image source on the doc, deduped, order-preserving.
    Reads v2 + apr01 sidecars + legacy fields. Filters obvious junk (Azure
    blob URLs that 403, non-http entries)."""
    urls: list[str] = []
    seen: set[str] = set()
    DEAD_HOSTS = ("fieldspropertyimages.blob.core.windows.net",)

    def push(items):
        if not items:
            return
        if isinstance(items, str):
            items = [items]
        for it in items:
            if isinstance(it, dict):
                u = it.get("url") or it.get("image_url") or it.get("src") or ""
            else:
                u = it if isinstance(it, str) else ""
            if not u or not u.startswith("http"):
                continue
            if any(h in u for h in DEAD_HOSTS):
                continue
            if u in seen:
                continue
            seen.add(u)
            urls.append(u)

    v2 = doc.get("scraped_data_v2") or {}
    push(v2.get("hero_image_url"))
    push(v2.get("image_urls"))

    apr01 = doc.get("scraped_data_apr01_recovered") or {}
    push(apr01.get("images"))

    apr01_rs = doc.get("scraped_data_recently_sold_apr01_recovered") or {}
    push(apr01_rs.get("images"))

    apr01_fs = doc.get("scraped_data_for_sale_apr01_recovered") or {}
    push(apr01_fs.get("images"))

    push(doc.get("property_images_original"))
    push(doc.get("scraped_property_images"))
    push(doc.get("property_images"))

    return urls


def process_record(coll, doc: dict, tail_n: int | None, image_workers: int,
                   download_dir: Path | None) -> dict:
    """Classify images of one record. If tail_n is None, classify all unique URLs.
    Reads from a union of all image sources (v2 + apr01 sidecars + legacy)."""
    _id = doc["_id"]
    unique_urls = collect_all_image_urls(doc)
    if not unique_urls:
        return {"_id": str(_id), "status": "NO_IMAGES"}

    if tail_n is None:
        candidates = unique_urls
        base_offset = 0  # positions are relative to unique_urls
    else:
        candidates = unique_urls[-tail_n:] if len(unique_urls) >= tail_n else list(unique_urls)
        base_offset = len(unique_urls) - len(candidates)

    classifications: list[dict] = [None] * len(candidates)  # type: ignore

    def _do(idx_url):
        idx, url = idx_url
        verdict, raw = classify_image(url)
        return idx, {
            "position": base_offset + idx + 1,
            "of_total": len(unique_urls),
            "verdict": verdict,
            "raw": raw,
            "url": url,
        }

    if image_workers > 1 and len(candidates) > 1:
        with ThreadPoolExecutor(max_workers=image_workers) as ex:
            for fut in as_completed([ex.submit(_do, (i, u)) for i, u in enumerate(candidates)]):
                idx, result = fut.result()
                classifications[idx] = result
    else:
        for i, u in enumerate(candidates):
            _, result = _do((i, u))
            classifications[i] = result

    yes_urls = [c["url"] for c in classifications if c["verdict"] == "YES"]

    set_doc = {
        "floor_plans_v2_extracted": yes_urls,
        "floor_plans_v2_extracted_at": dt.datetime.utcnow(),
        "floor_plans_v2_classifier": {
            "version": CLASSIFIER_VERSION,
            "model": MODEL,
            "tail_n": tail_n if tail_n is not None else "ALL",
            "total_images": len(unique_urls),
            "unique_images": len(unique_urls),
            "candidates_classified": len(candidates),
            "candidates": classifications,
        },
    }
    coll.update_one({"_id": _id}, {"$set": set_doc})

    addr = doc.get("address") or f"{doc.get('STREET_NO_1')} {doc.get('STREET_NAME')} {doc.get('STREET_TYPE')}"

    # Optionally download yes-classified images so we can spot-check
    if download_dir and yes_urls:
        download_dir.mkdir(parents=True, exist_ok=True)
        for i, u in enumerate(yes_urls):
            try:
                r = requests.get(u, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    safe_addr = str(addr).replace("/", "_").replace(" ", "_")[:40]
                    out = download_dir / f"{_id}_{safe_addr}_yes_{i+1}.png"
                    out.write_bytes(r.content)
            except Exception:
                pass

    return {
        "_id": str(_id),
        "address": addr,
        "total_images": len(unique_urls),
        "unique_images": len(unique_urls),
        "candidates_classified": len(candidates),
        "yes_count": len(yes_urls),
        "yes_positions": [c["position"] for c in classifications if c["verdict"] == "YES"],
        "errors_count": sum(1 for c in classifications if c["verdict"] == "ERROR"),
        "status": "OK",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburb", default="robina")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--all", action="store_true", help="Process every eligible record")
    ap.add_argument("--tail", type=int, default=3, help="Classify last N images (default 3)")
    ap.add_argument("--all-images", action="store_true",
                    help="Classify every unique image URL in each record (overrides --tail)")
    ap.add_argument("--min-images", type=int, default=5, help="Skip records with < N v2 images")
    ap.add_argument("--workers", type=int, default=1,
                    help="Records to process concurrently (default 1)")
    ap.add_argument("--image-workers", type=int, default=5,
                    help="Per-record image classifications in parallel (default 5)")
    ap.add_argument("--download-yes", action="store_true",
                    help="Download classified-YES images to /tmp/fp_extracted for visual check")
    ap.add_argument("--force", action="store_true", help="Re-classify even if already done")
    args = ap.parse_args()

    # Configure logging so background runs stream nicely
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        stream=sys.stdout,
    )

    db = get_client()["Gold_Coast"]
    coll = db[args.suburb]

    # Eligible = records with images from ANY source (v2 + apr01 sidecars + legacy)
    # — not just scraped_data_v2.image_count which is too narrow.
    HAS_ANY_IMAGE = {"$or": [
        {"scraped_data_v2.image_urls.0": {"$exists": True}},
        {"scraped_data_apr01_recovered.images.0": {"$exists": True}},
        {"scraped_data_recently_sold_apr01_recovered.images.0": {"$exists": True}},
        {"scraped_data_for_sale_apr01_recovered.images.0": {"$exists": True}},
        {"property_images_original.0": {"$exists": True}},
        {"scraped_property_images.0": {"$exists": True}},
    ]}
    query: dict[str, Any] = {"$and": [HAS_ANY_IMAGE]}
    if not args.force:
        query["$and"].append({"floor_plans_v2_extracted_at": {"$in": [None, ""]}})

    total_eligible = coll.count_documents(query)
    print(f"Eligible {args.suburb} records (>= {args.min_images} v2 images, not yet classified): {total_eligible}")

    proj = {
        "_id": 1, "address": 1, "STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1,
        "scraped_data_v2.image_urls": 1, "scraped_data_v2.hero_image_url": 1,
        "scraped_data_v2.image_count": 1,
        "scraped_data_apr01_recovered.images": 1,
        "scraped_data_recently_sold_apr01_recovered.images": 1,
        "scraped_data_for_sale_apr01_recovered.images": 1,
        "property_images_original": 1, "scraped_property_images": 1, "property_images": 1,
    }
    cursor = coll.find(query, proj)
    if not args.all:
        cursor = cursor.limit(args.limit)

    download_dir = Path("/tmp/fp_extracted") if args.download_yes else None
    if download_dir:
        download_dir.mkdir(parents=True, exist_ok=True)
        # Clean from prior runs
        for p in download_dir.iterdir():
            try:
                p.unlink()
            except Exception:
                pass

    tail_arg = None if args.all_images else args.tail
    docs = list(cursor)  # Realise before threading so cursor isn't shared
    logging.info("Queued %d records (tail=%s, workers=%d, image_workers=%d)",
                 len(docs), tail_arg or "ALL", args.workers, args.image_workers)

    results = []
    t0 = time.time()
    counter_lock = threading.Lock()
    done_count = [0]
    total_yes = [0]

    def _worker(idx_doc):
        idx, doc = idx_doc
        try:
            row = process_record(coll, doc, tail_arg, args.image_workers, download_dir)
        except Exception as e:
            row = {"_id": str(doc["_id"]), "status": "EXCEPTION", "error": str(e)}
        with counter_lock:
            done_count[0] += 1
            yc = row.get("yes_count", 0)
            total_yes[0] += yc
            n = done_count[0]
            if n % 25 == 0 or n == len(docs):
                elapsed = time.time() - t0
                rps = n / elapsed if elapsed > 0 else 0
                eta_sec = (len(docs) - n) / rps if rps > 0 else 0
                logging.info(
                    "progress: %d/%d  yes_records=%d  yes_imgs=%d  elapsed=%.0fs  ETA=%.0fs",
                    n, len(docs),
                    sum(1 for r in results if r.get("yes_count", 0) > 0) + (1 if yc > 0 else 0),
                    total_yes[0], elapsed, eta_sec,
                )
        return row

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(_worker, (i, d)) for i, d in enumerate(docs, 1)]
            for fut in as_completed(futures):
                results.append(fut.result())
    else:
        for i, doc in enumerate(docs, 1):
            results.append(_worker((i, doc)))

    elapsed = time.time() - t0
    n_yes = sum(1 for r in results if r.get("yes_count", 0) > 0)
    n_none = sum(1 for r in results if r.get("status") == "OK" and r.get("yes_count", 0) == 0)
    n_err = sum(1 for r in results if r.get("status") not in ("OK", "NO_V2_IMAGES"))
    total_yes_imgs = sum(r.get("yes_count", 0) for r in results)
    total_classified = sum(r.get("candidates_classified", 0) for r in results)
    logging.info("=" * 60)
    logging.info("DONE in %.1fs. Records processed: %d", elapsed, len(results))
    logging.info("Records with >=1 floor plan found: %d (%.0f%%)", n_yes, 100*n_yes/max(len(results),1))
    logging.info("Records with 0 floor plans found:  %d", n_none)
    logging.info("Records with errors:               %d", n_err)
    logging.info("Total floor plan images extracted: %d", total_yes_imgs)
    logging.info("Total images classified:           %d", total_classified)
    if download_dir:
        print(f"Yes-classified images downloaded to: {download_dir}")

    # Save full results json
    out = REPO_ROOT / "logs" / "coverage" / f"fp_extraction_{args.suburb}_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, default=str, indent=2))
    print(f"Full results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

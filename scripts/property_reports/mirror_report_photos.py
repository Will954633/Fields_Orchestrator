#!/usr/bin/env python3
"""
mirror_report_photos.py — mirror a mini-site report's photos to our own blob.

Some `system_monitor.property_reports` docs stored `property.photos` as Domain
`rimh2.domainstatic.com.au` thumbnails (~150px) — older listings whose URL format
(`w800-h600-<id>` prefix) slipped past the resolver's full-res rewrite. The
mini-site renders those blank. This script:

  1. Rewrites each thumbnail to its full-res `bucket-api.domain.com.au` original.
  2. Downloads it (following redirects) to our permanent blob store
     `/data/blobs/property-images/reports/<suburb>/<property_id>/NN.jpg`
     (served at https://blobs.fieldsestate.com.au/...).
  3. Repoints `property.photos[i].url` at the blob copy, preserving role/caption
     and keeping the original Domain URL in `source_url`.

Idempotent: photos already on blobs.fieldsestate.com.au are skipped. The website
also applies toFullResUrl at serve time (property-report.mjs) as a catch-all, so
this is about permanence — not depending on Domain's CDN.

USAGE:
  python3 scripts/property_reports/mirror_report_photos.py --dry-run
  python3 scripts/property_reports/mirror_report_photos.py --slug 5-cedarwood-crescent-robina
  python3 scripts/property_reports/mirror_report_photos.py --all-thumbnails
"""
import os
import sys
import argparse

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.db import get_client  # noqa: E402

BLOB_ROOT = "/data/blobs/property-images/reports"
BLOB_HOST = "https://blobs.fieldsestate.com.au/property-images/reports"
RIMH2 = "rimh2.domainstatic.com.au"


def to_full_res(url: str) -> str:
    """Mirror of the website's toFullResUrl (shared-utils.mjs)."""
    if not isinstance(url, str) or RIMH2 not in url:
        return url
    if "hpg-unique-data" in url:
        return url
    tail = url.rsplit("/", 1)[-1]
    if not tail or "http" in tail:
        return url
    return "https://bucket-api.domain.com.au/v1/bucket/image/" + tail


def download(url: str) -> bytes:
    r = requests.get(url, timeout=45, allow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (Fields blob mirror)"})
    r.raise_for_status()
    if not r.content or len(r.content) < 1024:
        raise ValueError(f"suspiciously small ({len(r.content)}B)")
    return r.content


def process(doc, col, dry):
    slug = doc["slug"]
    suburb = doc.get("suburb_key") or "unknown"
    pid = str(doc.get("property_id") or doc["_id"])
    photos = (doc.get("property") or {}).get("photos") or []
    if not photos:
        print(f"  {slug}: no photos — skip")
        return 0

    out_dir = os.path.join(BLOB_ROOT, suburb, pid)
    changed = 0
    new_photos = []
    for i, p in enumerate(photos):
        url = p.get("url", "")
        if BLOB_HOST.split("//")[1] in url or "blobs.fieldsestate.com.au" in url:
            new_photos.append(p)                      # already mirrored
            continue
        full = to_full_res(url)
        fname = f"{i:02d}.jpg"
        blob_url = f"{BLOB_HOST}/{suburb}/{pid}/{fname}"
        if dry:
            print(f"    [{i}] {p.get('role','gallery'):8} {full[:60]} -> {blob_url}")
            new_photos.append({**p, "url": blob_url, "source_url": url})
            changed += 1
            continue
        try:
            data = download(full)
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, fname), "wb") as f:
                f.write(data)
            new_photos.append({**p, "url": blob_url, "source_url": url})
            changed += 1
            print(f"    [{i}] {p.get('role','gallery'):8} {len(data):>8}B -> {blob_url}")
        except Exception as e:
            print(f"    [{i}] FAILED {full[:60]}: {e} — keeping full-res Domain URL")
            new_photos.append({**p, "url": full, "source_url": url})

    if changed and not dry:
        col.update_one({"_id": doc["_id"]},
                       {"$set": {"property.photos": new_photos}})
    print(f"  {slug}: {changed} photo(s) {'would be ' if dry else ''}mirrored")
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", nargs="+")
    ap.add_argument("--all-thumbnails", action="store_true",
                    help="every report whose property.photos still has a rimh2 thumbnail")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    col = get_client()["system_monitor"]["property_reports"]
    if args.slug:
        docs = list(col.find({"slug": {"$in": args.slug}}))
    elif args.all_thumbnails:
        docs = [d for d in col.find({}, {"slug": 1, "property.photos": 1, "property_id": 1, "suburb_key": 1})
                if any(RIMH2 in (p.get("url") or "")
                       for p in (d.get("property") or {}).get("photos") or [])]
        # re-fetch full docs
        docs = list(col.find({"_id": {"$in": [d["_id"] for d in docs]}}))
    else:
        ap.error("pass --slug <slug...> or --all-thumbnails")

    print(f"{'DRY RUN — ' if args.dry_run else ''}mirroring {len(docs)} report(s):")
    total = sum(process(d, col, args.dry_run) for d in docs)
    print(f"\nDone. {total} photo(s) {'would be ' if args.dry_run else ''}mirrored.")


if __name__ == "__main__":
    main()

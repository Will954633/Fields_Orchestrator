#!/usr/bin/env python3
"""
mirror_offmarket_photos.py — copy live Domain facade photos of OFF-MARKET homes
to our own blob, so we can build owned property cards (an off-market /for-sale-v3).

Off-market houses (listing_status null) still carry Domain CDN photo URLs from when
they were last listed. Those rotate off and aren't ours to republish. This backfill
downloads the live ones and stores owned copies at
    property-images/offmarket_cards/<suburb>/<property_id>/<NN>.jpg
served durably at blobs.fieldsestate.com.au, then records the owned URLs on the doc:
    offmarket_card_photos            : [owned urls]
    offmarket_card_photos_mirrored_at: ISO ts
    offmarket_card_hero              : first owned url

Photo selection follows the site's extractPhotos order (see PROPERTY_DATA_INDEX.md),
filtering the dead Azure host. Verify targets over HTTP, never the VM disk.

Rule 7b: this is a backfill, not a cron — but it still asserts an outcome. If homes
had live Domain URLs on record yet 0 photos mirrored, it EXITS NONZERO (upstream broke,
the population isn't empty).

Usage:
  python3 scripts/mirror_offmarket_photos.py --suburb robina --beds 3 --limit 90
  python3 scripts/mirror_offmarket_photos.py --suburb robina --beds 3 --limit 5 --dry-run
"""
import argparse, os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

import requests
from shared.db import get_gold_coast_db
from shared import blob_storage

DEAD_HOST = "fieldspropertyimages.blob.core.windows.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CONTAINER = "property-images"
DOMAIN_ASSET_ORIGIN = "https://b.domainstatic.com.au/"

def to_full_res(url):
    """Mirror of shared-utils.mjs toFullResUrl: a signed rimh2 thumbnail renders at
    150x100 regardless of the size in its name; the last path segment IS the Domain
    asset token, which b.domainstatic.com.au serves at full res (~1600px). See
    PROPERTY_DATA_INDEX.md / shared-utils PHOTO-QUALITY-01."""
    if not isinstance(url, str):
        return url
    if "bucket-api.domain.com.au" in url:
        tail = url.split("/")[-1]
        return DOMAIN_ASSET_ORIGIN + tail if tail and "http" not in tail else url
    if "rimh2.domainstatic.com.au" not in url:
        return url
    if "hpg-unique-data" in url:  # legacy: segment is a whole URL, can't rewrite
        return url
    tail = url.split("/")[-1]
    if not tail or "http" in tail:
        return url
    return DOMAIN_ASSET_ORIGIN + tail

def photo_candidates(doc):
    """Facade photo URLs in resolution order, dead host filtered, deduped."""
    out = []
    def add(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            u = v.get("url") or v.get("image_url") or v.get("src")
            if u:
                out.append(u)
    if doc.get("domain_hero_image_url"):
        add(doc["domain_hero_image_url"])
    for u in doc.get("domain_image_urls") or []:
        add(u)
    for u in (doc.get("scraped_data_v2") or {}).get("image_urls") or []:
        add(u)
    for src in ("scraped_data_apr01_recovered", "scraped_data_for_sale_apr01_recovered"):
        for im in (doc.get(src) or {}).get("images") or []:
            add(im)
    for u in doc.get("property_images_original") or []:
        add(u)
    seen, clean = set(), []
    for u in out:
        if not u or not u.startswith("http") or DEAD_HOST in u:
            continue
        u = to_full_res(u)  # rewrite rimh2 150px thumbnails to full-res origin
        if u in seen:
            continue
        seen.add(u)
        clean.append(u)
    return clean

def fetch(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
        if r.status_code < 400 and r.content:
            return r.content
    except Exception:
        pass
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default="robina")
    ap.add_argument("--beds", type=int, default=3)
    ap.add_argument("--limit", type=int, default=90)
    ap.add_argument("--max-photos", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true",
                    help="re-mirror homes already done")
    a = ap.parse_args()

    db = get_gold_coast_db()
    col = db[a.suburb]
    q = {"listing_status": None, "property_type": "House", "bedrooms": a.beds}
    if not a.refresh:
        q["offmarket_card_photos"] = {"$exists": False}

    # Rank by photo availability so a small --limit still yields good cards.
    docs = list(col.find(q))
    ranked = []
    for d in docs:
        cands = photo_candidates(d)
        if cands:
            ranked.append((len(cands), d, cands))
    ranked.sort(key=lambda t: -t[0])
    had_urls = len(ranked)
    ranked = ranked[: a.limit]

    print(f"{a.beds}-bed off-market {a.suburb}: {len(docs)} homes, "
          f"{had_urls} with live-host photo URLs; mirroring top {len(ranked)}"
          f"{' (DRY RUN)' if a.dry_run else ''}\n")

    homes_done = photos_up = homes_failed = 0
    for n_cands, d, cands in ranked:
        pid = str(d["_id"])
        addr = (d.get("address") or "?")[:45]
        owned = []
        for i, url in enumerate(cands[: a.max_photos]):
            data = fetch(url)
            if not data:
                continue
            if a.dry_run:
                owned.append(f"DRY:{url[:40]}")
                continue
            blob_name = f"offmarket_cards/{a.suburb}/{pid}/{i:02d}.jpg"
            pub = blob_storage.upload(CONTAINER, blob_name, data, content_type="image/jpeg")
            if pub:
                owned.append(pub)
        if owned:
            homes_done += 1
            photos_up += len(owned)
            if not a.dry_run:
                col.update_one({"_id": d["_id"]}, {"$set": {
                    "offmarket_card_photos": owned,
                    "offmarket_card_hero": owned[0],
                    "offmarket_card_photos_mirrored_at": datetime.now(timezone.utc).isoformat(),
                }})
            print(f"  ✓ {addr:45} {len(owned)}/{min(n_cands,a.max_photos)} photos")
        else:
            homes_failed += 1
            print(f"  ✗ {addr:45} 0 photos (all URLs dead)")

    print(f"\nDONE: {homes_done} homes mirrored, {photos_up} photos, {homes_failed} failed")

    # Rule 7b: input existed but nothing landed -> upstream broke, not empty.
    if had_urls > 0 and homes_done == 0 and not a.dry_run:
        print("ERROR: homes had live photo URLs but 0 mirrored — upstream broken", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

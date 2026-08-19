"""
build_demo_photos.py — mirror + redact the public demo report's imagery.

Companion to build_public_demo.py. Text redaction does not touch pixels, and on
the first demo subject the pixels were the strongest identifier in the document:
the hero listing photo showed the street number on the plinth beside the front
door, in focus and legible.

Policy, derived from looking at all seven source photos:

  HERO      the facade shot, destructively blurred. Blur is the demo's design
            language ("this is someone's private report"), and at hero scale it
            sits behind text anyway. Destructive by construction — downsample to
            1/16 and back, THEN gaussian — so the house number is not recoverable
            by sharpening. A cosmetic CSS blur would have shipped the original.
  GALLERY   outdoor / architectural frames only. Interiors are excluded, not
            because they locate the house (they don't) but because they show the
            occupants' family photographs and personal effects, and a listing on
            Domain is a different context from a page we buy cold traffic to.

Everything is rehosted to our own blob store. Pointing an ad at a page that
hot-links Domain's CDN is the one exposure here with a named counterparty.

Usage:
    python3 -m scripts.property_reports.build_demo_photos \
        --source-slug 21-royal-links-drive-robina \
        --demo-slug sample-robina-house \
        --hero 0 --gallery 6,3,5 \
        --out /tmp/demo_photos.json
"""
import argparse
import json
import os
import sys

import requests
from PIL import Image, ImageFilter

from shared.db import get_client
from shared.env import load_env

BLOB_ROOT = "/data/blobs/property-images/reports/demo"
BLOB_HOST = "https://blobs.fieldsestate.com.au/property-images/reports/demo"

# Destructive blur: the image is reduced to this fraction of its width and
# scaled back before the gaussian pass. Detail below this scale is gone from the
# file, not merely hidden — sharpening cannot recover the street number.
_PIXELATE_FACTOR = 16
_GAUSSIAN_RADIUS = 12
_MAX_EDGE = 2000


def _fetch(url):
    r = requests.get(url, timeout=60, allow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (Fields demo build)"})
    r.raise_for_status()
    if len(r.content) < 1024:
        raise ValueError(f"suspiciously small image ({len(r.content)}B) from {url}")
    return r.content


def _load(raw_path):
    im = Image.open(raw_path).convert("RGB")
    if max(im.size) > _MAX_EDGE:
        im.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.LANCZOS)
    return im


def destructive_blur(im):
    w, h = im.size
    small = im.resize((max(1, w // _PIXELATE_FACTOR), max(1, h // _PIXELATE_FACTOR)),
                      Image.BILINEAR)
    back = small.resize((w, h), Image.BILINEAR)
    return back.filter(ImageFilter.GaussianBlur(_GAUSSIAN_RADIUS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-slug", required=True)
    ap.add_argument("--demo-slug", required=True)
    ap.add_argument("--hero", type=int, required=True,
                    help="source photo index to use as the blurred hero")
    ap.add_argument("--gallery", required=True,
                    help="comma-separated source photo indices, in display order")
    ap.add_argument("--out", required=True, help="path to write the photos JSON")
    ap.add_argument("--write-blobs", action="store_true",
                    help="write files to the blob store (otherwise a local preview dir)")
    args = ap.parse_args()

    load_env()
    db = get_client()["system_monitor"]
    src = db.property_reports.find_one({"slug": args.source_slug}, {"property.photos": 1})
    if not src:
        sys.exit(f"source report not found: {args.source_slug}")
    photos = src.get("property", {}).get("photos") or []
    if not photos:
        sys.exit("source report has no photos")

    dest_dir = (os.path.join(BLOB_ROOT, args.demo_slug) if args.write_blobs
                else os.path.join("/tmp/demo_blobs", args.demo_slug))
    os.makedirs(dest_dir, exist_ok=True)
    raw_dir = os.path.join("/tmp/demo_raw", args.demo_slug)
    os.makedirs(raw_dir, exist_ok=True)

    gallery_idx = [int(x) for x in args.gallery.split(",") if x.strip()]
    plan = [(args.hero, "hero", True)] + [(i, "gallery", False) for i in gallery_idx]

    out = []
    for n, (idx, role, blur) in enumerate(plan):
        if idx >= len(photos):
            sys.exit(f"source photo index {idx} out of range (have {len(photos)})")
        url = photos[idx]["url"]
        raw = os.path.join(raw_dir, f"src{idx:02d}.jpg")
        if not os.path.exists(raw):
            with open(raw, "wb") as fh:
                fh.write(_fetch(url))
        im = _load(raw)
        if blur:
            im = destructive_blur(im)
        name = f"{n:02d}{'_blurred' if blur else ''}.jpg"
        path = os.path.join(dest_dir, name)
        im.save(path, quality=86, optimize=True)
        out.append({
            "url": f"{BLOB_HOST}/{args.demo_slug}/{name}",
            "role": role,
            "redaction": "destructive_blur" if blur else "none",
            # NOTE: source_url is deliberately omitted. mirror_report_photos.py
            # keeps it for provenance, but on the demo doc it would restore the
            # Domain listing id — i.e. the address — into the public payload.
        })
        print(f"  [{n}] src#{idx} {role:<7} {'BLURRED' if blur else 'clean  '} "
              f"{im.size[0]}x{im.size[1]} -> {path}")

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n✓ {len(out)} photos ({'blob store' if args.write_blobs else 'LOCAL PREVIEW'})")
    print(f"✓ wrote {args.out}")
    if not args.write_blobs:
        print("\n(preview only — pass --write-blobs to publish to the blob store)")


if __name__ == "__main__":
    main()

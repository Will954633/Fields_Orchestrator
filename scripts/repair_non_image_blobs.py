#!/usr/bin/env python3
"""
Repair blobs that carry an image extension but do not contain an image.

Background (2026-08-13, see 15_On_Market/HANDOFF_two_live_defects.md):
Domain's image list for a listing can contain a URL that was never an image —
a Matterport 3D Showcase page, a video embed. `download_images_to_blob.py`
fetched those successfully (HTTP 200), and `blob_storage.upload` wrote the
returned HTML to a `.jpg` with a hard-coded `content_type='image/jpeg'`.
Nothing inspected the bytes, so an HTML page became a "photo" and the gallery
rendered a broken image.

The write path is now guarded (`blob_storage.sniff_image_format` refuses a
non-image payload declared as `image/*`, and the downloader skips known tour
hosts up front), so no NEW impostors can be created. This script cleans up the
ones already on disk and in the database.

What it does per affected blob:
  1. Confirms the file is genuinely not an image (magic-byte sniff, not the
     extension and not `file`).
  2. Removes the matching URL from the document's `property_images` /
     `floor_plans` array — by URL match, NEVER by index. The arrays are already
     not 1:1 with `*_original` (failed downloads collapse the list), so index
     alignment cannot be assumed.
  3. Optionally records the discarded source URL as a virtual tour on the
     document, so genuinely useful content is not simply thrown away.
  4. Moves the bad blob aside to `<path>.notanimage` rather than deleting it,
     so the repair is reversible.

⚠ Matterport source URLs carry an `auth=Bearer …` token. This script never
prints a raw source URL — tokens are redacted in all output.

USAGE:
  python3 scripts/repair_non_image_blobs.py --scan                # find + report only
  python3 scripts/repair_non_image_blobs.py --scan --root /data/blobs/property-images/sold
  python3 scripts/repair_non_image_blobs.py --dry-run             # show planned repairs
  python3 scripts/repair_non_image_blobs.py --apply               # perform them
  python3 scripts/repair_non_image_blobs.py --apply --keep-tour   # + record virtual_tour_url
"""
import os
import re
import sys
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from shared.env import load_env            # type: ignore
from shared.db import get_client           # type: ignore
from shared.blob_storage import sniff_image_format, _looks_like_markup  # type: ignore

DEFAULT_ROOT = '/data/blobs/property-images'
PUBLIC_BASE = 'https://blobs.fieldsestate.com.au/property-images'
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

_TOKEN_RE = re.compile(r'(auth=Bearer[^&\s]*|[?&](token|sig|signature|key)=[^&\s]*)', re.I)


def redact(url):
    """Strip credentials from a URL before it is printed or logged."""
    if not isinstance(url, str):
        return str(url)
    return _TOKEN_RE.sub('<REDACTED>', url)


def title_of(data):
    m = re.search(rb'<title[^>]*>(.*?)</title>', data[:8192], re.I | re.S)
    return m.group(1).decode('utf-8', 'replace').strip()[:90] if m else ''


def scan(root, workers=4):
    """Return [(path, size, kind, title)] for every image-extension file that
    is not actually an image."""
    paths = [p for p in Path(root).rglob('*')
             if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stat().st_size > 1024]
    print(f"Scanning {len(paths):,} image-extension files under {root} …", flush=True)

    def check(p):
        try:
            with open(p, 'rb') as f:
                head = f.read(8192)
        except Exception:
            return None
        if sniff_image_format(head) is not None:
            return None
        kind = 'html' if _looks_like_markup(head) else 'unknown'
        return (p, p.stat().st_size, kind, title_of(head))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return [r for r in ex.map(check, paths) if r]


def blob_public_url(path, root):
    return f"{PUBLIC_BASE}/{Path(path).relative_to(root).as_posix()}"


def locate_doc(client, path, root):
    """Resolve a blob path back to its Mongo document.

    Path shape: {db_label}/{suburb}/{property_id}/{photos|floor_plans}/{date}/{nn}.jpg
    """
    rel = Path(path).relative_to(root).parts
    if len(rel) < 4:
        return None
    _db_label, suburb, property_id, category = rel[0], rel[1], rel[2], rel[3]
    from bson import ObjectId
    try:
        oid = ObjectId(property_id)
    except Exception:
        return None
    coll = client['Gold_Coast'][suburb]
    doc = coll.find_one({'_id': oid})
    if not doc:
        return None
    field = 'property_images' if category == 'photos' else 'floor_plans'
    return {'coll': coll, 'doc': doc, 'field': field, 'suburb': suburb}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=DEFAULT_ROOT, help='Blob subtree to scan')
    ap.add_argument('--scan', action='store_true', help='Report affected blobs and exit')
    ap.add_argument('--dry-run', action='store_true', help='Show planned repairs, change nothing')
    ap.add_argument('--apply', action='store_true', help='Perform the repairs')
    ap.add_argument('--keep-tour', action='store_true',
                    help='Record the discarded source URL as virtual_tour_url on the document')
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()

    if not (args.scan or args.dry_run or args.apply):
        ap.error('pick one of --scan / --dry-run / --apply')

    load_env()
    found = scan(args.root, args.workers)

    print(f"\n{'=' * 74}\nNON-IMAGE BLOBS: {len(found)}\n{'=' * 74}")
    for p, size, kind, title in found:
        print(f"  {kind:>7}  {size:>8,}B  {title or '(no title)'}")
        print(f"           {p}")
    if not found:
        print("  none — nothing to repair")
        return
    if args.scan:
        return

    client = get_client()
    repaired = skipped = 0

    for p, size, kind, title in found:
        info = locate_doc(client, p, args.root)
        if not info:
            print(f"\n  ! could not resolve a document for {p} — left in place")
            skipped += 1
            continue

        coll, doc, field = info['coll'], info['doc'], info['field']
        bad_url = blob_public_url(p, args.root)
        current = doc.get(field) or []
        if bad_url not in current:
            print(f"\n  · {doc.get('address', doc['_id'])}: blob already absent from {field}")
            skipped += 1
            continue

        # Match by URL, never by index — the arrays are not 1:1 with *_original.
        new_list = [u for u in current if u != bad_url]

        # The source URL that produced this file, for optional tour capture.
        idx = int(Path(p).stem)
        originals = doc.get(f'{field}_original') or []
        source = originals[idx] if idx < len(originals) else None

        print(f"\n  {doc.get('address', doc['_id'])} [{info['suburb']}]")
        print(f"    {field}: {len(current)} -> {len(new_list)} (removing 1 non-image)")
        if source:
            print(f"    source was: {redact(source)}")

        if args.dry_run:
            continue

        update = {'$set': {field: new_list}}
        if args.keep_tour and source and 'matterport' in source.lower():
            update['$set']['virtual_tour_url'] = source
            print("    + recording virtual_tour_url")

        coll.update_one({'_id': doc['_id']}, update)
        Path(p).rename(str(p) + '.notanimage')   # reversible; not a delete
        repaired += 1

    print(f"\n{'=' * 74}")
    print(f"{'Planned' if args.dry_run else 'Repaired'}: "
          f"{len(found) - skipped if args.dry_run else repaired}   Skipped: {skipped}")
    print(f"{'=' * 74}")
    client.close()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
enhance_property_photos.py — one command to twilight-enhance every photo of a home.

Pulls a property's full-resolution listing photos from our own blob CDN, uses
Google Gemini vision to CLASSIFY each shot (so we know what it is), routes each to
the right twilight style automatically, generates the enhanced image with the
Gemini 2.5 Flash Image model ("nano-banana"), and writes an annotated manifest
plus a labelled contact sheet.

    # by address (collection inferred from the suburb):
    python3 enhance_property_photos.py --address "93 Burleigh Street, Burleigh Waters"

    # by id (fastest, unambiguous):
    python3 enhance_property_photos.py --id 690bd81b8b8f546592617fbb --collection burleigh_waters

    # classify only, no image generation (cheap dry run to check the annotation):
    python3 enhance_property_photos.py --id <id> --collection <c> --classify-only

    # reuse photos already downloaded (skip the CDN pull):
    python3 enhance_property_photos.py --id <id> --collection <c> --no-download

Output lands in ./<address-slug>/ :
    original/NN.jpg              full-res source
    enhanced/NN__<cat>.jpg       twilight-enhanced (skips floor plans / diagrams)
    manifest.json                per-photo annotation + what was done
    contact_sheet.jpg            labelled before/after grid

Requires: GOOGLE_GEMINI_API_KEY in the environment (source the .env first).
Styles live in twilight_edit.py and are imported here — single source of truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

import requests
from google import genai
from google.genai import types
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from twilight_edit import STYLES  # noqa: E402  (default / subtle / dramatic / interior / interior_twilight)

HERE = Path(__file__).resolve().parent
IMAGE_MODEL = "gemini-2.5-flash-image"      # nano-banana — generates the enhanced photo
VISION_MODEL = "gemini-2.5-flash"           # cheap/fast — classifies the photo

# ── category → which twilight style to apply. None = leave the photo alone. ──
CATEGORY_STYLE = {
    "exterior_front":   "default",
    "exterior_rear":    "default",
    "exterior_other":   "default",
    "alfresco_outdoor": "default",
    "aerial":           "default",
    "living":           "interior_twilight",
    "kitchen":          "interior_twilight",
    "dining":           "interior_twilight",
    "bedroom":          "interior_twilight",
    "bathroom":         "interior_twilight",
    "laundry":          "interior_twilight",
    "interior_other":   "interior_twilight",
    "floor_plan":       None,   # never enhance a floor plan
    "boundary_diagram": None,   # never enhance an aerial site-boundary overlay
    "other":            None,
}
CATEGORIES = list(CATEGORY_STYLE.keys())

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "room_or_subject": {"type": "string"},   # e.g. "master bedroom", "kitchen", "front facade"
        "caption": {"type": "string"},            # one short human caption for the shot
        "twilight_suitable": {"type": "boolean"}, # false for e.g. tightly-cropped wet rooms
        "notes": {"type": "string"},
    },
    "required": ["category", "room_or_subject", "caption", "twilight_suitable"],
}

_CLASSIFY_PROMPT = (
    "You are cataloguing a real-estate listing photo. Identify what the photo shows. "
    "category must be one of the allowed values. Use 'boundary_diagram' for an aerial "
    "with the lot boundary drawn on it, 'aerial' for a plain drone shot, 'floor_plan' "
    "for a plan drawing. 'alfresco_outdoor' is a covered patio/outdoor entertaining area. "
    "Give a short human caption (e.g. 'Master bedroom with ensuite', 'Front facade from "
    "street', 'Kitchen looking to breakfast bar'). Set twilight_suitable=false only if a "
    "dusk relight would look odd (e.g. a tightly cropped bathroom vanity, a floor plan)."
)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def _orchestrator_root() -> Path:
    """Walk up to the Fields_Orchestrator root so `shared.db` imports from anywhere."""
    p = HERE
    for _ in range(8):
        if (p / "shared" / "db.py").exists():
            return p
        p = p.parent
    return Path("/home/fields/Fields_Orchestrator")


def resolve_doc(args):
    """Return (doc, collection_name). Import kept local so --help works without a DB."""
    sys.path.insert(0, str(_orchestrator_root()))
    from shared.db import get_gold_coast_db
    import bson
    db = get_gold_coast_db()
    if args.id:
        coll = args.collection or _infer_collection(args.address or "")
        if not coll:
            sys.exit("Pass --collection with --id (or an --address to infer it).")
        doc = db[coll].find_one({"_id": bson.ObjectId(args.id)})
        return doc, coll
    if not args.address:
        sys.exit("Provide --address or --id.")
    coll = args.collection or _infer_collection(args.address)
    if not coll:
        sys.exit("Could not infer collection from address — pass --collection.")
    rx = {"$regex": re.escape(args.address.split(",")[0].strip()), "$options": "i"}
    doc = db[coll].find_one({"listing_status": "for_sale",
                             "$or": [{"address": rx}, {"display_address": rx}]})
    if not doc:
        doc = db[coll].find_one({"$or": [{"address": rx}, {"display_address": rx}]})
    return doc, coll


def _infer_collection(address: str) -> str | None:
    """Map the suburb in a free-text address to a Gold_Coast collection name."""
    a = address.lower()
    for suburb in ("burleigh waters", "varsity lakes", "robina", "merrimac", "carrara",
                   "burleigh heads", "miami", "mermaid waters", "palm beach"):
        if suburb in a:
            return suburb.replace(" ", "_")
    return None


def blob_urls(doc) -> list[str]:
    ih = doc.get("image_history") or []
    if ih and ih[-1].get("urls"):
        return list(ih[-1]["urls"])
    return list(doc.get("domain_image_urls") or [])


def download_and_dedup(urls: list[str], dest: Path) -> list[Path]:
    """Download every url, drop perceptual duplicates (blob CDN mixes size derivatives),
    keep the highest-resolution instance of each. Returns saved paths in order."""
    dest.mkdir(parents=True, exist_ok=True)
    best: dict[str, tuple[int, bytes]] = {}     # ahash -> (pixels, bytes)
    order: list[str] = []
    for u in urls:
        try:
            b = requests.get(u, timeout=30).content
            im = Image.open(BytesIO(b)).convert("RGB")
        except Exception:
            continue
        h = _ahash(im)
        px = im.width * im.height
        if h not in best:
            order.append(h)
        if h not in best or px > best[h][0]:
            best[h] = (px, b)
    saved = []
    for i, h in enumerate(order):
        p = dest / f"{i:02d}.jpg"
        p.write_bytes(best[h][1])
        saved.append(p)
    return saved


def _ahash(im: Image.Image) -> str:
    g = im.convert("L").resize((8, 8), Image.BILINEAR)
    px = list(g.getdata())
    avg = sum(px) / len(px)
    bits = "".join("1" if p >= avg else "0" for p in px)
    return hashlib.md5(bits.encode()).hexdigest()


def classify(path: Path, client: genai.Client) -> dict:
    im = Image.open(path)
    if max(im.size) > 1024:
        im.thumbnail((1024, 1024))
    resp = client.models.generate_content(
        model=VISION_MODEL,
        contents=[_CLASSIFY_PROMPT, im],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_CLASSIFY_SCHEMA,
        ),
    )
    try:
        return json.loads(resp.text)
    except Exception:
        return {"category": "other", "room_or_subject": "unknown",
                "caption": "unclassified", "twilight_suitable": False, "notes": "parse-fail"}


def enhance(path: Path, style: str, client: genai.Client, out: Path) -> bool:
    im = Image.open(path)
    if max(im.size) > 1600:
        im.thumbnail((1600, 1600))
    for attempt in range(4):
        try:
            resp = client.models.generate_content(model=IMAGE_MODEL, contents=[STYLES[style], im])
            for part in resp.candidates[0].content.parts:
                data = getattr(getattr(part, "inline_data", None), "data", None)
                if data:
                    Image.open(BytesIO(data)).convert("RGB").save(out, quality=92)
                    return True
        except Exception as e:
            if attempt == 3:
                print(f"      ! {out.name}: {e}")
    return False


def contact_sheet(rows: list[dict], base: Path, out: Path) -> None:
    cells = []
    for r in rows:
        a = Image.open(base / "original" / r["file"]); a.thumbnail((520, 360))
        if r.get("enhanced"):
            b = Image.open(base / "enhanced" / r["enhanced"]); b.thumbnail((520, 360))
        else:
            b = Image.new("RGB", (a.width, a.height), (40, 40, 40))
        pad, lab = 6, 30
        w = a.width + b.width + pad * 3
        h = max(a.height, b.height) + lab + pad
        cell = Image.new("RGB", (w, h), (24, 24, 24))
        cell.paste(a, (pad, lab)); cell.paste(b, (a.width + pad * 2, lab))
        d = ImageDraw.Draw(cell)
        d.text((pad, 4), f"{r['file']}  {r['category']} — {r['caption']}"[:90], fill=(255, 210, 80))
        d.text((pad, 16), ("→ " + r["style"]) if r.get("style") else "→ (kept as-is)",
               fill=(120, 220, 255))
        cells.append(cell)
    if not cells:
        return
    cw = max(c.width for c in cells)
    ch = sum(c.height for c in cells) + 6 * len(cells)
    sheet = Image.new("RGB", (cw, ch), (0, 0, 0))
    y = 0
    for c in cells:
        sheet.paste(c, (0, y)); y += c.height + 6
    sheet.save(out, quality=85)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address")
    ap.add_argument("--id")
    ap.add_argument("--collection")
    ap.add_argument("--outdir", help="override output folder (default: ./<address-slug>)")
    ap.add_argument("--classify-only", action="store_true", help="annotate only, don't generate")
    ap.add_argument("--no-download", action="store_true", help="reuse existing original/ folder")
    ap.add_argument("--only", help="comma-separated image numbers to process, e.g. 03,09,26")
    args = ap.parse_args()

    key = os.environ.get("GOOGLE_GEMINI_API_KEY")
    if not key:
        sys.exit("GOOGLE_GEMINI_API_KEY not set — `set -a && source .env && set +a` first.")
    client = genai.Client(api_key=key)

    doc, coll = resolve_doc(args)
    if not doc:
        sys.exit("Property not found.")
    address = doc.get("address") or doc.get("display_address") or str(doc["_id"])
    base = Path(args.outdir) if args.outdir else HERE / slugify(address)
    orig = base / "original"
    print(f"■ {address}  [{coll}]  → {base}")

    if args.no_download:
        files = sorted(orig.glob("*.jpg"))
    else:
        urls = blob_urls(doc)
        print(f"  pulling {len(urls)} blob urls, de-duplicating…")
        files = download_and_dedup(urls, orig)
    print(f"  {len(files)} unique photos")

    only = set(args.only.split(",")) if args.only else None
    (base / "enhanced").mkdir(exist_ok=True)
    rows = []
    for f in files:
        num = f.stem
        if only and num not in only:
            continue
        meta = classify(f, client)
        cat = meta["category"]
        style = CATEGORY_STYLE.get(cat)
        if style and not meta.get("twilight_suitable", True):
            style = None
        row = {"file": f.name, "num": num, "category": cat,
               "room_or_subject": meta.get("room_or_subject"),
               "caption": meta.get("caption"), "twilight_suitable": meta.get("twilight_suitable"),
               "style": style, "enhanced": None}
        tag = f"{num}  {cat:16s} {meta.get('caption','')[:48]}"
        if style and not args.classify_only:
            out = base / "enhanced" / f"{num}__{cat}.jpg"
            if enhance(f, style, client, out):
                row["enhanced"] = out.name
                print(f"  ✓ {tag}  → {style}")
            else:
                print(f"  ✗ {tag}  → {style} (failed)")
        else:
            print(f"  · {tag}  → {'(' + (style or 'kept') + ', classify-only)' if args.classify_only else 'kept as-is'}")
        rows.append(row)

    (base / "manifest.json").write_text(json.dumps(
        {"address": address, "collection": coll, "id": str(doc["_id"]), "photos": rows},
        indent=2))
    if not args.classify_only:
        contact_sheet(rows, base, base / "contact_sheet.jpg")
    print(f"■ manifest.json + contact_sheet.jpg written to {base}")


if __name__ == "__main__":
    main()

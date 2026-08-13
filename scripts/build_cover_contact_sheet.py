#!/usr/bin/env python3
"""
Contact sheet for pre-warmed report covers.

Verifying 7,730 covers one at a time is not possible; tiling them is. This
builds grid JPEGs (default 24 per sheet) plus a browsable HTML index, so a
whole batch can be scanned in a few screens and the failure modes that matter
show up instantly:

  - a photo of the WRONG house              (the defect the 13TC fallback caused)
  - an uncentred cadastral aerial            (subject is one of five roofs)
  - a hero that is an interior or a sign     (listing photo #1 is not always the facade)
  - a missing or wrong address on the card

Each tile is captioned with the slug and the hero source, because the source is
the strongest predictor of a bad cover — `local_cadastral` is the tier to check
hardest, `auto_apr01` is a real listing photo, `boundary_aerial` is the outlined
parcel and is always the subject.

    python3 scripts/build_cover_contact_sheet.py
    python3 scripts/build_cover_contact_sheet.py --per-sheet 40
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from PIL import Image, ImageDraw  # noqa: E402

COVERS = Path("/data/blobs/off-market-reports/covers")
OUT = Path("/home/fields/Fields_Orchestrator/15_Off-Market/Concepts/Cover_Audit")
TILE_W = 300
CAPTION_H = 34
COLS = 6
BG = (245, 243, 239)
INK = (44, 41, 36)


def hero_sources():
    """slug -> cover_hero tier, from the prewarm's audit record."""
    try:
        from shared.db import get_client
        col = get_client()["system_monitor"]["offmarket_report_covers"]
        return {d["slug"]: (d.get("cover_hero") or "?") for d in col.find({}, {"slug": 1, "cover_hero": 1})}
    except Exception:
        return {}


def build(per_sheet: int):
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("sheet_*.jpg"):
        old.unlink()

    sources = hero_sources()
    files = sorted(COVERS.glob("*.jpg"))
    if not files:
        raise SystemExit("No covers found — has the prewarm run?")

    sheets = []
    for n, start in enumerate(range(0, len(files), per_sheet), 1):
        chunk = files[start:start + per_sheet]
        rows = (len(chunk) + COLS - 1) // COLS
        tile_h = int(TILE_W * 1.414)  # A4
        sheet = Image.new("RGB", (COLS * TILE_W, rows * (tile_h + CAPTION_H)), BG)
        draw = ImageDraw.Draw(sheet)
        for i, f in enumerate(chunk):
            x = (i % COLS) * TILE_W
            y = (i // COLS) * (tile_h + CAPTION_H)
            try:
                im = Image.open(f).convert("RGB").resize((TILE_W - 8, tile_h - 8), Image.LANCZOS)
                sheet.paste(im, (x + 4, y + 4))
            except Exception:
                draw.rectangle([x + 4, y + 4, x + TILE_W - 4, y + tile_h - 4], outline=(200, 0, 0))
            slug = f.stem
            src = sources.get(slug, "?")
            draw.text((x + 6, y + tile_h + 4), slug[:46], fill=INK)
            draw.text((x + 6, y + tile_h + 18), f"hero: {src}", fill=(120, 110, 100))
        path = OUT / f"sheet_{n:03d}.jpg"
        sheet.save(path, quality=86, optimize=True)
        sheets.append((path.name, len(chunk)))
        print(f"  {path}  ({len(chunk)} covers)")

    tally = {}
    for s in files:
        tally[sources.get(s.stem, "?")] = tally.get(sources.get(s.stem, "?"), 0) + 1

    html = [
        "<!doctype html><meta charset='utf-8'><title>Cover audit</title>",
        "<meta name='robots' content='noindex'>",
        "<style>body{background:#f5f3ef;font:15px/1.5 system-ui;margin:0;padding:24px;color:#2c2924}",
        "img{width:100%;height:auto;display:block;margin:0 0 28px;border:1px solid #ddd}",
        "h1{font-weight:600}code{background:#e8e4dd;padding:1px 5px;border-radius:3px}</style>",
        f"<h1>Report cover audit — {len(files)} covers</h1>",
        "<p>Scan for: a photo of the <b>wrong house</b>, an <b>uncentred aerial</b> "
        "(subject is one of several roofs), an <b>interior or signage</b> shot, or a "
        "<b>wrong address</b> on the card.</p>",
        "<p>Hero sources: " + ", ".join(f"<code>{k}</code> {v}" for k, v in sorted(tally.items())) + "</p>",
    ]
    for name, count in sheets:
        html.append(f"<p><b>{name}</b> — {count} covers</p><img src='{name}' loading='lazy'>")
    (OUT / "index.html").write_text("\n".join(html))
    print(f"\n  {OUT/'index.html'}")
    print(f"  https://fieldsestate.com.au/concepts/off-market/cover-audit/index.html")
    print(f"\n  hero sources: {tally}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-sheet", type=int, default=24)
    build(ap.parse_args().per_sheet)

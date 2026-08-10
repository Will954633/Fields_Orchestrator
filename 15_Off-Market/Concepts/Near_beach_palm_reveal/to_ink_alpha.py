#!/usr/bin/env python3
"""
to_ink_alpha.py — turn the light-on-dark engravings into ink that sits on the
V4 report's warm paper.

WHY NOT JUST INVERT TO BLACK-ON-WHITE
───────────────────────────────────────────────────────────────────────────────
A flat black-on-white PNG carries its own WHITE ground, and the V4 page is
#f7f5f1. Dropping one on the page puts a faintly brighter rectangle behind every
drawing — visible on any decent screen, and exactly the artefact that made the
Fields logo look wrong earlier today (its ground was baked-in white with a fully
opaque alpha).

So we do what `build_master.py` already does for the palm: store the drawing as
INK COVERAGE IN THE ALPHA CHANNEL, with RGB set to the page's ink colour. The
drawing then composites onto whatever paper it lands on, keeps its soft hatching
edges, and can be re-tinted without re-rendering.

THE SOURCES ARE LIGHT-ON-DARK, so ink = 1 - luminance. Anything already
black-on-white (palm_bw.png) is detected and passed through without inverting.

    python3 to_ink_alpha.py --preview          # contact sheet on V4 paper
    python3 to_ink_alpha.py --out ink/
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent

# The V4 report's tokens — ink on paper. Kept here so a preview shows the real
# thing rather than black on white.
PAPER = (247, 245, 241)     # --paper  #f7f5f1
INK = (42, 39, 36)          # --ink    #2a2724

HAZE_FLOOR = 0.045   # coverage below this is scanner/model haze, not a stroke
GAMMA = 1.10         # >1 holds the faint hatching back so it does not read grey
CROP_MARGIN = 40     # px of paper kept around the ink bounding box
BBOX_INK = 0.10      # coverage that counts as a stroke when cropping


def ink_coverage(path: Path) -> np.ndarray:
    """0..1 ink coverage. Handles both polarities and any alpha."""
    im = Image.open(path).convert("RGBA")
    arr = np.asarray(im).astype(np.float32) / 255.0
    rgb, a = arr[..., :3], arr[..., 3]

    # ⚠ Transparent regions are GROUND, not ink. The V2 exports carry an alpha
    # channel whose holes are the dark background showing through; compositing
    # them onto the source's own ground first is what stops those holes reading
    # as solid strokes after the inversion.
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    dark_ground = float(np.median(lum[a > 0.5])) < 0.5 if (a > 0.5).any() else True
    lum = lum * a + (0.0 if dark_ground else 1.0) * (1 - a)

    cov = (1.0 - lum) if not dark_ground else lum
    # `dark_ground` means the DRAWING is light: coverage is the luminance itself.

    # ⚠ MEASURE THE GROUND, DO NOT ASSUME IT IS ZERO. Three of the nine sources
    # are flat RGB with a ground around 30/255 rather than pure black, and a
    # fixed haze floor left that residue as ~12% ink across the whole frame — a
    # visible pale rectangle behind the drawing on warm paper, which is the exact
    # artefact this file exists to avoid. The ground is estimated from a border
    # band, which is drawing-free on every one of these compositions.
    b = max(4, min(cov.shape[:2]) // 40)
    border = np.concatenate([cov[:b].ravel(), cov[-b:].ravel(),
                             cov[:, :b].ravel(), cov[:, -b:].ravel()])
    ground = float(np.percentile(border, 85))
    floor = max(HAZE_FLOOR, ground + 0.02)
    cov = np.clip((cov - floor) / (1.0 - floor), 0, 1) ** GAMMA
    return cov


def crop(cov: np.ndarray) -> np.ndarray:
    ys, xs = np.where(cov > BBOX_INK)
    if not len(ys):
        return cov
    y0, y1 = max(0, ys.min() - CROP_MARGIN), min(cov.shape[0], ys.max() + CROP_MARGIN)
    x0, x1 = max(0, xs.min() - CROP_MARGIN), min(cov.shape[1], xs.max() + CROP_MARGIN)
    return cov[y0:y1, x0:x1]


def to_rgba(cov: np.ndarray) -> Image.Image:
    h, w = cov.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = INK
    out[..., 3] = (cov * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def on_paper(img: Image.Image) -> Image.Image:
    bg = Image.new("RGB", img.size, PAPER)
    bg.paste(img, (0, 0), img)
    return bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ink")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    srcs = sorted((HERE / "Other images/Version_2_other_images").glob("*.png"))
    srcs = [s for s in srcs if "glass" not in s.name.lower()]   # not an emblem
    outdir = HERE / args.out
    outdir.mkdir(exist_ok=True)

    made = []
    for s in srcs:
        cov = crop(ink_coverage(s))
        img = to_rgba(cov)
        img.thumbnail((900, 900), Image.LANCZOS)
        dest = outdir / f"{s.stem.lower().replace(' ', '_')}_ink.png"
        img.save(dest, optimize=True)
        made.append((dest, img))
        print(f"  {s.name:<34} -> {dest.name:<34} {img.size}  {dest.stat().st_size//1024}KB")

    if not made:
        raise RuntimeError("no source artwork converted — check the source folder")

    if args.preview:
        cols, cell = 3, 380
        rows = (len(made) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * cell), PAPER)
        for i, (_, img) in enumerate(made):
            t = img.copy()
            t.thumbnail((cell - 40, cell - 40), Image.LANCZOS)
            x = (i % cols) * cell + (cell - t.size[0]) // 2
            y = (i // cols) * cell + (cell - t.size[1]) // 2
            sheet.paste(t, (x, y), t)
        p = HERE / "ink_preview_on_paper.png"
        sheet.save(p)
        print(f"\n  contact sheet on V4 paper: {p}")


if __name__ == "__main__":
    main()

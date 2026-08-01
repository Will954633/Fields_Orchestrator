#!/usr/bin/env python3
"""
build_master.py — prepare the black-and-white master for the pixel-reveal animation.

Takes the source hatch sketch and produces:

  palm_bw.png         flat black-and-white version (white paper, black ink)
  palm_ink_alpha.png  the same ink as an RGBA mask (RGB=black, A=ink coverage)
                      so the animation can composite ink onto any paper colour
                      without painting white squares over the background
  index.html          the animation, with palm_ink_alpha.png inlined as a data
                      URI so the file opens standalone (file:// canvas reads
                      would otherwise taint on getImageData)

Run:  python3 build_master.py
"""

import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "Hatch_Sketch_Pandanas_Palm.png"
TEMPLATE = HERE / "reveal.template.html"

# --- tuning -----------------------------------------------------------------
CROP_MARGIN = 44      # px of paper kept around the ink bounding box
BBOX_INK = 0.06       # ink strength that counts as a stroke when cropping
BBOX_MIN_PX = 3       # ...and this many per row/column, so specks can't set it
BLACK_POINT = 0.0015  # luminance percentile mapped to pure black
CLEAN_FLOOR = 0.014   # ink weaker than this is scanner haze — flatten to paper
GAMMA = 1.06          # >1 on the ink curve holds the light hatch back slightly
UNSHARP = (1.0, 45, 3)  # radius, percent, threshold — keeps fine hatch crisp
# ----------------------------------------------------------------------------


def load_luma(path: Path) -> np.ndarray:
    """Desaturate to luminance. The source is near-monochrome already (mean
    chroma ~2/255) so a straight ITU-R 601 luma is a faithful B&W reading."""
    im = Image.open(path).convert("RGB")
    im = im.filter(ImageFilter.UnsharpMask(*UNSHARP))
    return np.asarray(im.convert("L")).astype(np.float32)


def paper_white(luma: np.ndarray) -> float:
    """The paper is the single most common bright tone, not the brightest pixel.
    Here it sits at 254, so a percentile-based white point would leave a 1/255
    haze over the whole background — enough to make every 'empty' block count as
    ink and to tint the animation's paper grey."""
    bright = luma[luma > 200].astype(np.uint8)
    vals, counts = np.unique(bright, return_counts=True)
    return float(vals[counts.argmax()])


def crop_to_ink(ink: np.ndarray) -> tuple[int, int, int, int]:
    mask = ink > BBOX_INK
    rows = np.where(mask.sum(axis=1) >= BBOX_MIN_PX)[0]
    cols = np.where(mask.sum(axis=0) >= BBOX_MIN_PX)[0]
    h, w = ink.shape
    print(f"  ink bbox      x {cols.min()}-{cols.max()}  y {rows.min()}-{rows.max()}")
    return (
        max(0, int(cols.min()) - CROP_MARGIN),
        max(0, int(rows.min()) - CROP_MARGIN),
        min(w, int(cols.max()) + 1 + CROP_MARGIN),
        min(h, int(rows.max()) + 1 + CROP_MARGIN),
    )


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"source image not found: {SOURCE}")

    print(f"reading {SOURCE.name}")
    luma = load_luma(SOURCE)

    # levels: paper -> pure white, deepest stroke -> pure black
    white = paper_white(luma)
    black = float(np.quantile(luma, BLACK_POINT))
    print(f"  levels        black {black:.0f} -> 0, paper {white:.0f} -> 255")
    ink = np.clip((white - luma) / max(white - black, 1e-6), 0.0, 1.0) ** GAMMA

    # flatten the residual haze so blank paper is exactly blank
    hazy = float((ink > 0) .mean() - (ink >= CLEAN_FLOOR).mean())
    ink[ink < CLEAN_FLOOR] = 0.0
    print(f"  cleaned       {hazy * 100:.1f}% of pixels were sub-{CLEAN_FLOOR} haze")

    x0, y0, x1, y1 = crop_to_ink(ink)
    ink = ink[y0:y1, x0:x1]
    print(f"  cropped to    {x1 - x0} x {y1 - y0} (from {luma.shape[1]} x {luma.shape[0]})")

    norm = 1.0 - ink                     # 0 = black ink, 1 = white paper
    h, w = ink.shape
    print(f"  ink coverage  {(ink > 0).mean() * 100:.1f}% of pixels carry ink")

    # 1. flat black-and-white version (a deliverable on its own)
    flat = Image.fromarray(np.round(norm * 255).astype(np.uint8), mode="L")
    flat.save(HERE / "palm_bw.png", optimize=True)

    # 2. ink-as-alpha mask, used by the animation
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 3] = np.round(ink * 255).astype(np.uint8)
    mask = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    mask.save(buf, format="PNG", optimize=True)
    mask_bytes = buf.getvalue()
    (HERE / "palm_ink_alpha.png").write_bytes(mask_bytes)

    for name in ("palm_bw.png", "palm_ink_alpha.png"):
        kb = (HERE / name).stat().st_size / 1024
        print(f"  wrote         {name}  ({kb:.0f} KB)")

    # 3. inline the mask into the animation so index.html stands alone
    if not TEMPLATE.exists():
        raise SystemExit(f"template not found: {TEMPLATE}")
    data_uri = "data:image/png;base64," + base64.b64encode(mask_bytes).decode("ascii")
    html = (
        TEMPLATE.read_text()
        .replace("{{INK_DATA_URI}}", data_uri)
        .replace("{{IMAGE_W}}", str(w))
        .replace("{{IMAGE_H}}", str(h))
    )
    out = HERE / "index.html"
    out.write_text(html)
    print(f"  wrote         index.html ({out.stat().st_size / 1024:.0f} KB, {w}x{h} inlined)")


if __name__ == "__main__":
    main()

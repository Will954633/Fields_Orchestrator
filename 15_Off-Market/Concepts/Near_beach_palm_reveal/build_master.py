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
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

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
PAPER_COST = 0.03       # smaller = crossing blank paper costs more
# ----------------------------------------------------------------------------


def growth_order(ink: np.ndarray) -> np.ndarray:
    """Geodesic distance from the base of the trunk, travelling THROUGH the ink.

    This is what separates a crystal from a pixel reveal. A pixel reveal orders
    blocks by straight-line distance, so the canopy starts filling before the
    branch that feeds it exists. Here the cost of moving is the inverse of ink
    density, so growth runs up the trunk, out along each branch and only then
    into the fronds — it can only reach a frond by travelling the wood that
    carries it, which is exactly how a crystal accretes.

    Returned normalised 0..1; unreachable pixels are pinned to the far end.
    """
    h, w = ink.shape
    cost = 1.0 / (PAPER_COST + ink)          # cheap through ink, dear across paper

    idx = np.arange(h * w).reshape(h, w)
    rows, cols, vals = [], [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a = idx[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
        b = idx[max(0, dy):h - max(0, -dy), max(0, dx):w - max(0, -dx)]
        ca = cost[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
        cb = cost[max(0, dy):h - max(0, -dy), max(0, dx):w - max(0, -dx)]
        wgt = (ca + cb) * 0.5 * np.hypot(dy, dx)
        rows.append(a.ravel()); cols.append(b.ravel()); vals.append(wgt.ravel())
    r = np.concatenate(rows); c = np.concatenate(cols); v = np.concatenate(vals)
    g = coo_matrix((v, (r, c)), shape=(h * w, h * w)).tocsr()

    # seed: the densest ink at the foot of the trunk
    band = ink[int(h * 0.90):int(h * 0.97)]
    colmass = band.sum(axis=0)
    seed_x = int(np.argmax(np.convolve(colmass, np.ones(31) / 31, mode="same")))
    seed_y = int(h * 0.93)
    print(f"  growth seed  ({seed_x}, {seed_y}) — foot of the trunk")

    d = dijkstra(g, directed=False, indices=seed_y * w + seed_x).reshape(h, w)
    finite = np.isfinite(d)
    dmax = d[finite & (ink > 0.02)].max()
    d = np.where(finite, np.minimum(d, dmax), dmax)
    print(f"  geodesic     max {dmax:.0f} over {finite.mean()*100:.1f}% reachable")
    return np.clip(d / dmax, 0, 1)


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

    # 2. ink-as-alpha mask, used by the animation.
    #    RGB carries the geodesic growth order as a 16-bit value (R high byte,
    #    G low), which the animation uses for the crystal reveal. It costs
    #    nothing — those channels were zeroed before.
    print("  computing growth order (geodesic through the ink)...")
    order = growth_order(ink)
    o16 = np.round(order * 65535).astype(np.uint16)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 0] = (o16 >> 8).astype(np.uint8)
    rgba[..., 1] = (o16 & 0xFF).astype(np.uint8)
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

#!/usr/bin/env python3
"""
cut_glass.py — turn the crack artwork into glass pieces that tile exactly.

This is the step an image generator cannot do. Asking one for 200 shards gives
you 200 handsome pieces that do not fit together, and you see every seam the
moment they move. Instead we take ONE master crack image and cut it, so every
piece is bounded by cracks that were actually drawn and the pane reassembles
with no gaps.

  cracked-glass-v4.png  ->  glass_pieces.json

The cells between the cracks are the pieces. Found by thresholding the cracks,
labelling the black regions they enclose, and tracing each region's outline.
Coordinates are written normalised 0..1 so the front end can scale one cut to
any screen.

Run:  python3 cut_glass.py [--src cracked-glass-v4.png] [--preview]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent

# --- tuning -----------------------------------------------------------------
CRACK_T = 26        # luma above this is a crack, not glass
MIN_AREA = 0.00012  # drop specks: fraction of the frame a piece must cover
EPS = 0.0016        # contour simplification, as a fraction of the frame
CLOSE = 3           # px of dilation to close hairline gaps in the network
# ----------------------------------------------------------------------------


def cut(src: Path, min_area: float, eps: float):
    img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"cannot read {src}")
    h, w = img.shape
    diag = math.hypot(w, h)

    # The cracks. Dilate slightly: the artwork's hairlines break in places, and
    # a single-pixel gap merges two pieces into one and loses the boundary.
    cracks = (img > CRACK_T).astype(np.uint8)
    cracks = cv2.dilate(cracks, np.ones((CLOSE, CLOSE), np.uint8), iterations=1)

    # The glass is everything the cracks enclose.
    glass = (1 - cracks).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(glass, connectivity=4)

    pieces = []
    frame_area = w * h
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area / frame_area < min_area:
            continue
        mask = (labels == i).astype(np.uint8)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        # Simplify: an unsimplified contour is one point per boundary pixel,
        # which is thousands of points per piece and far too heavy to animate.
        approx = cv2.approxPolyDP(c, eps * diag, True).reshape(-1, 2)
        if len(approx) < 3:
            continue
        cx, cy = cents[i]
        pieces.append({
            "poly": [[round(float(px) / w, 5), round(float(py) / h, 5)] for px, py in approx],
            "c": [round(float(cx) / w, 5), round(float(cy) / h, 5)],
            "a": round(float(area) / frame_area, 6),
        })

    # Order matters for the fall: pieces let go outward from the impact, which
    # in this artwork is the centre. Sorting here means the front end never has
    # to compute it.
    for p in pieces:
        p["r"] = round(math.hypot(p["c"][0] - 0.5, p["c"][1] - 0.5), 5)
    pieces.sort(key=lambda p: p["r"])

    return {"w": w, "h": h, "pieces": pieces}


def preview(data, src: Path, out: Path):
    """Colour every piece so you can see the cut actually tiles."""
    w, h = data["w"], data["h"]
    canvas = np.zeros((h, w, 3), np.uint8)
    rng = np.random.default_rng(7)
    for p in data["pieces"]:
        pts = np.array([[int(x * w), int(y * h)] for x, y in p["poly"]], np.int32)
        cv2.fillPoly(canvas, [pts], [int(v) for v in rng.integers(60, 255, 3)])
    base = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    canvas[base > CRACK_T] = (255, 255, 255)
    cv2.imwrite(str(out), canvas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=HERE / "cracked-glass-v4.png")
    ap.add_argument("--out", type=Path, default=HERE / "glass_pieces.json")
    ap.add_argument("--min-area", type=float, default=MIN_AREA)
    ap.add_argument("--eps", type=float, default=EPS)
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()

    data = cut(a.src, a.min_area, a.eps)
    a.out.write_text(json.dumps(data, separators=(",", ":")))
    areas = [p["a"] for p in data["pieces"]]
    verts = [len(p["poly"]) for p in data["pieces"]]
    print(f"{a.src.name}  {data['w']}x{data['h']}")
    print(f"  pieces      {len(data['pieces'])}")
    print(f"  covering    {sum(areas)*100:.1f}% of the frame (rest is crack)")
    print(f"  size        smallest {min(areas)*100:.3f}%  largest {max(areas)*100:.2f}%")
    print(f"  vertices    mean {sum(verts)/len(verts):.1f}  max {max(verts)}")
    print(f"  wrote       {a.out.name} ({a.out.stat().st_size/1024:.0f} KB)")
    if a.preview:
        p = HERE / "glass_pieces_preview.png"
        preview(data, a.src, p)
        print(f"  preview     {p.name}")


if __name__ == "__main__":
    main()

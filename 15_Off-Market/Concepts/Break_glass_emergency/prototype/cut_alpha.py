#!/usr/bin/env python3
"""
Cut the emergency box out of its black background so it can sit on the site's
grass footer as an object rather than a black rectangle.

Why not a simple threshold: the box body is very dark, and a lit-pixel threshold
(gray > 10) captures 908k pixels on 01_intact but only 626k on 05_handle_down —
it is measuring ILLUMINATION, not silhouette, and would punch holes through the
box's own shadowed panels.

So instead: the true background is the black region CONNECTED TO THE IMAGE
BORDER. Flood-fill from the border, and everything not reached is the object,
including its dark interior. That is robust to how brightly any given frame
happens to be lit.

Edges get a sub-pixel feather so the cut-out does not alias against the grass.

Usage:  python3 cut_alpha.py [--check]
        --check only reports, writes nothing.
"""
import sys
import glob
import os
import numpy as np
import cv2
from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
# 07_handle_sprite is already RGBA (build_assets.py cuts it) — leave it alone.
FRAMES = ["01_intact", "02_broken", "03_handle_up", "05_handle_down", "06_plate_clean"]

# Anything at or below this is candidate background. Deliberately low: the box's
# darkest panels sit not far above pure black, and flood-fill (not the threshold)
# is what actually decides the silhouette.
BG_LEVEL = 12


def silhouette(gray: np.ndarray) -> np.ndarray:
    """Opaque mask (uint8 0/255) for the object, via border flood-fill."""
    h, w = gray.shape
    dark = (gray <= BG_LEVEL).astype(np.uint8)

    # Seal 1px pinholes in the dark field so the fill cannot leak INTO the box
    # through a single dark pixel on its edge.
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    # Flood from every border pixel that is dark. Whatever the fill reaches is
    # true background; unreached dark pixels are interior shadow and stay opaque.
    ff = dark.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    for x in range(0, w, 8):
        for y in (0, h - 1):
            if ff[y, x]:
                cv2.floodFill(ff, mask, (x, y), 2)
    for y in range(0, h, 8):
        for x in (0, w - 1):
            if ff[y, x]:
                cv2.floodFill(ff, mask, (x, y), 2)

    bg = (ff == 2)
    obj = (~bg).astype(np.uint8) * 255

    # Largest connected component only — drops stray specks in the background.
    n, lab, stats, _ = cv2.connectedComponentsWithStats((obj > 0).astype(np.uint8), 8)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        obj = ((lab == biggest).astype(np.uint8)) * 255

    # Fill any enclosed holes (a bright ring around a dark centre would otherwise
    # leave the centre transparent).
    ffh = obj.copy()
    m2 = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ffh, m2, (0, 0), 255)
    obj = obj | cv2.bitwise_not(ffh)

    return obj


def main() -> None:
    check = "--check" in sys.argv
    dirs = [a for a in sys.argv[1:] if not a.startswith("-")]
    src = dirs[0] if dirs else SRC

    # ONE silhouette for all frames, taken as the union of the per-frame masks.
    #
    # Per-frame masks are NOT usable: measured, x0 ranges 157-271 across the five
    # frames — a 114px swing, ~20px on screen at the footer's 200px width, which
    # would make the cut-out edge jump during every crossfade. The cause is that
    # the box's left face is unlit in 03/05/06 and sits below BG_LEVEL, so the
    # flood-fill eats into it. The right, top and bottom edges already agree
    # across all five, which is what tells us the box itself does not move.
    #
    # The union takes the outline from whichever frame lights each edge, and the
    # dark left face then renders as a dark face — which is correct, it IS the
    # shadowed side of the object, not background.
    per_frame = {}
    for name in FRAMES:
        path = os.path.join(src, f"{name}.webp")
        if not os.path.exists(path):
            print(f"  MISSING {path}")
            continue
        gray = cv2.cvtColor(np.array(Image.open(path).convert("RGB")), cv2.COLOR_RGB2GRAY)
        per_frame[name] = silhouette(gray)

    if not per_frame:
        print("no frames found")
        return

    union = np.zeros_like(next(iter(per_frame.values())))
    for m in per_frame.values():
        union = np.maximum(union, m)
    h, w = union.shape
    ff = union.copy()
    m2 = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, m2, (0, 0), 255)
    union = union | cv2.bitwise_not(ff)

    print(f"{'frame':<22}{'own bbox':<30}{'opaque px'}")
    for name, m in per_frame.items():
        ys, xs = np.where(m > 0)
        print(f"{name:<22}{str((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))):<30}{int((m > 0).sum())}")
    ys, xs = np.where(union > 0)
    print(f"\nUNION (applied to every frame): "
          f"{(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))}  {int((union > 0).sum())} px")

    if check:
        print("\n--check: nothing written.")
        return

    # Sub-pixel feather so the cut edge does not alias against the grass.
    alpha = cv2.GaussianBlur(union, (0, 0), 0.8)
    for name in per_frame:
        path = os.path.join(src, f"{name}.webp")
        rgb = np.array(Image.open(path).convert("RGB"))
        Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(path, "WEBP", quality=90, method=6)
    print(f"\nwritten with alpha -> {src}")


if __name__ == "__main__":
    main()

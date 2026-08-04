#!/usr/bin/env python3
"""Turn the pandanus fruit drawing into a sprite the deck can roll.

    python3 build_fruit_sprite.py

Two problems to solve, and the second is the one that matters:

  POLARITY   The source is dark ink on white paper, like every other drawing
             here. On the deck the strokes have to come up cream on black with
             the paper gone entirely, so alpha = ink coverage and the RGB is a
             flat cream. Same conversion `build_reveal.py` does with
             polarity="invert", just baked once instead of per frame.

  THE PIVOT  A rolling object turns about the centre of the ball. The drawing's
             bounding box is NOT that centre — the fruit has leaf strands
             trailing off the top and left, which drag the bbox up and out. Spin
             about the bbox centre and the fruit wobbles like a bad wheel.
             So: find the round mass, centre the canvas on IT, and let the
             strands hang wherever they fall. The sprite comes out square with
             the ball dead centre, which means the deck can rotate it about its
             own middle and get a true roll.

Writes ../preview/media/pandanus_fruit.png and prints the geometry the JS needs.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "sources" / "Pandanas_Palm_Fruit.png"
OUT = HERE.parent / "preview" / "media" / "pandanus_fruit.png"
META = HERE.parent / "preview" / "media" / "pandanus_fruit.json"

CREAM = (0xE6, 0xDD, 0xD2)
SIZE = 640           # output square, retina headroom for a ~140px draw
BALL_INK = 0.12      # any stroke at all — the CLOSE below is what finds the mass
GAMMA = 0.85         # lift the mid hatch a little so it reads at small sizes
MARGIN = 1.28        # window half-width as a multiple of the ball radius
FLOOR = 0.025        # ink at or below this is paper, not a stroke — see below


def ink_of(path: Path) -> np.ndarray:
    """Ink coverage in 0..1. Flattened onto white first — a stored RGB under a
    transparent pixel is not paper, and reading it as paper ruined five emblems
    the first time round."""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)
    luma = np.asarray(im.convert("L")).astype(np.float32) / 255.0
    return 1.0 - luma


def ball_circle(ink: np.ndarray) -> tuple[int, int, int]:
    """Centre and radius of the fruit itself, ignoring the trailing strands.

    CLOSE BEFORE OPEN, and this order is the whole trick. The fruit is drawn as
    hundreds of separate drupes, so thresholding alone shatters it — the first
    attempt returned r=55 on a 1254px image, having found a single drupe and
    called it the fruit. Closing first merges the drupes into one mass; opening
    then strips the thin strands off it; the largest component is the ball.
    Stable across every threshold from 0.08 to 0.35, which is how you know it is
    finding the shape rather than a threshold artefact."""
    solid = (ink > BALL_INK).astype(np.uint8)
    solid = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    solid = cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    n, labels, stats, cent = cv2.connectedComponentsWithStats(solid, 8)
    if n <= 1:
        h, w = ink.shape
        return w // 2, h // 2, min(w, h) // 2
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[i]
    cx, cy = int(round(cent[i][0])), int(round(cent[i][1]))
    # radius from area rather than the bbox: the bbox of a near-circle with one
    # flat edge overstates it, and the area is what actually fills the disc.
    r = int(round(np.sqrt(area / np.pi)))
    print(f"  ball          centre ({cx},{cy})  r {r}  "
          f"(bbox {w}x{h}, area {area}, {100*area/ink.size:.1f}% of frame)")
    return cx, cy, r


def main() -> None:
    print(f"reading {SRC.name}")
    ink = ink_of(SRC)
    print(f"  source        {ink.shape[1]} x {ink.shape[0]}   "
          f"mean ink {ink.mean():.3f}")

    cx, cy, r = ball_circle(ink)

    # Square window centred on the ball, wide enough that the strands survive.
    # MARGIN keeps the top tuft; anything the window clips was a wisp
    # heading off the page anyway.
    half = int(round(r * MARGIN))
    H, W = ink.shape
    pad = max(0, half - min(cx, cy, W - cx, H - cy))
    if pad:
        ink = np.pad(ink, pad, mode="constant")
        cx, cy = cx + pad, cy + pad
    win = ink[cy - half:cy + half, cx - half:cx + half]
    print(f"  window        {win.shape[1]} x {win.shape[0]}  (half {half}, pad {pad})")

    # Black point BEFORE gamma. The scanned paper is 253/255, not 255, which is
    # an ink value of 0.008 — invisible on its own, but GAMMA<1 lifts it to
    # alpha 4 across the whole empty margin and the sprite renders as a faint
    # grey SQUARE on the black page. Measured at luminance 0.94 against a page
    # background of exactly 0. Anything at or under FLOOR is paper.
    a = np.clip((win - FLOOR) / (1.0 - FLOOR), 0.0, 1.0) ** GAMMA
    a = cv2.resize(a, (SIZE, SIZE), interpolation=cv2.INTER_AREA)

    rgba = np.zeros((SIZE, SIZE, 4), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = CREAM
    rgba[..., 3] = np.clip(a * 255.0, 0, 255).astype(np.uint8)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(OUT, optimize=True)
    kb = OUT.stat().st_size / 1024

    # The deck needs to know how much of the sprite is ball, so it can sit the
    # fruit ON a surface rather than floating the whole padded square above it.
    meta = {
        "size": SIZE,
        "ball_radius_frac": round(r / half / 2, 4),   # radius as a fraction of the sprite
        "source": SRC.name,
        "note": "cream strokes, alpha=ink coverage, ball centred for rotation",
    }
    META.write_text(json.dumps(meta, indent=2) + "\n")

    print(f"\nwrote {OUT.relative_to(HERE.parent)}  {SIZE}x{SIZE}  {kb:.0f} KB")
    print(f"      ball radius = {meta['ball_radius_frac']:.3f} of sprite width")
    print(f"      alpha: mean {rgba[...,3].mean()/255:.3f}, "
          f"{(rgba[...,3]>8).mean()*100:.1f}% of pixels carry ink")


if __name__ == "__main__":
    main()

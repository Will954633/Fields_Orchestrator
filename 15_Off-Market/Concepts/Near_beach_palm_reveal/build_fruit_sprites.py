#!/usr/bin/env python3
"""
build_fruit_sprites.py — turn the hand-drawn fruit into a rolling sprite sheet.

Takes `Other images/Pandanas_Palm_Fruit.png` (a front-on pen-and-ink pandanus
head) and wraps its real drupe texture around a sphere, rendering N frames of
one full barrel roll about the horizontal long axis.

Why this rather than drawing the fruit procedurally: the procedural version
never matched the hand of the tree. Why this rather than asking for 24 drawn
frames: a rolling object has to be pixel-consistent frame to frame or it
strobes, and separately-drawn frames never are. Here every frame comes from one
source image through one 3D mapping, so consistency is structural.

Two things the source forces:
  * Bracts hang across the fruit's face. They would smear round the sphere as it
    rolled, so the texture is sampled from a strand-free patch of drupes rather
    than from the whole fruit.
  * The drawing has its own baked-in lighting (bright upper-left). That must be
    flattened out, or the highlight would rotate WITH the surface instead of
    staying where the light is. The patch is de-lit, then re-lit per frame.

Run:  python3 build_fruit_sprites.py
Out:  fruit_sprites.png  (grid) + fruit_sprites.json (metadata)
"""

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "Other images" / "Pandanas_Palm_Fruit.png"

# --- tuning -----------------------------------------------------------------
PATCH_CENTRE = (830, 860)   # strand-free drupes (see patch candidates A-D)
PATCH = 340
FRAMES = 24                 # one full revolution; at 2.7s that is ~9fps of spin
TILE = 200                  # px per frame; it is only ever drawn at ~154px
COLS = 6
DRUPES_ACROSS = 8.0         # across the visible diameter
DRUPES_IN_PATCH = 6.0       # roughly how many the sampled patch spans
DELIGHT_BLUR = 34           # radius used to flatten the drawing's own shading
LIGHT = (-0.46, 0.66, 0.60)  # upper-left, toward the viewer
AMBIENT = 0.34
# The sphere is drawn smaller than the tile so protruding drupes have room to
# break the outline without being clipped by the tile edge.
BASE_R = 0.88
BUMP = 0.042                # how far a drupe top stands proud of the body
# ----------------------------------------------------------------------------


def delit_patch() -> np.ndarray:
    """Sampled drupes with the drawing's large-scale shading divided out, so we
    can apply our own lighting per frame."""
    im = Image.open(SOURCE).convert("L")
    x, y = PATCH_CENTRE
    p = im.crop((x - PATCH // 2, y - PATCH // 2, x + PATCH // 2, y + PATCH // 2))
    a = np.asarray(p).astype(np.float32) / 255.0
    base = np.asarray(p.filter(ImageFilter.GaussianBlur(DELIGHT_BLUR))).astype(np.float32) / 255.0
    flat = a / np.clip(base, 0.06, None)
    lo, hi = np.quantile(flat, 0.01), np.quantile(flat, 0.99)
    flat = np.clip((flat - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    print(f"  de-lit patch {flat.shape}  mean {flat.mean():.3f}")
    return flat


def build_wrap_texture(patch: np.ndarray, w: int, h: int) -> np.ndarray:
    """A texture of exactly (h, w) that is periodic in v (around the roll axis).

    Only v has to wrap — u runs along the axis and is traversed once. Mirror
    tiling was the first attempt and it put an obvious reflected seam down every
    sphere, because a reflection is a symmetry the eye reads instantly in a
    regular pattern like packed drupes. Tiling forward with a feathered
    cross-fade at each junction has no symmetry to spot.
    """
    ph, pw = patch.shape
    band = ph // 4
    reps = int(np.ceil(h / (ph - band))) + 1
    col = np.zeros((reps * (ph - band) + band, pw), np.float32)
    ramp = np.linspace(0, 1, band, dtype=np.float32)[:, None]
    y = 0
    for r in range(reps):
        # shift each repeat sideways so the tiling does not line up in columns
        tile = np.roll(patch, (r * 97) % pw, axis=1)
        if r == 0:
            col[0:ph] = tile
        else:
            col[y:y + band] = col[y:y + band] * (1 - ramp) + tile[:band] * ramp
            col[y + band:y + ph] = tile[band:]
        y += ph - band
    col = col[:h + band]

    # close the loop: fade the tail back into the head
    out = col[:h].copy()
    out[:band] = out[:band] * ramp + col[h:h + band] * (1 - ramp)

    if pw != w:
        idx = np.clip((np.arange(w) / w * pw).astype(np.int64), 0, pw - 1)
        out = out[:, idx]
    return out


def sample_wrap(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear: clamp along the axis, wrap around it."""
    h, w = tex.shape
    x0, y0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    x0c, x1c = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    y0c, y1c = np.mod(y0, h), np.mod(y0 + 1, h)
    a = tex[y0c, x0c] * (1 - fx) + tex[y0c, x1c] * fx
    b = tex[y1c, x0c] * (1 - fx) + tex[y1c, x1c] * fx
    return a * (1 - fy) + b * fy


def render(tex: np.ndarray) -> Image.Image:
    px_per_drupe = PATCH / DRUPES_IN_PATCH
    # along the roll axis: the visible diameter spans DRUPES_ACROSS drupes
    span_axis = DRUPES_ACROSS * px_per_drupe
    # around the axis: a full turn is pi x the diameter
    span_round = DRUPES_ACROSS * math.pi * px_per_drupe
    TEXW, TEXH = int(round(span_axis)), int(round(span_round))
    tex = build_wrap_texture(tex, TEXW, TEXH)
    # A separate height map at DRUPE scale. Displacing by the raw texture makes
    # every pen stroke a spike and the fruit comes out looking like a chestnut —
    # the outline should be chewed up by the drupes, not by the hatching.
    drupe_px = PATCH / DRUPES_IN_PATCH
    hb = Image.fromarray((tex * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(drupe_px * 0.22))
    height = np.asarray(hb).astype(np.float32) / 255.0
    hlo, hhi = np.quantile(height, 0.05), np.quantile(height, 0.95)
    height = np.clip((height - hlo) / max(hhi - hlo, 1e-6), 0, 1)
    print(f"  wrap texture {tex.shape}  height map blur {drupe_px*0.22:.1f}px")

    lx, ly, lz = LIGHT
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ln, ly / ln, lz / ln

    g = (np.arange(TILE) + 0.5) / TILE * 2 - 1
    GX, GY = np.meshgrid(g, -g)
    # work in units where the body has radius 1, then scale into the tile
    X, Y = GX / BASE_R, GY / BASE_R
    rq = np.sqrt(X * X + Y * Y)
    # Beyond the body radius we are on a protruding drupe, so clamp the surface
    # point to the rim rather than going imaginary.
    rc = np.clip(rq, 1e-6, 1.0)
    Xc, Yc = X / np.maximum(rq, 1.0), Y / np.maximum(rq, 1.0)
    Z = np.sqrt(np.clip(1.0 - np.minimum(rq, 1.0) ** 2, 0, None))

    rows = math.ceil(FRAMES / COLS)
    sheet = Image.new("RGBA", (COLS * TILE, rows * TILE), (0, 0, 0, 0))

    for f in range(FRAMES):
        rot = f / FRAMES * 2 * math.pi
        # Un-rotate the surface point to find where it sits on the texture.
        # Rotation is about X, so the axial coordinate never changes — only the
        # angle around the axis does. That IS the barrel roll.
        ny = Yc * math.cos(-rot) - Z * math.sin(-rot)
        nz = Yc * math.sin(-rot) + Z * math.cos(-rot)
        theta = np.arctan2(ny, nz)

        u = (Xc + 1) * 0.5 * (TEXW - 1)
        v = (theta + math.pi) / (2 * math.pi) * TEXH
        val = sample_wrap(tex, u, v)

        # --- silhouette displacement ------------------------------------
        # A perfect circle is the one thing that gives this away as geometry:
        # on a real head the drupes stand proud and chew up the outline. Push
        # the alpha boundary out by the drupe height sampled AT THE RIM, so the
        # bumps belong to the drupes actually sitting on the edge — and change
        # as it rolls, rather than being a fixed decorative wobble.
        # Along the silhouette the texture angle is constant for the top half
        # and flips by pi for the bottom, so sampling it directly leaves a hard
        # notch where the two meet — at the poles of the roll axis, the left and
        # right extremes. Sample both and cross-fade through the flip.
        th_up = math.atan2(math.cos(rot), -math.sin(rot))
        th_dn = th_up + math.pi
        v_up = (th_up + math.pi) / (2 * math.pi) * TEXH
        v_dn = (th_dn + math.pi) / (2 * math.pi) * TEXH
        h_up = sample_wrap(height, u, np.full_like(u, v_up))
        h_dn = sample_wrap(height, u, np.full_like(u, v_dn))
        sgn = np.clip(Yc / 0.22, -1, 1)                  # smooth sign of sin(phi)
        w_up = (sgn + 1) * 0.5
        rim_h = h_up * w_up + h_dn * (1 - w_up)
        edge_r = 1.0 + BUMP * (1.0 - rim_h)   # ink (dark in source) = drupe body

        # relight: our own lambert on the flattened texture
        lam = np.clip(X * lx + Y * ly + Z * lz, 0, None)
        shade = AMBIENT + (1 - AMBIENT) * np.power(lam, 0.85)
        # The source is dark ink on white paper. The deck's dark theme is the
        # drawing inverted — the tree's strokes read LIGHT on black — so the
        # fruit has to be inverted too or it sits on the page as a dark blob
        # while the tree beside it is bright.
        ink = 1.0 - val
        out = np.clip((ink * 0.86 + 0.14) * shade, 0, 1)

        rgb = (out * 255).astype(np.uint8)
        # feather in units of the body radius, so it scales with the sprite
        a = np.clip((edge_r - rq) / 0.030, 0, 1)
        alpha = (a * 255).astype(np.uint8)

        tile = np.dstack([rgb, rgb, rgb, alpha])
        img = Image.fromarray(tile, "RGBA")
        sheet.paste(img, ((f % COLS) * TILE, (f // COLS) * TILE))
        if f % 9 == 0:
            print(f"  frame {f:2d}/{FRAMES}")

    return sheet


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"source sketch not found: {SOURCE}")
    print(f"reading {SOURCE.name}")
    tex = delit_patch()
    sheet = render(tex)
    # The sheet is greyscale ink with an alpha cut-out; storing it as RGBA
    # triples the payload for three identical channels. LA is what it actually
    # is, and this is a real page asset, not a local file.
    out = HERE / "fruit_sprites.png"
    sheet.convert("LA").save(out, optimize=True)
    meta = {"frames": FRAMES, "tile": TILE, "cols": COLS,
            "rows": math.ceil(FRAMES / COLS), "baseR": BASE_R,
            "source": SOURCE.name, "note": "one full barrel roll about the horizontal long axis"}
    (HERE / "fruit_sprites.json").write_text(json.dumps(meta, indent=2))
    print(f"  wrote {out.name}  {sheet.size}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
build_whale_sprite.py — turn Whale_V2.png into an animatable sprite + rig.

Whale_V2.png already carries a clean alpha matte, so there is no keying to do.
What it does need:

  * trimming     the matte fills 1432x782 of a 1536x1024 frame, leaving ~50px
                 of margin — not enough for the fluke to swing. Trim tight and
                 let the animation allocate its own padding.
  * feathering   the matte is near-binary (only 0.38% of the frame sits at
                 partial alpha), which aliases badly once the sprite is warped
                 and rotated per strip. A sub-pixel blur on alpha alone fixes it.
  * edge extend  RGB is already extended past the matte in the source, but the
                 crop can expose fresh edges. Bleeding colour outward a few px
                 keeps bilinear sampling from pulling transparent black in and
                 fringing the silhouette.

It also measures the spine out of the matte — per-column centreline and
thickness — which is what the animation uses to place the travelling wave
instead of guessing where the peduncle is.

Writes:  whale_sprite.png, whale_rig.json, index.html
Run:     python3 build_whale_sprite.py
"""

import base64
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Near_beach_palm_reveal" / "Other images" / "Whale_V2.png"
TEMPLATE = HERE / "swim.template.html"

# --- tuning -----------------------------------------------------------------
ALPHA_FLOOR = 16      # alpha at/below this is background when finding the bbox
TRIM_MARGIN = 6       # px of transparent kept around the matte after trimming
FEATHER = 0.7         # gaussian sigma applied to alpha only, to kill the jaggies
BLEED_ITERS = 10      # how far RGB is pushed outward past the matte
SPINE_SMOOTH = 41     # odd window, in columns, for smoothing the centreline
# ----------------------------------------------------------------------------


def bleed_rgb(rgb: np.ndarray, solid: np.ndarray, iters: int) -> np.ndarray:
    """Push colour outward into transparent pixels.

    Bilinear sampling during the warp reads a texel's neighbours regardless of
    their alpha. If those neighbours are transparent *black* rather than
    transparent *whale*, the silhouette picks up a dark rim. Extending the
    colour past the matte means whatever gets sampled out there is the right
    hue, and alpha still hides it.
    """
    rgb = rgb.astype(np.float32).copy()
    known = solid.copy()
    for _ in range(iters):
        if known.all():
            break
        # 4-neighbour mean over currently-known pixels
        acc = np.zeros_like(rgb)
        cnt = np.zeros(known.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sh_rgb = np.roll(np.roll(rgb, dy, 0), dx, 1)
            sh_k = np.roll(np.roll(known, dy, 0), dx, 1).astype(np.float32)
            acc += sh_rgb * sh_k[..., None]
            cnt += sh_k
        fill = (~known) & (cnt > 0)
        rgb[fill] = acc[fill] / cnt[fill][..., None]
        known |= fill
    return np.clip(rgb, 0, 255).astype(np.uint8)


def spine_from_matte(alpha: np.ndarray) -> dict:
    """Per-column centreline and thickness, normalised nose(0) -> fluke tip(1).

    The whale is not drawn along a horizontal axis — it sags through the belly
    and the peduncle lifts toward the flukes. Reading the spine out of the matte
    means the wave rides the body the artist actually drew, and the zone
    boundaries (rigid front / peduncle / fluke) come from measured thickness
    rather than from percentages copied out of a paper.
    """
    h, w = alpha.shape
    solid = alpha > ALPHA_FLOOR
    centre = np.full(w, np.nan, np.float32)
    thick = np.zeros(w, np.float32)
    for x in range(w):
        ys = np.where(solid[:, x])[0]
        if len(ys):
            centre[x] = 0.5 * (ys.min() + ys.max())
            thick[x] = len(ys)

    # fill gaps, then smooth — the flukes split into two lobes and briefly
    # drag the naive min/max centreline around
    idx = np.arange(w)
    good = ~np.isnan(centre)
    centre = np.interp(idx, idx[good], centre[good])
    k = np.ones(SPINE_SMOOTH, np.float32) / SPINE_SMOOTH
    pad = SPINE_SMOOTH // 2
    centre = np.convolve(np.pad(centre, pad, mode="edge"), k, "valid")
    thick_s = np.convolve(np.pad(thick, pad, mode="edge"), k, "valid")

    # u runs nose -> tail. The nose is at the RIGHT of the frame, so u flips x.
    u = 1.0 - (idx + 0.5) / w

    # Where the tail stock ends and the trunk begins.
    #
    # There is no local minimum to look for here: in this three-quarter pose the
    # flukes read as two thin lobes, so filled-pixel count climbs monotonically
    # from the fluke tip into the body and a "find the waist" search just lands
    # in the middle of the whale. Instead, take the tail stock as everything
    # thinner than half the trunk and call the crossing the peduncle.
    #
    # The trunk reference is a 90th percentile, not a max, because the pectoral
    # fins hang below the belly and spike the column count by ~2x where they
    # cross — the fattest columns in the image are fin, not body.
    trunk = float(np.percentile(thick_s, 90))
    tail_side = thick_s[: int(w * 0.6)]
    over = np.where(tail_side > 0.5 * trunk)[0]
    waist = int(over[0]) if len(over) else int(w * 0.2)

    return {
        "centre": [round(float(v), 2) for v in centre],
        "thickness": [round(float(v), 1) for v in thick_s],
        "u": [round(float(v), 5) for v in u],
        "waist_x": waist,
        "waist_u": round(float(1.0 - (waist + 0.5) / w), 4),
        "trunk_thickness": round(trunk, 1),
        "fluke_tip_x": 0,
        "nose_x": int(w - 1),
    }


def main() -> None:
    src = Image.open(SOURCE)
    if src.mode != "RGBA":
        raise SystemExit(f"expected RGBA, got {src.mode} — V2 should carry a matte")
    arr = np.asarray(src)
    rgb, alpha = arr[..., :3], arr[..., 3]

    ys, xs = np.where(alpha > ALPHA_FLOOR)
    y0 = max(int(ys.min()) - TRIM_MARGIN, 0)
    y1 = min(int(ys.max()) + TRIM_MARGIN + 1, alpha.shape[0])
    x0 = max(int(xs.min()) - TRIM_MARGIN, 0)
    x1 = min(int(xs.max()) + TRIM_MARGIN + 1, alpha.shape[1])
    rgb, alpha = rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    h, w = alpha.shape

    rgb = bleed_rgb(rgb, alpha > ALPHA_FLOOR, BLEED_ITERS)
    alpha = np.asarray(
        Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(FEATHER))
    )

    rig = spine_from_matte(alpha)
    rig.update({"width": w, "height": h,
                "source": SOURCE.name,
                "trim": {"x": x0, "y": y0, "w": w, "h": h}})

    sprite = Image.fromarray(np.dstack([rgb, alpha]))
    sprite.save(HERE / "whale_sprite.png")
    (HERE / "whale_rig.json").write_text(json.dumps(rig, separators=(",", ":")))

    # inline into the page so it opens from file:// without tainting the canvas
    png = (HERE / "whale_sprite.png").read_bytes()
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    html = (TEMPLATE.read_text()
            .replace("{{SPRITE_DATA_URI}}", uri)
            .replace("{{RIG_JSON}}", json.dumps(rig, separators=(",", ":"))))
    (HERE / "index.html").write_text(html)

    print(f"sprite      {w}x{h}  ({len(png)/1024:.0f} KB)")
    print(f"peduncle    x={rig['waist_x']}  u={rig['waist_u']}  "
          f"(tail stock meets trunk; trunk ref {rig['trunk_thickness']}px)")
    print(f"index.html  {(HERE / 'index.html').stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()

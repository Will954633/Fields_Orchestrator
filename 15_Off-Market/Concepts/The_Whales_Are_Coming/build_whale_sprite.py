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
from scipy.ndimage import label

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


# --- ink treatment ----------------------------------------------------------
# The look from the V3 reveal deck (Page_Redesign_V3/reveals/build_reveal.py):
# the drawing is reduced to an INK COVERAGE mask and that coverage is painted in
# a warm cream onto black paper. Paper becomes ground, strokes come up light —
# it reads as scratchboard or silverpoint rather than as an inverted photo.
#
# Constants are lifted from that build so the whale matches the rest of the deck
# exactly rather than approximately.
INK_COLOUR = (0xE6, 0xDD, 0xD2)
INK_BLACK_POINT = 0.0015   # luminance quantile mapped to full ink
INK_CLEAN_FLOOR = 0.014    # weaker than this is scanner haze — flatten to paper
INK_GAMMA = 1.06           # >1 holds the light hatch back slightly
INK_UNSHARP = (1.0, 45, 3) # radius, percent, threshold — keeps fine hatch crisp


def paper_white(luma: np.ndarray) -> float:
    """The paper is the most common bright tone, not the brightest pixel.

    A percentile white point leaves a 1/255 haze across the whole background,
    which is enough to make genuinely empty paper carry ink.
    """
    bright = luma[luma > 200].astype(np.uint8)
    if bright.size == 0:
        return float(luma.max())
    vals, counts = np.unique(bright, return_counts=True)
    return float(vals[counts.argmax()])


def ink_coverage(src: Path) -> np.ndarray:
    """Ink coverage over the FULL source frame, before any cropping.

    Transparency is flattened onto white first, never discarded. Whale_V2.png is
    77% transparent over a dark grey RGB ground; going straight to convert("RGB")
    keeps that stored ground and turns the entire empty background into solid
    ink.
    """
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)
    im = im.convert("RGB").filter(ImageFilter.UnsharpMask(*INK_UNSHARP))
    luma = np.asarray(im.convert("L")).astype(np.float32)

    white = paper_white(luma)
    black = float(np.quantile(luma, INK_BLACK_POINT))
    ink = np.clip((white - luma) / max(white - black, 1e-6), 0.0, 1.0) ** INK_GAMMA
    ink[ink < INK_CLEAN_FLOOR] = 0.0
    return ink


def ink_layer(ink: np.ndarray, weight: np.ndarray) -> Image.Image:
    """Cream-on-black layer: flat ink colour, alpha = coverage x layer weight.

    The weight is the layer's own matte, used soft rather than as a boolean so
    the ink edge inherits the matte's feather instead of being cut hard against
    the black.

    Clipping at all matters even though empty paper already carries zero ink —
    the flipper layers must not carry each other's strokes, or a blade would drag
    a ghost of its neighbour around as it swings.
    """
    h, w = ink.shape
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = INK_COLOUR
    rgba[..., 3] = np.round(np.clip(ink * weight, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


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


# Anchors along the trunk's ventral silhouette, sampled at columns where no
# flipper hangs below it. Everything below this line is flipper: the profile
# shows two clean spikes (near flipper x 700-940, far flipper x 1025-1140)
# separated by belly at x 950-1010, so a single cut separates all three.
# The line dips well below the belly over x 520-800: the ventral pleat line
# sweeps left there and a cut at the true silhouette takes it along with the
# flipper. The blade hangs far lower than the pleat over that span, so there is
# clear water between them to cut through. From x 840 rightward the cut has to
# come back up to the real silhouette, because that is where the flipper root
# genuinely crosses the body.
VENTRAL_ANCHORS = [(0, 300), (400, 470), (520, 560), (600, 610), (700, 625),
                   (780, 610), (840, 570), (900, 552), (975, 548), (1010, 551),
                   (1150, 451), (1250, 381), (1444, 300)]
BLADE_MIN_PX = 5000    # anything smaller is a speck, not a flipper
HINGE_ROWS = 12        # rows of the cut edge averaged to place the hinge

# The eye, read off the drawing at 5x. It is an almond running from (962, 396)
# up to (1052, 381) — tilted about 10 degrees — with the bright lower-lid crease
# at y ~ 405 and the upper lid margin at y ~ 378.
#
# The blink stretches the bands of skin above and below the eye toward each
# other, so the lids are made of the artist's own hatching sampled from the
# tissue immediately around the eye. Painting a lid — or inpainting the socket
# and drawing a crease — would have to invent texture matching a pen drawing at
# 5x, and would not.
#
# BOTH lids move, and the movement tapers to zero at the corners. A cetacean
# blink is not an upper lid dropping like a shutter: the orbicularis oculi closes
# the palpebral fissure "using the medial and lateral canthi as fulcrums"
# (Nishimaniwa et al., J. Vet. Med. Sci. 88(1):1-12) — a sphincter purse anchored
# at the corners, with the globe retracting inward at the same time.
#
# Which lid does the work is species-specific, and the humpback is the awkward
# case. In dolphins and porpoises the upper palpebral region has degenerated into
# an aponeurotic sheet with almost no facial-nerve supply, so the lower lid does
# most of the moving. Mysticetes did not: in the humpback and bowhead the muscle
# is "entirely composed of muscular fibers", the ancestral arrangement — so a
# humpback blink should be MORE symmetric than a dolphin's, not less.
# (Rodrigues et al. 2015, Acta Zool. 96:328; Zhu, Hillmann & Henk 2000, Anat.
# Rec. 259:189.)
#
# No nictitating membrane. Cetaceans lack one (Meshida et al. 2020, Anat. Rec.),
# despite what most popular sources claim. Do not animate a third eyelid.
EYE = {
    "x": 958, "y": 372, "w": 100, "h": 42,   # the eye opening
    "lid_open_y": 378,     # upper lid margin when open
    "lower_open_y": 406,   # lower lid margin when open — the bright crease
    "meet_y": 393,         # where the two margins meet when shut
    "lid_src_h": 48,       # skin above the eye stretched down
    "lower_src_h": 30,     # tissue below the eye stretched up (shorter: the
                           # bright jaw groove starts soon after)
    "angle_deg": -10.4,    # tilt of the lid axis
}


def split_flippers(rgb: np.ndarray, alpha: np.ndarray) -> tuple:
    """Cut the two pectoral flippers off the body as independently posable layers.

    The flippers hang below the belly into open water, so the cut runs along the
    trunk's ventral silhouette and almost all of each blade is already against
    background — there is nothing to inpaint.

    The hinge is placed ON the cut line rather than at the anatomical shoulder,
    which is a little higher inside the body. Rotating about the cut means the
    blade's displacement is zero exactly where it meets the body, so the seam
    cannot open however far the flipper swings. A hinge at the true shoulder
    would be more correct and would shear the join by r*theta — about 8px at a
    6 degree stroke, which reads as the flipper detaching.
    """
    h, w = alpha.shape
    solid = alpha > 32
    ax = [a[0] for a in VENTRAL_ANCHORS]
    ay = [a[1] for a in VENTRAL_ANCHORS]
    ventral = np.interp(np.arange(w), ax, ay)

    below = solid & (np.arange(h)[:, None] > (ventral[None, :] + 2))
    lab, n = label(below)
    blades = []
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < BLADE_MIN_PX:
            continue
        ys, xs = np.where(m)
        blades.append({"mask": m, "x0": int(xs.min()), "x1": int(xs.max()),
                       "y0": int(ys.min()), "y1": int(ys.max()),
                       "cx": float(xs.mean())})
    if len(blades) != 2:
        raise SystemExit(f"expected 2 flippers below the ventral line, found {len(blades)}")

    # nearer to the viewer is the one further from the nose (nose is at max x)
    blades.sort(key=lambda b: b["cx"])
    names = ["near", "far"]

    body_alpha = alpha.copy()
    layers = {}
    for name, b in zip(names, blades):
        m = b["mask"]
        body_alpha[m] = 0

        # hinge: centroid of the topmost rows of the blade — the cut edge
        ys, xs = np.where(m)
        top = ys < ys.min() + HINGE_ROWS
        hinge = (float(xs[top].mean()), float(ys[top].mean()))

        x0, x1, y0, y1 = b["x0"] - 4, b["x1"] + 5, b["y0"] - 4, b["y1"] + 5
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, w), min(y1, h)
        la = np.where(m, alpha, 0)[y0:y1, x0:x1]
        lrgb = bleed_rgb(rgb[y0:y1, x0:x1], la > 32, 6)
        layers[name] = {
            "img": Image.fromarray(np.dstack([lrgb, la]).astype(np.uint8)),
            "alpha": la,
            "meta": {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                     "hinge_x": round(hinge[0] - x0, 1),
                     "hinge_y": round(hinge[1] - y0, 1),
                     "hinge_abs_x": round(hinge[0], 1),
                     "hinge_abs_y": round(hinge[1], 1)},
        }
    return body_alpha, layers


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

    body_alpha, flippers = split_flippers(rgb, alpha)

    # the spine is measured from the body alone — with the flippers still
    # attached they roughly double the column count where they cross and drag
    # the measured centreline down through the whole shoulder region
    rig = spine_from_matte(body_alpha)
    rig.update({"width": w, "height": h,
                "source": SOURCE.name,
                "trim": {"x": x0, "y": y0, "w": w, "h": h},
                "flippers": {k: v["meta"] for k, v in flippers.items()},
                "eye": EYE})

    Image.fromarray(np.dstack([rgb, body_alpha])).save(HERE / "whale_body.png")
    for name, layer in flippers.items():
        layer["img"].save(HERE / f"whale_flipper_{name}.png")

    # --- the ink treatment, from the same crop and the same cuts ---------------
    # Computed on the FULL source then cropped identically, so every coordinate
    # in whale_rig.json — spine, flipper hinges, eye — stays valid for both
    # sprite sets and the two pages share one rig.
    ink = ink_coverage(SOURCE)[y0:y1, x0:x1]
    ink_layer(ink, body_alpha / 255.0).save(HERE / "whale_body_ink.png")
    for name, layer in flippers.items():
        m = layer["meta"]
        sub = ink[m["y"]:m["y"] + m["h"], m["x"]:m["x"] + m["w"]]
        ink_layer(sub, layer["alpha"] / 255.0).save(HERE / f"whale_flipper_{name}_ink.png")

    def uri(p: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()

    tpl = TEMPLATE.read_text()
    rig_json = json.dumps(rig, separators=(",", ":"))
    for out, suffix, theme in (("sketch.html", "", "dark"),
                               ("ink.html", "_ink", "ink")):
        html = (tpl
                .replace("{{BODY_DATA_URI}}", uri(HERE / f"whale_body{suffix}.png"))
                .replace("{{NEAR_DATA_URI}}", uri(HERE / f"whale_flipper_near{suffix}.png"))
                .replace("{{FAR_DATA_URI}}", uri(HERE / f"whale_flipper_far{suffix}.png"))
                .replace("{{THEME_DEFAULT}}", theme)
                .replace("{{RIG_JSON}}", rig_json))
        (HERE / out).write_text(html)
    (HERE / "whale_rig.json").write_text(rig_json)

    print(f"body        {w}x{h}")
    for name, layer in flippers.items():
        m = layer["meta"]
        print(f"flipper {name:5s} {m['w']}x{m['h']} at ({m['x']},{m['y']})  "
              f"hinge ({m['hinge_abs_x']},{m['hinge_abs_y']})")
    print(f"peduncle    x={rig['waist_x']}  u={rig['waist_u']}  "
          f"(tail stock meets trunk; trunk ref {rig['trunk_thickness']}px)")
    print(f"ink         mean coverage {ink.mean():.3f}, "
          f"{(ink > 0).mean()*100:.1f}% of the crop carries ink")
    for out in ("sketch.html", "ink.html"):
        print(f"{out:12s} {(HERE / out).stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()

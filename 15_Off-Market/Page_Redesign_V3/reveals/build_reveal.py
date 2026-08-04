#!/usr/bin/env python3
"""
build_reveal.py — turn any hatch drawing into a self-contained pixel-reveal page.

Generalised from Concepts/Near_beach_palm_reveal/build_master.py, which was
hard-wired to the pandanus. V3 needs the same treatment applied to nine
drawings, so source, output stem and reveal ordering are all arguments now.

For each source it writes, into --out-dir:

  <stem>_ink.png   ink as an RGBA mask (RGB = growth order, A = coverage) so the
                   animation composites strokes onto any paper colour without
                   painting white boxes over the deck's black ground
  <stem>.html      the animation with that mask inlined as a data URI, so it
                   opens standalone and survives being rendered from file://

The one real difference from the palm build is --order.

  geodesic   distance from the base of the trunk, travelling THROUGH the ink.
             This is what makes the palm *grow* — the canopy cannot fill before
             the branch feeding it exists. It is also a Dijkstra over one node
             per pixel (~1.5M nodes / 6M edges on these sources), which is the
             expensive part of the build.
  none       skip it. The `develop` and `dissolve` reveal modes key off ink
             density and noise, never the growth channel, so a scene that is not
             a single growing object has nothing to gain from paying for it.

A parkland, a lake edge or a whale has no trunk to grow from — seeding at "the
densest ink low in the frame" would pick an arbitrary shrub and crawl outward
from it. Those use --order none --mode develop, where the darkest structure
lands first and the light hatch fills in behind it, which reads as a drawing
being made rather than as something growing.

Run:
  python3 build_reveal.py --src sources/Parkland.png --stem parkland --order none
  python3 build_reveal.py --all          # every source, per REVEALS below
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "reveal.template.html"

# --- tuning (inherited from build_master.py — measured against these sources) -
CROP_MARGIN = 44      # px of paper kept around the ink bounding box
BBOX_INK = 0.06       # ink strength that counts as a stroke when cropping
BBOX_MIN_PX = 3       # ...and this many per row/column, so specks can't set it
BLACK_POINT = 0.0015  # luminance percentile mapped to pure black
CLEAN_FLOOR = 0.014   # ink weaker than this is scanner haze — flatten to paper
GAMMA = 1.06          # >1 on the ink curve holds the light hatch back slightly
UNSHARP = (1.0, 45, 3)  # radius, percent, threshold — keeps fine hatch crisp
PAPER_COST = 0.03       # smaller = crossing blank paper costs more
# -----------------------------------------------------------------------------

# The mapping from a lead angle to one of these stems is angle_media.yaml's job,
# not this script's — several angles legitimately share one drawing.
REVEALS = {
    # Six attributes per drawing, so this is a dict rather than a positional
    # tuple — the tuple form had grown to five fields and was unreadable.
    #   order     geodesic (ink travels through the drawing) | none
    #   mode      growth (needs geodesic) | develop
    #   polarity  invert (paint the strokes) | positive (paint the subject's light)
    #   seed      growth origin, X,Y fractions of the CROPPED drawing
    #   masks     rectangles to erase, fractions of the frame
    #
    # growth is the house animation — the thing appears to grow rather than
    # resolve. It needs a base the ink can travel up from. `develop` is the
    # fallback for subjects that have none: a dog does not grow out of a paw.

    "pandanus": dict(src="Hatch_Sketch_Pandanas_Palm.png", order="geodesic",
                     mode="growth",  polarity="invert"),
    # Lorikeets on a eucalypt branch — scratchboard (light strokes on a dark
    # ground), so `positive` paints them directly. Seeded at the foot of the
    # branch so growth climbs it into the birds; the automatic rule would take
    # the heaviest ink low in the frame, which here is a cluster of leaves.
    "bushbirds": dict(src="Bushland_Birds.png",            order="geodesic",
                      mode="growth", polarity="positive", seed=(0.45, 0.97)),
    # the plain gum it replaced, kept buildable
    "gum":      dict(src="Bushland_Tree.png",              order="geodesic",
                     mode="growth",  polarity="invert"),
    "reeds":    dict(src="Native_reeds.png",               order="geodesic",
                     mode="growth",  polarity="invert"),
    "banksia":  dict(src="bushand_creek_native_flower.png", order="geodesic",
                     mode="growth",  polarity="invert"),
    # Pre-inverted plate. Seeded explicitly at the foot of the pole: the
    # automatic rule takes the heaviest ink low in the frame and picks the BALL,
    # which would start growth in the ball and crawl backwards into the pin.
    "golfflag": dict(src="flag_pole_golf_v2.png",          order="geodesic",
                     mode="growth",  polarity="invert_cutout", seed=(0.35, 0.96),
                     gamma=0.8),

    # No base to grow from — these resolve rather than grow.
    # Version 1's treatment — Source A inverted — with the coat lifted.
    #
    # Will chose the inverted look, then: "too much of the dog is black". Under
    # inversion the pale coat carries little ink, so at the default gamma only
    # the stroke edges light and the body stays dark. gamma BELOW 1 raises the
    # faint ink, which is exactly the coat: 0.5 takes mean-lit from 84 to 105
    # and the whole body becomes readable fur while the shadows and the glowing
    # edges — the character of the render — stay put.
    #
    # Source A, not v3: A is the transparent cutout whose inversion Will picked.
    # See preview/dogs.html for the full gamma ladder on both sources.
    "dog":      dict(src="Large_block_dog.png",    order="none", mode="develop",
                     polarity="invert", gamma=0.5),
    # v3 inverted, the finer-fur alternative
    "dog_v3_inv": dict(src="dog_v3.png",           order="none", mode="develop",
                       polarity="invert_cutout", gamma=0.7),
    # v3 tonally correct (pale coat, dark eyes) — superseded, kept buildable
    "dog_positive": dict(src="dog_v3.png",         order="none", mode="develop",
                         polarity="positive"),
    "dog_v1":   dict(src="Large_block_dog.png",    order="none", mode="develop",
                     polarity="positive"),
    "satchel":  dict(src="School_Walk.png",      order="none", mode="develop",
                     polarity="positive"),
    "whale":    dict(src="Whale_V2.png",         order="none", mode="develop",
                     polarity="invert"),

    # --- superseded, kept buildable as reference cases ------------------------
    # v1 flag: fabric blank inside an outline (subject_ink_pct 47.8).
    "golfflag_v1": dict(src="flag_pole_golf.png", order="none", mode="develop",
                        polarity="positive", masks=((0.00, 0.68, 0.42, 1.00),)),
    # v1 landscape scenes: full-bleed, all fail the gate on paper purity.
    "parkland": dict(src="Parkland.png",          order="none", mode="develop", polarity="invert"),
    "bushland": dict(src="bushland.png",          order="none", mode="develop", polarity="invert"),
    "golf":     dict(src="Golf_course.png",       order="none", mode="develop", polarity="invert"),
    "lake":     dict(src="water_adjacent .png",   order="none", mode="develop", polarity="invert"),
    "school":   dict(src="Walk to school.png",    order="none", mode="develop", polarity="invert"),
    "pavilion": dict(src="Robina_Pavillion.png",  order="none", mode="develop", polarity="invert"),
    "whale_light": dict(src="whale.png",          order="none", mode="develop", polarity="invert"),
}


def growth_order(ink: np.ndarray, seed: tuple[float, float] | None = None) -> np.ndarray:
    """Geodesic distance from the base of the trunk, travelling THROUGH the ink.

    Cost of moving is the inverse of ink density, so growth runs up the trunk,
    out along each branch and only then into the fronds. Returned normalised
    0..1; unreachable pixels are pinned to the far end.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra

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

    if seed is not None:
        # Explicit seed, as a fraction of the cropped drawing. The automatic rule
        # below looks for the heaviest ink low in the frame, which finds a trunk
        # but is fooled by anything else sitting at the base: on the golf flag it
        # picks the BALL over the foot of the pole, so growth would start in the
        # ball and crawl backwards into the pin.
        seed_x, seed_y = int(seed[0] * w), int(seed[1] * h)
        print(f"  growth seed   ({seed_x}, {seed_y}) — given")
    else:
        band = ink[int(h * 0.90):int(h * 0.97)]
        colmass = band.sum(axis=0)
        seed_x = int(np.argmax(np.convolve(colmass, np.ones(31) / 31, mode="same")))
        seed_y = int(h * 0.93)
        print(f"  growth seed   ({seed_x}, {seed_y}) — foot of the trunk")
    seed_x = max(0, min(w - 1, seed_x)); seed_y = max(0, min(h - 1, seed_y))

    d = dijkstra(g, directed=False, indices=seed_y * w + seed_x).reshape(h, w)
    finite = np.isfinite(d)
    dmax = d[finite & (ink > 0.02)].max()
    d = np.where(finite, np.minimum(d, dmax), dmax)
    print(f"  geodesic      max {dmax:.0f} over {finite.mean()*100:.1f}% reachable")
    return np.clip(d / dmax, 0, 1)


def load_luma(path: Path, polarity: str = "invert") -> np.ndarray:
    """Desaturate to luminance. These sources are near-monochrome already, so a
    straight ITU-R 601 luma is a faithful B&W reading.

    Transparency is flattened FIRST. build_master.py went straight to
    convert("RGB"), which discards the alpha channel and keeps whatever RGB was
    stored underneath — that was safe for the pandanus (opaque) but Whale_V2.png
    is 77% transparent over dark RGB, so the same call turned its entire blank
    background into solid ink. Composite, never discard.

    Which colour it flattens onto is the polarity (see build()): white for an
    inverted subject, black for a positive one.
    """
    bg = (255, 255, 255, 255) if polarity == "invert" else (0, 0, 0, 255)
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        im = Image.alpha_composite(Image.new("RGBA", im.size, bg), im)
    # An opaque source is fine for `positive` when it is already a light-on-dark
    # plate — flag_pole_golf_v2.png arrives that way, drawn as the finished look
    # rather than as ink on paper. What is NOT fine is an opaque light-on-WHITE
    # file, where there is no ground to knock out and the whole frame would
    # paint solid.
    elif polarity == "positive":
        mean = np.asarray(im.convert("L")).mean()
        if mean > 96:
            raise SystemExit(
                f"{path.name}: positive polarity needs either a transparent "
                f"background to knock out, or an already-dark ground. This file "
                f"is opaque with mean luma {mean:.0f} — too light for either.")
    im = im.convert("RGB").filter(ImageFilter.UnsharpMask(*UNSHARP))
    return np.asarray(im.convert("L")).astype(np.float32)


def ground_mask(luma: np.ndarray, thresh: float = 96.0) -> np.ndarray:
    """The dark ground of a plate, as distinct from dark ink inside the subject.

    Connected components of dark pixels that touch the frame border. Ink strokes
    are dark too, but they are enclosed by the light material they are drawn on,
    so they never reach the border and are correctly left alone. A plain
    threshold would erase them along with the ground.
    """
    lbl, _ = ndimage.label(luma < thresh)
    edges = np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]])
    keep = np.unique(edges)
    return np.isin(lbl, keep[keep != 0])


def paper_black(luma: np.ndarray) -> float:
    """The ground of a light-on-dark plate: the most common DARK tone, not the
    darkest pixel. Mirror of paper_white(), and needed for the same reason —
    flag_pole_golf_v2.png sits on a mottled ~37 grey, so mapping only true black
    to zero would leave that whole ground painting as a dim wash over the deck.
    """
    dark = luma[luma < 96].astype(np.uint8)
    if dark.size == 0:
        return 0.0
    vals, counts = np.unique(dark, return_counts=True)
    return float(vals[counts.argmax()])


def paper_white(luma: np.ndarray) -> float:
    """The paper is the single most common bright tone, not the brightest pixel.
    A percentile white point leaves a 1/255 haze over the whole background —
    enough to make every 'empty' block count as ink."""
    bright = luma[luma > 200].astype(np.uint8)
    if bright.size == 0:
        # a full-bleed drawing (Whale_V2 is on a dark ground) has no paper at all
        return float(luma.max())
    vals, counts = np.unique(bright, return_counts=True)
    return float(vals[counts.argmax()])


def crop_to_ink(ink: np.ndarray) -> tuple[int, int, int, int]:
    mask = ink > BBOX_INK
    rows = np.where(mask.sum(axis=1) >= BBOX_MIN_PX)[0]
    cols = np.where(mask.sum(axis=0) >= BBOX_MIN_PX)[0]
    h, w = ink.shape
    if rows.size == 0 or cols.size == 0:
        return (0, 0, w, h)
    print(f"  ink bbox      x {cols.min()}-{cols.max()}  y {rows.min()}-{rows.max()}")
    return (
        max(0, int(cols.min()) - CROP_MARGIN),
        max(0, int(rows.min()) - CROP_MARGIN),
        min(w, int(cols.max()) + 1 + CROP_MARGIN),
        min(h, int(rows.max()) + 1 + CROP_MARGIN),
    )


def apply_masks(ink: np.ndarray, masks: list[tuple[float, float, float, float]]) -> np.ndarray:
    """Erase rectangles of the source, given as fractions of width/height.

    An escape hatch for one specific thing: the generator adding an element the
    spec rules out, on a drawing that is otherwise good. `flag_pole_golf.png`
    arrived with a cast shadow — a grey wedge that, with no ground plane drawn,
    floats beside the pole attached to nothing.

    Fractions rather than pixels so a re-export at a different size still masks
    the same place. This is a patch over a source defect, not a feature: the
    right fix is always to regenerate the drawing without the offending element,
    and a mask entry should be deleted the moment that happens.
    """
    h, w = ink.shape
    for x0, y0, x1, y1 in masks:
        ink[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 0.0
        print(f"  masked        x {x0:.2f}-{x1:.2f}  y {y0:.2f}-{y1:.2f} of the frame")
    return ink


def build(src: Path, stem: str, order: str, mode: str, out_dir: Path,
          polarity: str = "invert",
          masks: list[tuple[float, float, float, float]] | None = None,
          gamma: float = GAMMA,
          seed: tuple[float, float] | None = None) -> None:
    """polarity decides what gets painted in the deck's cream.

    invert    (default) — ink is the STROKES. Paper becomes the deck's black and
              the strokes come up cream. Right for a linear subject built out of
              hatch with paper showing through: the palm, the gum, the reeds,
              the banksia, the whale.

    invert_cutout — dark ink on light material, delivered on a dark ground.
              The ground is cut away, then it inverts exactly like `invert`.
              flag_pole_golf_v2.png is one: its cloth is light fabric with dark
              hatch over it, the same construction as the banksia — only the
              surround differs.

    positive  — ink is the SUBJECT'S OWN LIGHT. The transparent background is
              knocked out to black and the drawing keeps its original polarity,
              so a pale body stays pale and its dark fur strokes stay dark.

    The distinction is whether the subject has a filled body. Inverting a light
    body turns it dark: the golden retriever came out as a black dog with bright
    fur edges, because 'light fur' means 'little ink' means 'nothing painted'.
    A tree has no body — only strokes — so it cannot go wrong that way.
    Positive polarity needs a genuinely transparent background, since the black
    knockout is what separates subject from ground.
    """
    if not src.exists():
        raise SystemExit(f"source image not found: {src}")
    if not TEMPLATE.exists():
        raise SystemExit(f"template not found: {TEMPLATE}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{stem}  <-  {src.name}   (order={order}, mode={mode}, "
          f"polarity={polarity}, gamma={gamma})")
    had_alpha = Image.open(src).mode in ("RGBA", "LA", "P")
    luma = load_luma(src, polarity)

    white = paper_white(luma)
    black = float(np.quantile(luma, BLACK_POINT))
    if polarity == "invert_cutout":
        # A drawing made in DARK INK on light material, delivered sitting on a
        # dark ground. flag_pole_golf_v2.png is one: zoom into the cloth and it
        # is light fabric with dark hatch lines over it, exactly like the
        # banksia — only the surround differs.
        #
        # So the ink is the strokes, as it is for every botanical, and the
        # treatment is plain inversion: black sketch strokes come up as greys
        # and whites. The only thing in the way is the ground, which is dark and
        # would otherwise read as ink across the whole frame. Cut it out first,
        # take the levels from the subject alone, then invert.
        gm = ground_mask(luma)
        subj = luma[~gm]
        white = paper_white(subj) if subj.size else 255.0
        black = float(np.quantile(subj, BLACK_POINT)) if subj.size else 0.0
        print(f"  levels        ground cut ({gm.mean()*100:.0f}% of frame), "
              f"then black {black:.0f} -> 0, material {white:.0f} -> 255")
        ink = np.clip((white - luma) / max(white - black, 1e-6), 0.0, 1.0) ** gamma
        ink[gm] = 0.0
    elif polarity == "positive":
        # ink = the subject's own luminance, with the ground mapped to zero so it
        # drops out completely. The pale form runs to 1 and paints cream; the
        # dark strokes within it sit near 0 and read as lines through it.
        ground = paper_black(luma)
        ink = np.clip((luma - ground) / max(white - ground, 1e-6), 0.0, 1.0) ** gamma
        # Mapping the MODAL dark tone to zero is not enough on a hand-textured
        # plate: the ground is mottled, so everything above the mode survives
        # CLEAN_FLOOR and paints a faint grey wash across the deck. Cut the
        # border-connected dark region outright, exactly as invert_cutout does.
        # Only for an opaque source — a transparent one was already composited
        # onto black and has no ground left to find.
        cut = 0.0
        if not had_alpha:
            gm = ground_mask(luma, thresh=max(ground + 24, 48))
            ink[gm] = 0.0
            cut = gm.mean() * 100
        print(f"  levels        ground {ground:.0f} -> 0 (cut {cut:.0f}% of frame), "
              f"highlight {white:.0f} -> full ink (positive)")
    else:
        print(f"  levels        black {black:.0f} -> 0, paper {white:.0f} -> 255")
        ink = np.clip((white - luma) / max(white - black, 1e-6), 0.0, 1.0) ** gamma

    hazy = float((ink > 0).mean() - (ink >= CLEAN_FLOOR).mean())
    ink[ink < CLEAN_FLOOR] = 0.0
    if masks:
        # before crop_to_ink, so a masked element cannot still set the bbox
        ink = apply_masks(ink, masks)
    print(f"  cleaned       {hazy * 100:.1f}% of pixels were sub-{CLEAN_FLOOR} haze")

    x0, y0, x1, y1 = crop_to_ink(ink)
    ink = ink[y0:y1, x0:x1]
    h, w = ink.shape
    print(f"  cropped to    {w} x {h} (from {luma.shape[1]} x {luma.shape[0]})")
    print(f"  ink coverage  {(ink > 0).mean() * 100:.1f}% of pixels carry ink")

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    if order == "geodesic":
        print("  computing growth order (geodesic through the ink)...")
        o16 = np.round(growth_order(ink, seed) * 65535).astype(np.uint16)
        rgba[..., 0] = (o16 >> 8).astype(np.uint8)
        rgba[..., 1] = (o16 & 0xFF).astype(np.uint8)
    rgba[..., 3] = np.round(ink * 255).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG", optimize=True)
    mask_bytes = buf.getvalue()
    mask_path = out_dir / f"{stem}_ink.png"
    mask_path.write_bytes(mask_bytes)
    print(f"  wrote         {mask_path.name}  ({len(mask_bytes) / 1024:.0f} KB)")

    data_uri = "data:image/png;base64," + base64.b64encode(mask_bytes).decode("ascii")
    html = (
        TEMPLATE.read_text()
        .replace("{{INK_DATA_URI}}", data_uri)
        .replace("{{IMAGE_W}}", str(w))
        .replace("{{IMAGE_H}}", str(h))
    )
    page = out_dir / f"{stem}.html"
    page.write_text(html)
    print(f"  wrote         {page.name} ({page.stat().st_size / 1024:.0f} KB, default mode={mode})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, help="source drawing (PNG)")
    ap.add_argument("--stem", help="output name, e.g. parkland")
    ap.add_argument("--order", choices=("geodesic", "none"), default="none",
                    help="growth channel: geodesic (a growing object) or none (a scene)")
    ap.add_argument("--mode", default="develop", help="default reveal mode baked into the page URL")
    ap.add_argument("--seed", help="growth origin as X,Y fractions of the cropped "
                                   "drawing, e.g. 0.35,0.96 for the foot of a pole")
    ap.add_argument("--gamma", type=float, default=GAMMA,
                    help="ink curve. <1 lifts the fine hatch (a rendered object reads as "
                         "line work); >1 holds it back. Default %(default)s")
    ap.add_argument("--polarity", choices=("invert", "positive", "invert_cutout"),
                    default="invert",
                    help="invert = paint the strokes (linear subject); positive = paint the subject's own light (filled body, needs alpha)")
    ap.add_argument("--src-dir", type=Path, default=HERE / "sources")
    ap.add_argument("--out-dir", type=Path, default=HERE / "out")
    ap.add_argument("--all", action="store_true", help="build every entry in REVEALS")
    ap.add_argument("--only", nargs="*", help="with --all, restrict to these stems")
    a = ap.parse_args()

    if a.all:
        wanted = a.only or list(REVEALS)
        unknown = [s for s in wanted if s not in REVEALS]
        if unknown:
            raise SystemExit(f"unknown stem(s): {', '.join(unknown)}")
        for stem in wanted:
            r = REVEALS[stem]
            build(a.src_dir / r["src"], stem, r["order"], r["mode"], a.out_dir,
                  r["polarity"], list(r.get("masks", ())), r.get("gamma", GAMMA),
                  r.get("seed"))
        return

    if not a.src or not a.stem:
        ap.print_usage(sys.stderr)
        raise SystemExit("--src and --stem are required unless --all is given")
    seed = tuple(float(v) for v in a.seed.split(",")) if a.seed else None
    build(a.src, a.stem, a.order, a.mode, a.out_dir, a.polarity, None, a.gamma, seed)


if __name__ == "__main__":
    main()

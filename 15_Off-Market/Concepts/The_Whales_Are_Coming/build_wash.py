#!/usr/bin/env python3
"""
build_wash.py — recolour the whale from a reference painting's palette.

Luminance-indexed colour transfer. The reference is reduced to a SPECTRUM: its
colours binned by intensity, so bin 0 holds the darkest tones the painter used
and bin 255 the lightest. The greyscale whale is then histogram-matched into the
reference's intensity range and every pixel looked up in that spectrum.

Why the histogram match matters: without it, the whale's own tonal range is read
against the reference's bins directly, and if the painting is (say) lighter
overall than the drawing, most of the whale lands in bins the painter barely
used. Matching the cumulative distributions first means "the darkest 5% of the
whale" maps to "the darkest 5% of the painting", which is what makes the
transfer read as the same palette rather than as a tint.

The mapping is 1-D by construction, so two regions of the reference at the same
intensity but different hue — a grey head and a blue flipper, say — collapse to
one colour. That is the known cost of this method. It is the right cost here
because both images order tone the same way: dark along the back, pale at the
belly, so intensity is already carrying the anatomy.

Reads the layers build_whale_sprite.py produced, so the cut, the rig and the
hinges are all inherited unchanged.

Writes:  whale_{body,flipper_near,flipper_far}_wash.png
         wash_palette.png   the spectrum, labelled — see --palette-only
         index_wash.html
Run:     python3 build_wash.py --ref "path/to/watercolour_whale.png"
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import label

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "swim.template.html"

BINS = 256
SMOOTH_BINS = 7        # gaussian window along the spectrum, to stop banding
MIN_BIN_PX = 24        # a bin with fewer samples than this is interpolated, not trusted
BG_LUMA = 244          # border-connected pixels brighter than this are paper
SWATCHES = 16          # rows in the printed palette chart


def load_rgb_and_mask(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Reference RGB plus a mask of the subject.

    The background is flood-filled from the border rather than thresholded: a
    watercolour has plenty of pale washes inside the animal that a plain
    brightness cut would throw away with the paper, and losing the belly would
    strip the light end of the spectrum — exactly the end that decides what the
    whale's underside becomes.
    """
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        im = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im)
    rgb = np.asarray(im.convert("RGB")).astype(np.float32)
    luma = rgb @ np.array([0.299, 0.587, 0.114], np.float32)

    paper = luma > BG_LUMA
    lab, _ = label(paper)
    border = set(lab[0].tolist()) | set(lab[-1].tolist()) \
        | set(lab[:, 0].tolist()) | set(lab[:, -1].tolist())
    border.discard(0)
    mask = ~np.isin(lab, list(border))
    return rgb, mask


def build_spectrum(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """intensity bin -> mean colour, and the share of the subject in each bin."""
    luma = (rgb @ np.array([0.299, 0.587, 0.114], np.float32))[mask]
    cols = rgb[mask]
    idx = np.clip(luma.astype(int), 0, BINS - 1)

    lut = np.zeros((BINS, 3), np.float32)
    count = np.bincount(idx, minlength=BINS).astype(np.float32)
    for c in range(3):
        lut[:, c] = np.bincount(idx, weights=cols[:, c], minlength=BINS)
    lut[count > 0] /= count[count > 0, None]

    # bins with too little evidence are interpolated from the ones that have it,
    # so a handful of stray pixels cannot define a whole tonal band
    good = count >= MIN_BIN_PX
    if good.sum() < 2:
        raise SystemExit("reference has too little colour to build a spectrum")
    xs = np.arange(BINS)
    for c in range(3):
        lut[:, c] = np.interp(xs, xs[good], lut[good, c])

    k = np.ones(SMOOTH_BINS, np.float32) / SMOOTH_BINS
    pad = SMOOTH_BINS // 2
    for c in range(3):
        lut[:, c] = np.convolve(np.pad(lut[:, c], pad, mode="edge"), k, "valid")

    return np.clip(lut, 0, 255), count / max(count.sum(), 1)


def spectrum_saturation(lut: np.ndarray) -> np.ndarray:
    mx, mn = lut.max(1), lut.min(1)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)


def cdf_of(luma: np.ndarray, weights: np.ndarray) -> np.ndarray:
    h = np.bincount(np.clip(luma.astype(int), 0, BINS - 1),
                    weights=weights, minlength=BINS)
    c = np.cumsum(h)
    return c / max(c[-1], 1e-9)


def match_curve(src_cdf: np.ndarray, ref_cdf: np.ndarray) -> np.ndarray:
    """src intensity -> ref intensity, equalising the cumulative distributions."""
    return np.interp(src_cdf, ref_cdf, np.arange(BINS)).astype(np.float32)


def ref_weights(count: np.ndarray, sat: np.ndarray, bias: float) -> np.ndarray:
    """How much each intensity band should attract the whale's tones.

    At bias 0 this is the reference's own pixel count, which reproduces its
    distribution exactly — and that is precisely why the first attempt looked
    grey. 54% of this painting is pale wash sitting in bands where the spectrum's
    saturation has fallen to 0.23 and below; matching the distribution faithfully
    means faithfully inheriting all that greyness. The vivid colour lives at
    intensity 64-127, which is only 22% of the painting, so the whale was
    receiving mean saturation 0.285 out of 0.508 available.

    Raising bias weights the bands by how much colour they actually carry, so the
    whale's tones are drawn into the saturated part of the spectrum instead of
    being spread in proportion to how much pale wash the painter happened to use.
    """
    if bias <= 0:
        return count
    rel = sat / max(sat.mean(), 1e-6)
    return count * np.power(np.maximum(rel, 1e-3), bias)


def recolour(layer: Path, lut: np.ndarray, curve: np.ndarray,
             detail: float, wash: float, chroma: float) -> Image.Image:
    """Flat colour wash, then line work on top — the way the reference was painted.

    The first version looked up the LUT against the drawing's raw luminance and
    then added detail on top, so the pen hatch was carried twice: once as colour
    modulation and again as luminance. Measured against the reference that gave
    2.7x its local contrast (26.4 vs 9.8), and high-frequency light/dark
    integrates toward grey when the eye views it small — blurred saturation fell
    to p90 0.353 against the painting's 0.474. Per-pixel saturation was never the
    problem; it measured HIGHER than the reference throughout.

    So the colour field is looked up against a BLURRED luminance, which produces
    the flat washes a watercolour actually has, and the drawing's fine detail is
    added back separately and more sparingly as line work over the top.
    """
    a = np.asarray(Image.open(layer).convert("RGBA")).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3]
    luma = rgb @ np.array([0.299, 0.587, 0.114], np.float32)

    # 1. colour field: looked up against a BLURRED tone, so hue and chroma vary
    #    smoothly across the animal the way a wash does
    base = luma if wash <= 0 else np.asarray(
        Image.fromarray(luma.astype(np.uint8)).filter(ImageFilter.GaussianBlur(wash))
    ).astype(np.float32)
    field = lut[np.clip(np.interp(base, np.arange(BINS), curve).astype(int), 0, BINS - 1)]

    if chroma != 1.0:
        g = (field @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
        field = np.clip(g + chroma * (field - g), 0, 255)

    # 2. lightness: taken from the DRAWING, tone-matched into the reference's
    #    range. Scaling all three channels by v_target/max leaves hue and HSV
    #    saturation exactly untouched (both are scale-invariant) while setting
    #    the value — so the colour comes from the wash and every pen stroke comes
    #    from the drawing. Blurring for colour and then trying to add the detail
    #    back as a highpass does not work: the wash blur eats the mid frequencies
    #    that carry the barnacle stipple and the ventral pleats, and a radius-2
    #    highpass cannot put them back. That version came out looking like flat
    #    vector art.
    v_target = np.interp(luma, np.arange(BINS), curve)
    mx = field.max(2)
    scale = np.where(mx > 1.0, v_target / np.maximum(mx, 1e-6), 0.0)
    out = np.clip(field * scale[..., None], 0, 255)

    # optional extra bite on the finest strokes
    if detail > 0:
        blur = np.asarray(Image.fromarray(luma.astype(np.uint8))
                          .filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32)
        out = np.clip(out + detail * (luma - blur)[..., None], 0, 255)

    return Image.fromarray(np.dstack([out, alpha]).astype(np.uint8), "RGBA")


def palette_chart(lut: np.ndarray, share: np.ndarray, ref: Path) -> Image.Image:
    """The spectrum, labelled — band number, intensity range, hex, coverage."""
    rowh, w = 54, 760
    img = Image.new("RGB", (w, rowh * SWATCHES + 64), (250, 250, 248))
    d = ImageDraw.Draw(img)
    d.text((16, 14), f"SPECTRUM  <-  {ref.name}", fill=(20, 20, 24))
    d.text((16, 32), f"{SWATCHES} bands of {BINS // SWATCHES} intensity levels; "
                     f"colour is the mean of the reference's pixels in that band",
           fill=(110, 110, 116))
    step = BINS // SWATCHES
    for i in range(SWATCHES):
        lo, hi = i * step, (i + 1) * step - 1
        col = tuple(int(v) for v in lut[lo:hi + 1].mean(0))
        pct = 100 * share[lo:hi + 1].sum()
        y = 64 + i * rowh
        d.rectangle([16, y, 220, y + rowh - 8], fill=col, outline=(220, 220, 218))
        d.text((236, y + 6),  f"band {i:02d}   intensity {lo:3d}-{hi:3d}", fill=(20, 20, 24))
        d.text((236, y + 24), f"#{col[0]:02X}{col[1]:02X}{col[2]:02X}"
                              f"    {pct:5.1f}% of the reference", fill=(110, 110, 116))
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", type=Path, required=True, help="reference painting")
    ap.add_argument("--detail", type=float, default=0.15,
                    help="how much of the drawing's fine hatch to keep as line work (0-1)")
    ap.add_argument("--wash", type=float, default=9.0,
                    help="blur radius of the colour field; larger = flatter washes")
    ap.add_argument("--bias", type=float, default=2.0,
                    help="pull tones toward the spectrum's saturated bands (0 = faithful distribution)")
    ap.add_argument("--chroma", type=float, default=1.8,
                    help="chroma multiplier, applied about each pixel's luminance")
    ap.add_argument("--palette-only", action="store_true",
                    help="write wash_palette.png and stop — inspect before committing")
    a = ap.parse_args()

    if not a.ref.exists():
        raise SystemExit(f"reference not found: {a.ref}")
    rig_path = HERE / "whale_rig.json"
    if not rig_path.exists():
        raise SystemExit("run build_whale_sprite.py first — whale_rig.json is missing")

    rgb, mask = load_rgb_and_mask(a.ref)
    print(f"reference   {a.ref.name}  {rgb.shape[1]}x{rgb.shape[0]}, "
          f"subject {100 * mask.mean():.1f}% of frame")
    lut, share = build_spectrum(rgb, mask)

    palette_chart(lut, share, a.ref).save(HERE / "wash_palette.png")
    print(f"spectrum    {BINS} bins -> wash_palette.png")
    dark, light = lut[share.cumsum().searchsorted(0.05)], lut[share.cumsum().searchsorted(0.95)]
    print(f"            darkest 5%  #{int(dark[0]):02X}{int(dark[1]):02X}{int(dark[2]):02X}"
          f"   lightest 5%  #{int(light[0]):02X}{int(light[1]):02X}{int(light[2]):02X}")
    if a.palette_only:
        return

    # the whale's own intensity distribution, weighted by how opaque it is, so
    # feathered edge pixels cannot skew the match
    body = np.asarray(Image.open(HERE / "whale_body.png").convert("RGBA")).astype(np.float32)
    bl = body[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    ba = body[..., 3] / 255.0
    ref_l = (rgb @ np.array([0.299, 0.587, 0.114], np.float32))[mask]
    sat = spectrum_saturation(lut)
    counts = np.bincount(np.clip(ref_l.astype(int), 0, BINS - 1), minlength=BINS).astype(np.float32)
    w = ref_weights(counts, sat, a.bias)
    ref_cdf = np.cumsum(w) / max(np.cumsum(w)[-1], 1e-9)
    curve = match_curve(cdf_of(bl[ba > 0.02], ba[ba > 0.02]), ref_cdf)
    recv = np.interp(np.interp(bl[ba > 0.5], np.arange(BINS), curve), np.arange(BINS), sat)
    print(f"colour      bias {a.bias:.1f} -> whale receives mean spectrum saturation "
          f"{recv.mean():.3f} (of {sat.max():.3f} available)")
    print(f"match       whale {bl[ba > 0.5].mean():.0f} mean intensity "
          f"-> reference {ref_l.mean():.0f}")

    for stem in ("whale_body", "whale_flipper_near", "whale_flipper_far"):
        recolour(HERE / f"{stem}.png", lut, curve, a.detail, a.wash, a.chroma).save(HERE / f"{stem}_wash.png")
    print(f"layers      3 written (wash {a.wash:.1f}, chroma {a.chroma:.2f}, detail {a.detail:.2f})")

    def uri(p: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()

    html = (TEMPLATE.read_text()
            .replace("{{BODY_DATA_URI}}", uri(HERE / "whale_body_wash.png"))
            .replace("{{NEAR_DATA_URI}}", uri(HERE / "whale_flipper_near_wash.png"))
            .replace("{{FAR_DATA_URI}}", uri(HERE / "whale_flipper_far_wash.png"))
            .replace("{{THEME_DEFAULT}}", "wash")
            .replace("{{RIG_JSON}}", rig_path.read_text()))
    (HERE / "index_wash.html").write_text(html)
    print(f"index_wash.html {(HERE / 'index_wash.html').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

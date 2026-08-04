#!/usr/bin/env python3
"""
measure_source.py — score a drawing against what the reveal pipeline needs.

The pandanus animates the way it does because of measurable properties of the
source file, not because of anything in the animation code. This reports those
properties for any drawing so a new one can be checked before it is built,
rather than after it turns out to invert into a photographic negative.

Run:
  python3 measure_source.py sources/*.png
  python3 measure_source.py --json sources/whale.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

# Must stay identical to build_reveal.py or the numbers describe a different
# image than the one that actually gets built.
UNSHARP = (1.0, 45, 3)
BLACK_POINT = 0.0015
CLEAN_FLOOR = 0.014
GAMMA = 1.06
BBOX_INK = 0.06
BBOX_MIN_PX = 3
CROP_MARGIN = 44

# What actually decides whether a drawing survives inversion is whether it has a
# BACKGROUND — not how dense it is. Inversion turns the largest area of paper
# into the largest area of ink, so a drawing with blank paper behind it inverts
# cleanly at any density, and a drawing with a sky behind it never does.
#
# The v2 emblem set proved that. An early cut of this gate also capped ink
# coverage at 35%, on the theory that dense = bad. The school satchel is 54%
# dense once cropped and renders perfectly; the parkland scene is 77% dense and
# renders as a photographic negative. Density was a proxy that happened to
# correlate on the first nine files, and it broke on the tenth. Coverage and
# solid mass are still reported — they are useful for judging visual weight —
# but they are no longer pass/fail.
#
#                       pandanus  whale  tree  satchel | scenes (worst)
#   paper_purity_pct       100.0   98.5  100.0   100.0 | golf 44.2
#   edge_contact_pct         0.0    0.0    0.0     0.0 | lake 34.1
#   largest_blob_pct        98.4   99.0   99.2    99.6 | golf 84.5
LIMITS = {
    "paper_purity_pct":   (">=", 95.0),   # is there blank paper behind the subject
    "edge_contact_pct":   ("<=", 2.0),    # does the subject run off the frame
    "subject_ink_pct":    (">=", 70.0),   # is the FORM built from strokes (see below)
}

# Only enforced with --growth. Connectivity matters for the geodesic reveal,
# where ink travels THROUGH the drawing and anything detached is unreachable, so
# it pops in at the very end instead of growing. The `develop` reveal orders
# blocks by density and never touches the growth channel, so a detached piece is
# free there — and is often deliberate: the pandanus fruit and the golf ball are
# both detached on purpose, because they are the elements that leave the drawing
# and travel to card 04. Failing a drawing for having the companion element the
# spec asked for would be the gate contradicting itself.
GROWTH_LIMITS = {
    "largest_blob_pct":   (">=", 90.0),
}

# subject_ink_pct — of the pixels inside the subject's own silhouette, how many
# carry ink. It is what decides whether a drawing joins the botanical language:
# cream strokes glowing on black.
#
# The reveal paints ink. A form built from hatch is ink all the way through, so
# inverting it lights the whole form up. A form drawn as an OUTLINE around blank
# paper has nothing inside to light, so inversion yields a black shape with a
# bright edge, and no curve fixes it — gamma can lift faint ink but cannot
# invent ink where the source left paper.
#
#   banksia 88.6   whale 88.8   satchel 88.3   reeds 85.4   tree 81.2   dog 78.3
#   flag_pole_golf 47.8  <- half its own silhouette is blank fabric
#
# The test in words: if you deleted the paper, would the drawing still exist?
# Needs an alpha channel to know where the subject is; reported as None without
# one, and not enforced.

# Reported, never enforced. High values mean a visually heavy drawing that will
# dominate the copy beside it — a judgement call, not a defect.
INFORMATIONAL = ("ink_coverage_pct", "solid_mass_pct")


def ink_of(path: Path) -> tuple[np.ndarray, float]:
    """Read a source as ink coverage, whichever of the three conventions it uses.

    Sources arrive in three forms and all three are legitimate:
      1. dark ink on white paper           — the pandanus, the botanicals
      2. transparent cutout                — the retriever, the satchel
      3. already a light-on-dark plate     — flag_pole_golf_v2.png, drawn as the
                                             finished look rather than as ink
    Form 3 has to be read the other way round or every number comes out
    inverted: it first measured as 0% paper purity and 100% edge contact, which
    described the file's convention rather than anything wrong with the drawing.
    """
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        # Flatten onto white rather than letting convert("RGB") discard alpha —
        # the RGB stored under a transparent pixel is encoder-dependent and is
        # frequently black, which would read as solid ink across the background.
        im = im.convert("RGBA")
        flat = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(flat, im)
    im = im.convert("RGB").filter(ImageFilter.UnsharpMask(*UNSHARP))
    luma = np.asarray(im.convert("L")).astype(np.float32)

    bright = luma[luma > 200].astype(np.uint8)
    if bright.size == 0:
        white = float(luma.max())
    else:
        vals, counts = np.unique(bright, return_counts=True)
        white = float(vals[counts.argmax()])
    if luma.mean() < 96 and im.mode not in ("RGBA", "LA", "P"):
        # Form 3. Ground is the most common DARK tone, not the darkest pixel —
        # these plates sit on a mottled grey, and mapping only true black to
        # zero leaves the whole ground reading as ink.
        dark = luma[luma < 96].astype(np.uint8)
        vals, counts = np.unique(dark, return_counts=True)
        ground = float(vals[counts.argmax()])
        ink = np.clip((luma - ground) / max(white - ground, 1e-6), 0.0, 1.0) ** GAMMA
    else:
        black = float(np.quantile(luma, BLACK_POINT))
        ink = np.clip((white - luma) / max(white - black, 1e-6), 0.0, 1.0) ** GAMMA
    ink[ink < CLEAN_FLOOR] = 0.0
    return ink, white


def crop_to_ink(ink: np.ndarray) -> np.ndarray:
    """The same crop build_reveal.py applies, so density here describes the image
    that actually gets animated rather than the delivered frame. Without this the
    two scripts disagree — the satchel reads 35% uncropped and 54% cropped, and
    only the second number is the one the reader sees."""
    mask = ink > BBOX_INK
    rows = np.where(mask.sum(axis=1) >= BBOX_MIN_PX)[0]
    cols = np.where(mask.sum(axis=0) >= BBOX_MIN_PX)[0]
    if rows.size == 0 or cols.size == 0:
        return ink
    h, w = ink.shape
    return ink[max(0, int(rows.min()) - CROP_MARGIN):min(h, int(rows.max()) + 1 + CROP_MARGIN),
               max(0, int(cols.min()) - CROP_MARGIN):min(w, int(cols.max()) + 1 + CROP_MARGIN)]


def subject_ink(path: Path, full: np.ndarray) -> float | None:
    """Share of the subject's own silhouette that carries ink. Needs alpha."""
    im = Image.open(path)
    if im.mode not in ("RGBA", "LA", "P"):
        return None
    alpha = np.asarray(im.convert("RGBA"))[..., 3]
    if alpha.shape != full.shape or (alpha == 0).mean() < 0.02:
        return None                      # opaque, or a matte rather than a cutout
    sil = alpha > 128
    if not sil.any():
        return None
    return float(((full > 0.02) & sil).sum() / sil.sum() * 100)


def measure(path: Path) -> dict:
    full, white = ink_of(path)
    h, w = full.shape

    # Composition checks read the DELIVERED frame: whether there is blank paper
    # behind the subject, and whether the subject runs off the edge. Density
    # checks read the CROPPED frame, because that is what gets animated.
    ink = crop_to_ink(full)
    has_ink = ink > 0

    # connectivity, as the growth reveal sees it: a block can only be reached by
    # travelling through ink, so a detached element is pinned to the far end and
    # pops in at the very end of the animation instead of growing.
    mask = ink > BBOX_INK
    lbl, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(mask, lbl, range(1, n + 1))
        largest = float(sizes.max() / sizes.sum() * 100)
    else:
        largest, n = 0.0, 0

    # does the subject run off the frame? Measured on the delivered frame — once
    # cropped there is ink at the edge by construction, so cropping first would
    # make every drawing look like it bled off the page.
    fmask = full > BBOX_INK
    border = np.zeros_like(fmask)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    edge_contact = float((fmask & border).sum() / border.sum() * 100)

    # how much of the "paper" is genuinely blank vs a faint wash. A graded or
    # textured background survives CLEAN_FLOOR and inverts into a grey field.
    # Corners of the delivered frame, for the same reason as edge contact.
    corner = min(h, w) // 8
    corners = np.concatenate([
        full[:corner, :corner].ravel(), full[:corner, -corner:].ravel(),
        full[-corner:, :corner].ravel(), full[-corner:, -corner:].ravel()])
    paper_purity = float((corners == 0).mean() * 100)

    return {
        "file": path.name,
        "size": f"{w}x{h}",
        "paper_white": round(white),
        "ink_coverage_pct": round(float(has_ink.mean() * 100), 1),
        "solid_mass_pct": round(float((ink > 0.5).mean() * 100), 1),
        "largest_blob_pct": round(largest, 1),
        "blobs": int(n),
        "edge_contact_pct": round(edge_contact, 1),
        "paper_purity_pct": round(paper_purity, 1),
        "subject_ink_pct": (lambda v: round(v, 1) if v is not None else None)(
            subject_ink(path, full)),
    }


def verdict(m: dict, growth: bool = False) -> tuple[bool, list[str]]:
    fails = []
    checks = {**LIMITS, **(GROWTH_LIMITS if growth else {})}
    for key, (op, limit) in checks.items():
        v = m[key]
        if v is None:            # not measurable on this file — say so, don't fail it
            continue
        if (op == "<=" and v > limit) or (op == ">=" and v < limit):
            fails.append(f"{key} {v} (needs {op} {limit})")
    if not growth and m["largest_blob_pct"] < GROWTH_LIMITS["largest_blob_pct"][1]:
        fails.append(f"note: {m['blobs']} pieces, largest {m['largest_blob_pct']}% — "
                     f"fine for `develop`, but re-check with --growth before using "
                     f"the geodesic reveal")
    return (not [f for f in fails if not f.startswith("note:")]), fails


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--growth", action="store_true",
                    help="also enforce connectivity — required for the geodesic reveal")
    a = ap.parse_args()

    rows = []
    for p in a.paths:
        if not p.exists():
            print(f"missing: {p}", file=sys.stderr)
            continue
        m = measure(p)
        ok, fails = verdict(m, a.growth)
        m["passes"] = ok
        m["fails"] = fails
        rows.append(m)

    if a.json:
        print(json.dumps(rows, indent=2))
        return

    print(f'{"drawing":<34}{"size":>11}{"paper%":>8}{"edge%":>7}{"blob%":>7}{"subj%":>7}{"| ink%":>8}{"solid%":>8}  verdict')
    print("-" * 100)
    for m in sorted(rows, key=lambda r: r["ink_coverage_pct"]):
        print(f"{m['file']:<34}{m['size']:>11}{m['paper_purity_pct']:>8}"
              f"{m['edge_contact_pct']:>7}{m['largest_blob_pct']:>7}"
              f"{(m['subject_ink_pct'] if m['subject_ink_pct'] is not None else '—'):>7}"
              f"{'| ' + str(m['ink_coverage_pct']):>8}{m['solid_mass_pct']:>8}  "
              f"{'PASS' if m['passes'] else 'FAIL'}")
    print()
    for m in sorted(rows, key=lambda r: r["ink_coverage_pct"]):
        if m["fails"]:
            print(f"{m['file']}\n    " + "\n    ".join(m["fails"]))


if __name__ == "__main__":
    main()

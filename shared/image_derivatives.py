"""
Pre-generated image renditions for property photos.

Implements `15_On_Market/03_Audit/IMAGE_DERIVATIVES_SPEC.md`. The blob store holds
exactly one rendition per photo — whatever was downloaded — and nginx serves it as a
static file with no transform layer. Listing pages therefore ship ~3,000px originals
into an 800px slot: a 14-photo gallery costs ~10 MB where 1.8 MB would do.

This module writes WebP renditions BESIDE the original, named by width:

    for_sale/robina/<id>/photos/2026-08-10/03.jpg        <- original, never touched
    for_sale/robina/<id>/photos/2026-08-10/03.960.webp

The name is derivable from the original by string substitution alone, so consumers
need no schema change and no second lookup.

Two rules that matter:

  * **Never upscale.** 15 of 120 sampled photos are already <=960px wide. Where the
    source is narrower than the target, no derivative is written and the caller falls
    back to the original.
  * **Only report what was written.** The returned mapping contains a width only if
    that rendition actually exists. A 404 inside a `srcset` costs a request and
    silently degrades selection, so callers must build the set from this return value
    rather than assuming the full width list.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Dict, Optional

from PIL import Image, ImageOps

from shared import blob_storage


class DecodeError(Exception):
    """The stored original could not be decoded as an image.

    Distinct from "no rendition needed" ({}) and from "original missing" (None). The
    blob store contains files with a .jpg extension whose bytes are an HTML error page
    saved by a failed download; those must be counted as failures, not as no-ops.
    """


# Spec §3. 480 for cards/thumbnails, 960 for gallery tiles, 1600 for the opened view.
WIDTHS = (480, 960, 1600)

QUALITY = 80
METHOD = 4  # Pillow WebP effort: 4 is the quality/CPU knee
CONTENT_TYPE = "image/webp"


def derivative_name(blob_name: str, width: int) -> str:
    """`…/03.jpg` -> `…/03.<width>.webp`. Pure string transform, no I/O."""
    stem, _ext = os.path.splitext(blob_name)
    return f"{stem}.{width}.webp"


def derivative_url(original_url: str, width: int) -> str:
    """Same transform applied to a public URL, for consumers holding only the URL."""
    stem, _ext = os.path.splitext(original_url)
    return f"{stem}.{width}.webp"


def _local_path(container: str, blob_name: str) -> Path:
    root = Path(os.getenv("BLOB_LOCAL_ROOT", "/data/blobs"))
    return root / container / blob_name


def existing_derivatives(container: str, blob_name: str) -> Dict[int, str]:
    """Widths already on disk, as {width: public_url}. Local backend only.

    Used by the backfill to skip work. Returns {} on the azure backend, where a
    filesystem check is meaningless — that path re-encodes rather than guessing.
    """
    if os.getenv("BLOB_BACKEND", "local").strip().lower() != "local":
        return {}
    out: Dict[int, str] = {}
    for w in WIDTHS:
        name = derivative_name(blob_name, w)
        if _local_path(container, name).is_file():
            out[w] = blob_storage.public_url(container, name)
    return out


def make_derivatives(
    container: str,
    blob_name: str,
    data: bytes,
    widths=WIDTHS,
    skip_existing: bool = True,
) -> Dict[int, str]:
    """Write WebP renditions of `data` beside `blob_name`; return {width: public_url}.

    Only widths strictly narrower than the source are generated — a width omitted from
    the result means "no rendition exists", so the caller falls back to the original.
    An empty dict therefore means "decoded fine, nothing to write" and nothing worse.

    Raises `DecodeError` if the stored original is not a decodable image. A per-width
    encode failure is still swallowed (logged, width omitted) — one bad rendition is
    recoverable by fallback; an unreadable source is not, and must be counted.
    """
    targets = sorted(widths, reverse=True)

    have = existing_derivatives(container, blob_name) if skip_existing else {}
    if len(have) == len(targets):
        # Every rendition already on disk. Decoding here would cost a full JPEG decode
        # per photo on every re-run — the dominant cost of a nightly no-op pass.
        return dict(have)

    try:
        im = Image.open(io.BytesIO(data))
        # The TRUE source width decides what we may generate, and must be read before
        # draft() shrinks the raster — otherwise a 3,000px photo drafted to 1,500px
        # would look "too narrow for 1600w" and silently lose its largest rendition.
        true_w = im.size[0]
        # libjpeg can decode straight to a 1/2, 1/4 or 1/8 scale. Since every target is
        # a downscale, decoding the full 3,000px raster only to throw most of it away is
        # pure cost — draft() picks a DCT scale no smaller than what we ask for.
        # JPEG only; a no-op for other formats. Must precede load().
        try:
            im.draft("RGB", (targets[0], targets[0]))
        except Exception:
            pass
        im.load()
    except Exception as exc:
        # NOT `return {}`. An undecodable original and a photo that legitimately needs
        # no rendition would then be indistinguishable to the caller — the exact shape
        # Rule 7b exists to prevent, and it hid three corrupt originals on the first
        # real run. A corrupt source is a failure and must be counted as one.
        raise DecodeError(f"{blob_name}: {exc}") from exc

    # Phone photos carry rotation in EXIF; resizing without applying it bakes in a
    # sideways image that the original renders correctly.
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass

    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    out: Dict[int, str] = dict(have)

    # Widest first, each rendition resized from the previous one rather than from the
    # full raster. Downscaling 1600->960->480 is a fraction of the work of three
    # independent LANCZOS passes over the source, and the quality difference at these
    # ratios is not visible.
    cur = im
    for w in targets:
        if true_w <= w:
            continue  # never upscale
        try:
            h = round(cur.size[1] * w / cur.size[0])
            nxt = cur.resize((w, h), Image.LANCZOS)
        except Exception as exc:
            print(f"    ✗ derivative {w}w resize failed for {blob_name}: {exc}", flush=True)
            continue
        cur = nxt          # chain regardless of whether this width needed writing
        if w in out:
            continue
        try:
            buf = io.BytesIO()
            nxt.save(buf, "WEBP", quality=QUALITY, method=METHOD)
            url = blob_storage.upload(
                container, derivative_name(blob_name, w), buf.getvalue(),
                content_type=CONTENT_TYPE,
            )
            if url:
                out[w] = url
        except Exception as exc:
            print(f"    ✗ derivative {w}w failed for {blob_name}: {exc}", flush=True)

    return out


def make_derivatives_from_disk(
    container: str, blob_name: str, skip_existing: bool = True
) -> Optional[Dict[int, str]]:
    """Read an already-mirrored original off the local disk and derive from it.

    Three outcomes, deliberately distinct, because the backfill counts them separately
    and a heartbeat that conflates them reports success while doing nothing:

        None            original is not on disk
        DecodeError     original is on disk but is not a decodable image
        {} or {w: url}  original decoded; renditions written, or none were needed
    """
    path = _local_path(container, blob_name)
    try:
        data = path.read_bytes()
    except Exception:
        return None
    return make_derivatives(container, blob_name, data, skip_existing=skip_existing)

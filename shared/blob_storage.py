"""
Blob storage abstraction — write-side only.

Two backends, switched by BLOB_BACKEND env var:
  - "local" (default): writes to BLOB_LOCAL_ROOT on the VM, returns
    public URL under BLOB_PUBLIC_BASE_URL/<container>/<blob_name>.
  - "azure": writes to Azure Storage via AZURE_STORAGE_CONNECTION_STRING
    (legacy path, kept so we can fall back during the cutover window).

Reads are not abstracted — callers fetch via the public URL stored in
MongoDB, which goes through nginx → /data/blobs (local) or Azure (legacy).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _backend() -> str:
    return os.getenv("BLOB_BACKEND", "local").strip().lower()


def _local_root() -> Path:
    return Path(os.getenv("BLOB_LOCAL_ROOT", "/data/blobs"))


def _public_base() -> str:
    return os.getenv("BLOB_PUBLIC_BASE_URL", "https://blobs.fieldsestate.com.au").rstrip("/")


# Hosts that no longer serve anything. The Azure `fieldspropertyimages` account was
# retired 2026-05-28 and now answers 403 "account is disabled", but ~20k stored
# documents still carry those URLs. The blob PATHS are unchanged — the same objects
# are served by nginx from /data/blobs under BLOB_PUBLIC_BASE_URL — so a dead URL is
# recoverable by host substitution alone.
DEAD_BLOB_HOSTS = (
    "fieldspropertyimages.blob.core.windows.net",
)


def to_live_url(url: Optional[str]) -> Optional[str]:
    """Rewrite a dead-Azure blob URL to its live equivalent (identical path).

    Mirrors `toLiveBlobUrl` in the website's netlify/functions/shared-utils.mjs. The
    website already did this; the Python pipeline did not, so step 106 (floor plan
    vision) burned 54 analyses on 403s in the 2026-08-01 run while the same images
    sat live on the replacement host. Non-dead URLs and falsy input pass through.
    """
    if not url or not isinstance(url, str):
        return url
    for host in DEAD_BLOB_HOSTS:
        if host in url:
            return url.replace(host, _public_base().split("://", 1)[-1])
    return url


# Magic-byte signatures for every raster format we could plausibly be handed.
# (offset, signature) — offset 0 unless the container puts a length prefix first.
_IMAGE_MAGIC = (
    (0, b"\xff\xd8\xff",     "jpeg"),
    (0, b"\x89PNG\r\n\x1a\n", "png"),
    (0, b"GIF87a",           "gif"),
    (0, b"GIF89a",           "gif"),
    (0, b"BM",               "bmp"),
    (0, b"II*\x00",          "tiff"),
    (0, b"MM\x00*",          "tiff"),
    (0, b"\x00\x00\x01\x00", "ico"),
)


def sniff_image_format(data: bytes) -> Optional[str]:
    """Return a short format name if `data` really is an image, else None.

    Extension and Content-Type both lie: on 2026-08-13 six Matterport 3D tour
    pages (~200 KB of HTML each) were found stored as `.jpg` photos because the
    downloader trusted HTTP 200 and the uploader hard-coded `image/jpeg`. Only
    the bytes are authoritative. See 15_On_Market/HANDOFF_two_live_defects.md.
    """
    if not data or len(data) < 12:
        return None
    for offset, sig, name in _IMAGE_MAGIC:
        if data[offset:offset + len(sig)] == sig:
            return name
    # RIFF containers: "RIFF" <4-byte size> "WEBP"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    # ISO-BMFF: "....ftyp" + brand — AVIF / HEIC / HEIF
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis", b"heic", b"heix", b"heim", b"heis",
                     b"hevc", b"hevx", b"mif1", b"msf1"):
            return brand.decode("ascii", "replace")
    return None


def _looks_like_markup(data: bytes) -> bool:
    """True if the payload opens like HTML/XML — the common non-image impostor."""
    head = data[:512].lstrip()[:64].lower()
    return head.startswith((b"<!doctype", b"<html", b"<?xml", b"<head", b"<body"))


def upload(
    container: str,
    blob_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    cache_control: str = "public, max-age=31536000",
) -> Optional[str]:
    """Upload bytes; return the public URL or None on failure.

    blob_name uses forward slashes as path separators.

    If `content_type` claims an image, the bytes are sniffed first and the
    upload is REFUSED when they aren't one. Callers already treat None as a
    failed upload and drop the URL from the list, so a rejected impostor never
    reaches a gallery.
    """
    if content_type.startswith("image/"):
        fmt = sniff_image_format(data)
        if fmt is None:
            kind = "HTML/XML document" if _looks_like_markup(data) else "unrecognised data"
            print(
                f"    ✗ REFUSED non-image upload ({kind}, {len(data)} bytes) "
                f"declared as {content_type}: {container}/{blob_name}",
                flush=True,
            )
            return None

    backend = _backend()
    if backend == "local":
        try:
            target = _local_root() / container / blob_name
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
            return f"{_public_base()}/{container}/{blob_name}"
        except Exception as exc:
            print(f"    ✗ Local blob write failed: {exc}", flush=True)
            return None

    if backend == "azure":
        from azure.storage.blob import BlobServiceClient, ContentSettings  # lazy
        cs = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if not cs:
            print("    ✗ AZURE_STORAGE_CONNECTION_STRING not set", flush=True)
            return None
        try:
            svc = BlobServiceClient.from_connection_string(cs)
            bc = svc.get_blob_client(container=container, blob=blob_name)
            bc.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(
                    content_type=content_type,
                    cache_control=cache_control,
                ),
            )
            return f"https://{svc.account_name}.blob.core.windows.net/{container}/{blob_name}"
        except Exception as exc:
            print(f"    ✗ Azure blob upload failed: {exc}", flush=True)
            return None

    print(f"    ✗ Unknown BLOB_BACKEND={backend!r} (expected 'local' or 'azure')", flush=True)
    return None


def public_url(container: str, blob_name: str) -> str:
    """Compute the canonical public URL for a blob name (does not check existence)."""
    if _backend() == "azure":
        cs = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        account = cs.split("AccountName=")[1].split(";")[0] if "AccountName=" in cs else ""
        return f"https://{account}.blob.core.windows.net/{container}/{blob_name}"
    return f"{_public_base()}/{container}/{blob_name}"

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


def upload(
    container: str,
    blob_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    cache_control: str = "public, max-age=31536000",
) -> Optional[str]:
    """Upload bytes; return the public URL or None on failure.

    blob_name uses forward slashes as path separators.
    """
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

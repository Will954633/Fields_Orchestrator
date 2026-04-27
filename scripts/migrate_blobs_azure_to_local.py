"""One-shot bulk migration: Azure Blob Storage → /data/blobs.

Resumable: skips files that already exist locally with the same size.
Streams per-blob (no large in-memory buffers).
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from shared.env import load_env  # type: ignore
from azure.storage.blob import BlobServiceClient

load_env()

CONNECTION_STRING = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
LOCAL_ROOT = Path(os.environ.get("BLOB_LOCAL_ROOT", "/data/blobs"))
CONTAINERS = ["property-images", "accounting", "knowledge-base"]
THREADS = 16
PROGRESS_EVERY = 200


def migrate_one(svc: BlobServiceClient, container: str, blob_name: str, blob_size: int) -> tuple[str, int, str]:
    target = LOCAL_ROOT / container / blob_name
    if target.exists() and target.stat().st_size == blob_size:
        return ("skip", blob_size, blob_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        bc = svc.get_blob_client(container=container, blob=blob_name)
        with open(tmp, "wb") as f:
            stream = bc.download_blob(max_concurrency=2)
            for chunk in stream.chunks():
                f.write(chunk)
        tmp.replace(target)
        return ("ok", blob_size, blob_name)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return ("err", 0, f"{blob_name}: {exc}")


def migrate_container(svc: BlobServiceClient, container: str) -> dict:
    print(f"\n=== {container} ===", flush=True)
    cc = svc.get_container_client(container)
    counts = {"ok": 0, "skip": 0, "err": 0}
    bytes_done = 0
    t0 = time.time()
    last_print = t0

    with ThreadPoolExecutor(max_workers=THREADS) as ex:
        futures = []
        for b in cc.list_blobs():
            futures.append(ex.submit(migrate_one, svc, container, b.name, b.size or 0))
            if len(futures) >= 5000:  # drain to bound memory
                for fut in as_completed(futures):
                    status, size, name = fut.result()
                    counts[status] += 1
                    bytes_done += size
                    if (counts["ok"] + counts["skip"]) % PROGRESS_EVERY == 0 and time.time() - last_print > 5:
                        rate = bytes_done / 1024 / 1024 / max(time.time() - t0, 1)
                        print(f"  {container}: ok={counts['ok']:,} skip={counts['skip']:,} err={counts['err']:,} bytes={bytes_done/1024/1024:,.0f} MB rate={rate:.1f} MB/s", flush=True)
                        last_print = time.time()
                futures = []
        for fut in as_completed(futures):
            status, size, name = fut.result()
            counts[status] += 1
            bytes_done += size

    elapsed = time.time() - t0
    print(f"DONE {container}: ok={counts['ok']:,} skip={counts['skip']:,} err={counts['err']:,} bytes={bytes_done/1024/1024/1024:.2f} GB in {elapsed/60:.1f}m", flush=True)
    return counts


def main() -> int:
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
    overall = {"ok": 0, "skip": 0, "err": 0}
    for c in CONTAINERS:
        r = migrate_container(svc, c)
        for k in overall:
            overall[k] += r[k]
    print(f"\nOVERALL: {overall}", flush=True)
    return 1 if overall["err"] else 0


if __name__ == "__main__":
    sys.exit(main())

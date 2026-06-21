"""
Off-VM backup of the compliance records (items K, L, N).

The primary store is MongoDB on the VM. This mirrors all three compliance
collections off the VM so the records survive a VM loss and can be handed to an
auditor/insurer as openable files.

Two off-site targets:
  1. GCS bucket gs://fields-blob-backup/compliance/  — RELIABLE, automated.
     Writes via the VM's gcloud user creds (no token expiry). Always runs.
  2. Google Drive  Compliance/                       — human/auditor-friendly.
     BEST-EFFORT via the OAuth creds the gdrive MCP uses. Skipped (with a clear
     warning) when the OAuth token is invalid — that token is testing-mode and
     expires ~weekly, so it is NOT relied on for the guaranteed backup. To make
     Drive hands-off, move the OAuth app to production, or add a Shared Drive /
     domain-wide delegation for the floor-plan SA (see the audit doc).

Records contain addresses / owner data → these targets only, NEVER GitHub.

Usage:
  python3 -m scripts.compliance.offsite_backup            # export + GCS + Drive(best-effort)
  python3 -m scripts.compliance.offsite_backup --gcs-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from pymongo import MongoClient

COLLECTIONS = ["appraisal_archive", "credential_register", "licensee_signoff"]
EXPORT_DIR = Path("/home/fields/Fields_Orchestrator/compliance_exports")
GCS_BASE = "gs://fields-blob-backup/compliance"
OAUTH_KEYS = "/home/fields/.gdrive-oauth.keys.json"
OAUTH_TOKEN = "/home/fields/.gdrive-server-credentials.json"


def _db():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        sys.exit("COSMOS_CONNECTION_STRING not set")
    return MongoClient(conn)["system_monitor"]


def export_local() -> Dict[str, Any]:
    """Dump each collection to JSON + a manifest with per-file sha256."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    db = _db()
    manifest: Dict[str, Any] = {"generated_at": datetime.utcnow().isoformat() + "Z", "files": {}}
    for coll in COLLECTIONS:
        rows: List[Dict[str, Any]] = list(db[coll].find())
        path = EXPORT_DIR / f"{coll}.json"
        blob = json.dumps(rows, default=str, indent=2, sort_keys=True)
        path.write_text(blob)
        manifest["files"][coll] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(blob.encode()).hexdigest(),
            "bytes": len(blob),
        }
        print(f"  exported {coll}: {len(rows)} rows")
    (EXPORT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def push_gcs() -> bool:
    """Mirror to GCS: a dated immutable snapshot + a 'latest' copy."""
    date = datetime.utcnow().strftime("%Y-%m-%d")
    ok = True
    for dest in (f"{GCS_BASE}/snapshots/{date}/", f"{GCS_BASE}/latest/"):
        r = subprocess.run(["gsutil", "-m", "cp", str(EXPORT_DIR / "*.json"), dest],
                           capture_output=True, text=True, shell=False)
        # gsutil glob needs shell expansion; fall back to explicit file list.
        if r.returncode != 0:
            files = [str(p) for p in EXPORT_DIR.glob("*.json")]
            r = subprocess.run(["gsutil", "-m", "cp", *files, dest], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  GCS ✓ {dest}")
        else:
            print(f"  GCS ✗ {dest}: {r.stderr.strip()[:160]}")
            ok = False
    return ok


def push_drive() -> bool:
    """Best-effort Drive mirror via the MCP OAuth creds. Returns False (without
    raising) when the token is invalid — that is expected weekly until the OAuth
    app is productionised or the SA gets Shared-Drive/DWD access."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except Exception as e:
        print(f"  Drive skipped — libs unavailable: {e}")
        return False
    try:
        keys = json.load(open(OAUTH_KEYS)).get("installed") or json.load(open(OAUTH_KEYS))
        tok = json.load(open(OAUTH_TOKEN))
        creds = Credentials(
            token=tok.get("access_token"),
            refresh_token=tok.get("refresh_token"),
            token_uri=keys.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=keys.get("client_id"),
            client_secret=keys.get("client_secret"),
            scopes=tok.get("scope", "").split() or ["https://www.googleapis.com/auth/drive"],
        )
        creds.refresh(Request())  # raises on invalid_grant
        svc = build("drive", "v3", credentials=creds, cache_discovery=False)

        def folder(name: str, parent: str = None) -> str:
            q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
                 f"and trashed=false" + (f" and '{parent}' in parents" if parent else ""))
            hits = svc.files().list(q=q, fields="files(id)", spaces="drive").execute().get("files", [])
            if hits:
                return hits[0]["id"]
            meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
            if parent:
                meta["parents"] = [parent]
            return svc.files().create(body=meta, fields="id").execute()["id"]

        root = folder("Compliance")
        for sub in ("Appraisals", "Credentials", "Marketing-Signoff"):
            folder(sub, root)
        for p in EXPORT_DIR.glob("*.json"):
            existing = svc.files().list(
                q=f"name='{p.name}' and '{root}' in parents and trashed=false",
                fields="files(id)").execute().get("files", [])
            media = MediaFileUpload(str(p), mimetype="application/json", resumable=False)
            if existing:
                svc.files().update(fileId=existing[0]["id"], media_body=media).execute()
            else:
                svc.files().create(body={"name": p.name, "parents": [root]},
                                   media_body=media, fields="id").execute()
        print("  Drive ✓ Compliance/ mirrored")
        return True
    except Exception as e:
        print(f"  Drive skipped — auth/token issue ({str(e)[:90]}). GCS copy is authoritative.")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Off-VM backup of compliance records (K/L/N)")
    ap.add_argument("--gcs-only", action="store_true")
    args = ap.parse_args()
    export_local()
    gcs_ok = push_gcs()
    drive_ok = True if args.gcs_only else push_drive()
    print(f"\noffsite_backup: gcs={'ok' if gcs_ok else 'FAIL'} "
          f"drive={'skipped' if args.gcs_only else ('ok' if drive_ok else 'skipped')}")
    # GCS is the guaranteed tier — fail the job only if it fails.
    sys.exit(0 if gcs_ok else 1)


if __name__ == "__main__":
    main()

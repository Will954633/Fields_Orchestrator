#!/usr/bin/env python3
"""
05_archive.py — stage 05: move a finished video project off the root disk.

The root disk is 97G and video eats it (the 2026-09-11 disk incident that broke
three nights of MongoDB backups was part-caused by 5.4G of finished video sitting
here). Editing happens on the VM; the moment a project ships, it gets archived:

  PRIMARY  /data/blobs/video_archive/<Project>/   (738G disk; auto-synced off-site
           nightly by the 03:00 cron  gsutil rsync /data/blobs → gs://fields-blob-backup)
  OPTIONAL Google Drive folder "Video_Archive"    (--drive; Will's browser access)
           https://drive.google.com/drive/folders/1cIrw53ggePRR0eVZ0Jf8nq43NsHdAJ8D

Usage:
  python3 scripts/05_archive.py --project Robina_August_V2            # copy + verify
  python3 scripts/05_archive.py --project Robina_August_V2 --purge    # …then delete local
  python3 scripts/05_archive.py --project Burleigh_Waters --purge --drive
  python3 scripts/05_archive.py --work --purge      # archive+clear the shared work/ + qa/
                                                    # scratch under the current config slug
  python3 scripts/05_archive.py --project X --dry-run

Safety:
  - --purge NEVER runs unless the byte-for-byte checksum verify of the blob copy
    passes. Raw footage is unrecoverable; the copy is proven before the delete.
  - The Drive leg is best-effort: the shared OAuth token dies every 7 days while
    the consent screen is in Testing mode (see memory gdrive-oauth-7day-expiry).
    A dead token fails the Drive leg with a re-auth pointer but does NOT block
    the blob archive, which is the durable copy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent          # Video_Editing_Process/
ARCHIVE_ROOT = Path("/data/blobs/video_archive")
DRIVE_FOLDER_ID = "1cIrw53ggePRR0eVZ0Jf8nq43NsHdAJ8D"
OAUTH_KEYS = Path("/home/fields/.gdrive-oauth.keys.json")
OAUTH_TOKEN = Path("/home/fields/.gdrive-server-credentials.json")

REAUTH_HINT = (
    "Drive token dead (7-day Testing-mode expiry). Re-auth procedure: memory file "
    "gdrive_oauth_7day_expiry.md — needs Will in-session (~5 min). The blob archive "
    "above is the durable copy; re-run with --drive-only later to push to Drive."
)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def die(msg: str) -> None:
    log(f"ERROR: {msg}")
    sys.exit(1)


def dir_stats(root: Path) -> tuple[int, int]:
    files = [p for p in root.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def rsync(src: Path, dst: Path, extra: list[str] | None = None) -> None:
    cmd = ["rsync", "-a", *(extra or []), f"{src}/", f"{dst}/"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"rsync failed rc={r.returncode}: {r.stderr[:500]}")


def verify_checksum(src: Path, dst: Path) -> None:
    """Byte-level verify: rsync dry-run with --checksum lists any differing file.
    Empty output == every file identical. This is what licenses --purge."""
    r = subprocess.run(
        ["rsync", "-anc", "--delete", "--out-format=%n", f"{src}/", f"{dst}/"],
        capture_output=True, text=True)
    if r.returncode != 0:
        die(f"verify rsync failed rc={r.returncode}: {r.stderr[:500]}")
    diffs = [l for l in r.stdout.splitlines() if l and not l.endswith("/")]
    if diffs:
        die(f"verify FAILED — {len(diffs)} file(s) differ, e.g. {diffs[:5]}")


def archive_dir(src: Path, dest_name: str, purge: bool, dry: bool) -> Path:
    dst = ARCHIVE_ROOT / dest_name
    n, b = dir_stats(src)
    log(f"{src} → {dst}  ({n} files, {b / 1e9:.2f} GB)")
    if dry:
        log("dry-run: no copy made")
        return dst
    dst.mkdir(parents=True, exist_ok=True)
    rsync(src, dst)
    log("copy done; verifying checksums (reads both sides fully)…")
    verify_checksum(src, dst)
    log("verify OK — blob copy is byte-identical")
    manifest = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "source": str(src), "files": n, "bytes": b,
        "gcs_note": "synced nightly to gs://fields-blob-backup by 03:00 cron",
    }
    (dst / "archive_manifest.json").write_text(json.dumps(manifest, indent=2))
    if purge:
        shutil.rmtree(src)
        log(f"purged local copy: {src}")
    else:
        log("local copy kept (pass --purge to delete after verify)")
    return dst


# ── Google Drive leg ─────────────────────────────────────────────────────────

def drive_token() -> str | None:
    import requests
    try:
        keys = json.loads(OAUTH_KEYS.read_text())
        tok = json.loads(OAUTH_TOKEN.read_text())
        k = keys.get("installed") or keys.get("web") or keys
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": k["client_id"], "client_secret": k["client_secret"],
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token",
        }, timeout=20)
        if not r.ok:
            log(f"Drive auth failed: {r.json().get('error', r.status_code)}")
            return None
        return r.json()["access_token"]
    except Exception as e:
        log(f"Drive auth failed: {e}")
        return None


def drive_mkdir(at: str, name: str, parent: str) -> str:
    import requests
    h = {"Authorization": f"Bearer {at}"}
    q = (f"name = '{name}' and '{parent}' in parents and "
         "mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    r = requests.get("https://www.googleapis.com/drive/v3/files",
                     headers=h, params={"q": q, "fields": "files(id)"}, timeout=20)
    r.raise_for_status()
    hits = r.json().get("files", [])
    if hits:
        return hits[0]["id"]
    r = requests.post("https://www.googleapis.com/drive/v3/files", headers=h, json={
        "name": name, "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent]}, timeout=20)
    r.raise_for_status()
    return r.json()["id"]


def drive_existing(at: str, name: str, parent: str) -> tuple[str, int] | None:
    import requests
    q = f"name = '{name}' and '{parent}' in parents and trashed = false"
    r = requests.get("https://www.googleapis.com/drive/v3/files",
                     headers={"Authorization": f"Bearer {at}"},
                     params={"q": q, "fields": "files(id,size)"}, timeout=20)
    r.raise_for_status()
    hits = r.json().get("files", [])
    if not hits:
        return None
    return hits[0]["id"], int(hits[0].get("size", -1))


def drive_upload(at: str, path: Path, parent: str) -> bool:
    """Resumable upload; verifies Drive-reported size matches the local file.
    Idempotent: a file already present with the same name AND size is skipped;
    a same-name size-mismatch is trashed and re-uploaded. Returns True if the
    file was already there (skipped)."""
    import requests
    h = {"Authorization": f"Bearer {at}"}
    size = path.stat().st_size
    existing = drive_existing(at, path.name, parent)
    if existing:
        eid, esize = existing
        if esize == size:
            return True
        requests.patch(f"https://www.googleapis.com/drive/v3/files/{eid}",
                       headers=h, params={"fields": "id"}, json={"trashed": True},
                       timeout=20).raise_for_status()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # NB fields=size on the INITIATION url — without it the finalise response
    # omits size and the verify below reads -1 (the 2026-09-12 first-push bug).
    r = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name,size",
        headers={**h, "X-Upload-Content-Type": mime,
                 "X-Upload-Content-Length": str(size)},
        json={"name": path.name, "parents": [parent]}, timeout=30)
    r.raise_for_status()
    session = r.headers["Location"]
    if size == 0:
        r = requests.put(session, data=b"", headers={"Content-Range": "bytes */0"},
                         timeout=60)
        r.raise_for_status()
        return False
    CHUNK = 32 * 1024 * 1024
    with path.open("rb") as f:
        sent = 0
        while sent < size:
            data = f.read(CHUNK)
            end = sent + len(data)
            r = requests.put(session, data=data, headers={
                "Content-Range": f"bytes {sent}-{end - 1}/{size}"}, timeout=600)
            if r.status_code in (200, 201):
                got = int(r.json().get("size", -1))
                if got != size:
                    raise RuntimeError(f"Drive size mismatch {path.name}: {got} != {size}")
                return False
            if r.status_code != 308:
                raise RuntimeError(f"upload {path.name} failed: {r.status_code} {r.text[:200]}")
            sent = end
    raise RuntimeError(f"upload {path.name}: stream ended without Drive finalising")


def drive_push(archived: Path, dest_name: str) -> bool:
    at = drive_token()
    if not at:
        log(REAUTH_HINT)
        return False
    log(f"Drive: pushing {dest_name} → folder {DRIVE_FOLDER_ID}")
    parent = DRIVE_FOLDER_ID
    for part in dest_name.split("/"):          # "slug_scratch/work" → nested folders
        parent = drive_mkdir(at, part, parent)
    folders = {archived: parent}

    def ensure_folder(d: Path) -> str:
        if d not in folders:
            folders[d] = drive_mkdir(at, d.name, ensure_folder(d.parent))
        return folders[d]

    ok = fail = skipped = 0
    for p in sorted(archived.rglob("*")):
        if p.is_file():
            try:
                if drive_upload(at, p, ensure_folder(p.parent)):
                    skipped += 1
                else:
                    ok += 1
            except Exception as e:
                log(f"  FAILED {p.relative_to(archived)}: {e}")
                fail += 1
    log(f"Drive: {ok} uploaded, {skipped} already present, {fail} failed")
    return fail == 0


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="name under assets/, or an explicit dir path")
    ap.add_argument("--work", action="store_true",
                    help="archive the shared work/ + qa/ + out/ dirs under the current "
                         "config.yaml slug (use when a build is fully shipped)")
    ap.add_argument("--purge", action="store_true",
                    help="delete the local copy after the checksum verify passes")
    ap.add_argument("--drive", action="store_true",
                    help="also push the archive to the Google Drive Video_Archive folder")
    ap.add_argument("--drive-only", action="store_true",
                    help="skip copy/purge; push an ALREADY-archived project to Drive")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.project and not args.work:
        ap.error("need --project and/or --work")
    if not ARCHIVE_ROOT.parent.exists():
        die("/data/blobs not mounted — refusing to archive onto the root disk")

    targets: list[tuple[Path, str]] = []
    if args.project:
        src = Path(args.project)
        if not src.is_dir():
            src = BASE / "assets" / args.project
        if not src.is_dir() and not args.drive_only:
            die(f"no such project dir: {args.project} (looked in assets/)")
        targets.append((src, src.name))
    if args.work:
        import yaml
        slug = yaml.safe_load((BASE / "config.yaml").read_text())["project"]["slug"]
        dest = f"{slug}_scratch"
        # out/ is included: the social circle .movs ship nowhere else — the website
        # repo only ever receives the web mp4.
        for d in (BASE / "work", BASE / "qa", BASE / "out"):
            if d.is_dir():
                targets.append((d, f"{dest}/{d.name}"))

    all_drive_ok = True
    for src, dest_name in targets:
        if args.drive_only:
            archived = ARCHIVE_ROOT / dest_name
            if not archived.is_dir():
                die(f"{archived} not found — archive it first (without --drive-only)")
        else:
            archived = archive_dir(src, dest_name, purge=args.purge, dry=args.dry_run)
        if (args.drive or args.drive_only) and not args.dry_run:
            all_drive_ok &= drive_push(archived, dest_name)

    log("done" + ("" if all_drive_ok else " (Drive leg incomplete — see above)"))
    sys.exit(0 if all_drive_ok else 2)


if __name__ == "__main__":
    main()

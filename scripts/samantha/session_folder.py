#!/usr/bin/env python3
"""
session_folder.py — deterministic dated SESSION FOLDER inside Samantha's Drive folder.

Will's ask (2026-07-27): every session's outputs — the session summary, any scoping
documents created during the session, and anything else Samantha wants to share — go
into ONE dedicated folder named for today's date, inside her Drive folder, instead of
being dropped loosely in the root (which had become cluttered). Telegram stays the
push channel; this is the durable, browsable home for what a session produced.

Uses the same OAuth creds task_board.py / running_doc.py use (Drive scope).

Usage:
  python3 scripts/samantha/session_folder.py ensure            # create/get today's folder -> prints id + link
  python3 scripts/samantha/session_folder.py ensure --quiet    # prints ONLY the folder id (for scripting)
  python3 scripts/samantha/session_folder.py put --file X [--name N]   # upload a local file into today's folder
  python3 scripts/samantha/session_folder.py link              # print today's folder link (create if missing)
  (all accept --date YYYY-MM-DD; default = today AEST)
"""
from __future__ import annotations
import argparse, json, mimetypes, os, warnings
from datetime import datetime, timezone, timedelta
warnings.filterwarnings("ignore")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

OAUTH_KEYS = "/home/fields/.gdrive-oauth.keys.json"
SERVER_CREDS = "/home/fields/.gdrive-server-credentials.json"
PARENT_FOLDER = "19avOQvAdn5uYiPveNxuXuKaMHEfzgShb"  # Samantha's Drive folder
FOLDER_MIME = "application/vnd.google-apps.folder"


def _creds():
    keys = json.load(open(OAUTH_KEYS))["installed"]; tok = json.load(open(SERVER_CREDS))
    c = Credentials(token=tok.get("access_token"), refresh_token=tok.get("refresh_token"),
        token_uri=keys["token_uri"], client_id=keys["client_id"],
        client_secret=keys["client_secret"], scopes=(tok.get("scope") or "").split())
    if not c.valid:
        c.refresh(Request())
    return c


def _drive():
    return build("drive", "v3", credentials=_creds(), cache_discovery=False)


def _today_aest() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%Y-%m-%d")


def ensure_folder(drive, date_str: str) -> dict:
    name = f"Session {date_str}"
    q = (f"'{PARENT_FOLDER}' in parents and name = '{name}' and "
         f"mimeType = '{FOLDER_MIME}' and trashed = false")
    res = drive.files().list(q=q, fields="files(id,name,webViewLink)",
                             supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    files = res.get("files", [])
    if files:
        return files[0]
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [PARENT_FOLDER]}
    return drive.files().create(body=meta, fields="id,name,webViewLink",
                                supportsAllDrives=True).execute()


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ensure", "link"):
        p = sub.add_parser(name); p.add_argument("--date", default=""); p.add_argument("--quiet", action="store_true")
    p = sub.add_parser("put")
    p.add_argument("--file", required=True); p.add_argument("--name", default="")
    p.add_argument("--date", default="")
    a = ap.parse_args()

    drive = _drive()
    date_str = a.date or _today_aest()
    folder = ensure_folder(drive, date_str)

    if a.cmd in ("ensure", "link"):
        if getattr(a, "quiet", False):
            print(folder["id"])
        else:
            print(f"Session folder: {folder['name']}")
            print(f"  id:   {folder['id']}")
            print(f"  link: {folder.get('webViewLink', 'https://drive.google.com/drive/folders/'+folder['id'])}")
        return 0

    if a.cmd == "put":
        if not os.path.exists(a.file):
            print(f"ERROR: no such file {a.file}"); return 1
        name = a.name or os.path.basename(a.file)
        mime = mimetypes.guess_type(a.file)[0] or "application/octet-stream"
        media = MediaFileUpload(a.file, mimetype=mime, resumable=False)
        f = drive.files().create(body={"name": name, "parents": [folder["id"]]},
                                 media_body=media, fields="id,webViewLink",
                                 supportsAllDrives=True).execute()
        print(f"uploaded '{name}' -> {f.get('webViewLink')}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

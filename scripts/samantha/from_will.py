#!/usr/bin/env python3
"""
from_will.py — Samantha's "From Will" inbox (Google Drive folder).

Will communicates with Samantha by (a) adding his own docs to her Drive folder with
notes/instructions, and (b) commenting on her past daily-report docs. This reads ALL
NEW content from Will since her last pass — new/edited docs AND new comments — and
prints it as a digest she reads FIRST every run.

State: system_monitor.samantha_state doc _id="from_will" holds last_check (ISO).
Auth: reuses the gdrive MCP OAuth creds (auto-refresh). Needs the drive scope to read comments.

Usage:
  python3 scripts/samantha/from_will.py            # show new-since-last-COMMITTED-pass (records a pending mark)
  python3 scripts/samantha/from_will.py --commit   # AFTER you've delivered + actioned: mark it all seen
  python3 scripts/samantha/from_will.py --peek     # show only, record nothing
  python3 scripts/samantha/from_will.py --since 2026-07-01T00:00:00Z

Robustness: reading does NOT advance the "seen" pointer — it only records a *pending* mark. You run
`--commit` at the END of the run, after delivery. So if a run crashes mid-way, the pointer stays put and
the next run RE-READS the same content — nothing Will drops is ever silently lost. In practice an item
keeps showing every run until you've actually processed it and committed.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore")  # silence google-api FutureWarning noise in the digest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from src.mongo_client_factory import get_mongo_client, cosmos_retry  # noqa: E402

from google.oauth2.credentials import Credentials  # noqa: E402
from google.auth.transport.requests import Request  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

FOLDER_ID = "19avOQvAdn5uYiPveNxuXuKaMHEfzgShb"
OAUTH_KEYS = "/home/fields/.gdrive-oauth.keys.json"
SERVER_CREDS = "/home/fields/.gdrive-server-credentials.json"
HER_DOC_PREFIX = "Samantha Daily"  # her own report docs — scan for comments, don't list as "from Will"


def _drive():
    keys = json.load(open(OAUTH_KEYS))["installed"]
    tok = json.load(open(SERVER_CREDS))
    creds = Credentials(
        token=tok.get("access_token"), refresh_token=tok.get("refresh_token"),
        token_uri=keys["token_uri"], client_id=keys["client_id"],
        client_secret=keys["client_secret"], scopes=(tok.get("scope") or "").split(),
    )
    if not creds.valid:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _state():
    return get_mongo_client()["system_monitor"]["samantha_state"]


def _last_check(default_days=30) -> str:
    d = _state().find_one({"_id": "from_will"})
    if d and d.get("last_check"):
        return d["last_check"]
    return (datetime.now(timezone.utc) - timedelta(days=default_days)).isoformat()


def _set_last_check(iso: str) -> None:
    cosmos_retry(lambda: _state().update_one(
        {"_id": "from_will"}, {"$set": {"last_check": iso}}, upsert=True))


def _export_text(svc, f) -> str:
    mt = f.get("mimeType", "")
    try:
        if mt == "application/vnd.google-apps.document":
            # Google Doc = a RUNNING doc: read ACTIVE text only, skipping ORANGE (= done)
            # so completed/irrelevant items are never re-read or re-actioned.
            try:
                from running_doc import active_text  # same dir
                return active_text(f["id"])
            except Exception:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "running_doc", "/home/fields/Fields_Orchestrator/scripts/samantha/running_doc.py")
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod.active_text(f["id"])
            return svc.files().export(fileId=f["id"], mimeType="text/plain").execute().decode("utf-8", "replace")
        if mt.startswith("text/"):
            return svc.files().get_media(fileId=f["id"]).execute().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return f"[could not export: {e}]"
    return f"[binary/{mt} — open via link or read_file MCP if needed]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--peek", action="store_true", help="show only, record nothing")
    ap.add_argument("--commit", action="store_true",
                    help="mark all previously-read content as seen (run AFTER delivery)")
    ap.add_argument("--since", default="")
    args = ap.parse_args()

    # --commit: promote the pending mark to the committed pointer, then exit.
    if args.commit:
        d = _state().find_one({"_id": "from_will"})
        pending = (d or {}).get("pending_check")
        if pending:
            _set_last_check(pending)
            cosmos_retry(lambda: _state().update_one({"_id": "from_will"},
                                                     {"$unset": {"pending_check": ""}}))
            print(f"committed — content up to {pending} marked seen")
        else:
            print("nothing pending to commit")
        return 0

    since = args.since or _last_check()
    now_iso = datetime.now(timezone.utc).isoformat()
    svc = _drive()

    FOLDER_MIME = "application/vnd.google-apps.folder"

    def _list(parent):
        return svc.files().list(
            q=f"'{parent}' in parents and trashed=false",
            fields="files(id,name,mimeType,createdTime,modifiedTime,owners(displayName),webViewLink)",
            orderBy="modifiedTime desc", pageSize=200,
        ).execute().get("files", [])

    # Parent folder + one level into subfolders (esp. the "From Will" subfolder).
    files = _list(FOLDER_ID)
    for sub in [f for f in list(files) if f.get("mimeType") == FOLDER_MIME]:
        files.extend(_list(sub["id"]))

    new_docs, new_comments = [], []
    for f in files:
        name = f.get("name", "")
        if f.get("mimeType") == FOLDER_MIME:
            continue  # a folder is not a note
        is_her_report = name.startswith(HER_DOC_PREFIX)
        is_task_board = name.startswith("Samantha — Task Board")  # separate channel (its "From Will" tab)
        readable = f.get("mimeType") == "application/vnd.google-apps.document" \
            or f.get("mimeType", "").startswith("text/")
        # (a) new/edited readable doc from Will (exclude her own reports + the task board)
        if readable and not is_her_report and not is_task_board \
                and (f.get("createdTime", "") > since or f.get("modifiedTime", "") > since):
            new_docs.append((f, _export_text(svc, f)))
        # (b) new comments on ANY folder file (incl. her reports) since last check
        try:
            comments = svc.comments().list(
                fileId=f["id"], fields="comments(id,content,author/displayName,createdTime,resolved,quotedFileContent/value)",
            ).execute().get("comments", [])
        except Exception:
            comments = []
        for c in comments:
            # Comments are all authored as "Will Simpson" regardless of who actually
            # wrote them (Samantha posts through his OAuth identity, prefixed
            # "Samantha:" per charter.md convention) — without this filter, every
            # comment Samantha ever posts resurfaces here as if it were new content
            # FROM Will on the next run. Found 2026-07-23 during a session-end sweep.
            # NOTE: drive_comment.py's `comment --quote` prepends `Re: "<quote>" — `
            # before the text, so the marker isn't always at index 0 — check anywhere
            # near the start, not just a strict startswith.
            content = (c.get("content") or "").strip()
            is_samanthas_own = "samantha:" in content[:220].lower()
            if c.get("createdTime", "") > since and not is_samanthas_own:
                new_comments.append((name, f.get("webViewLink"), f["id"], c))

    # Digest
    print("=" * 70)
    print(f"FROM WILL — new content since {since}")
    print("=" * 70)
    if not new_docs and not new_comments:
        print("(nothing new from Will since last pass)")
    if new_docs:
        print(f"\n### NEW / EDITED DOCUMENTS FROM WILL ({len(new_docs)})")
        for f, text in new_docs:
            print(f"\n── {f['name']}  ({f.get('webViewLink')})")
            print(f"   modified {f.get('modifiedTime')}")
            body = text.strip()
            print("   " + "\n   ".join(body[:12000].splitlines()))
            if len(body) > 12000:
                print(f"   …[doc is {len(body)} chars — read the full doc via its link if needed]")
    if new_comments:
        print(f"\n### NEW COMMENTS FROM WILL ({len(new_comments)})")
        for docname, link, fid, c in new_comments:
            q = (c.get("quotedFileContent") or {}).get("value", "")
            who = (c.get("author") or {}).get("displayName", "?")
            resolved = " [resolved]" if c.get("resolved") else ""
            print(f"\n── on \"{docname}\"{resolved}  ({link})")
            if q:
                print(f'   re section: "{q[:200]}"')
            print(f"   {who} @ {c.get('createdTime')}: {c.get('content','').strip()}")
            print(f"   ↳ REPLY in-thread: python3 scripts/samantha/drive_comment.py reply "
                  f"--file {fid} --comment {c.get('id')} --text \"Samantha: ...\"")

    print("\n" + "=" * 70)
    print("ACTION EVERY item above: do it or answer it in your report + capture durable direction to memory.")

    if not args.peek:
        cosmos_retry(lambda: _state().update_one(
            {"_id": "from_will"}, {"$set": {"pending_check": now_iso}}, upsert=True))
        print(f"(recorded pending={now_iso}; run `from_will.py --commit` AFTER you deliver to mark seen.\n"
              " until then this content re-shows next run — nothing is lost if this run crashes.)")
    else:
        print("(--peek: recorded nothing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

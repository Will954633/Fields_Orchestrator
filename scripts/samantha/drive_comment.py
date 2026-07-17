#!/usr/bin/env python3
"""
drive_comment.py — Samantha writes back on Will's Google Docs (comments + replies).

Will comments on specific sections of his docs; Samantha replies IN THAT THREAD (so her
response sits on the exact section he highlighted). She can also post a new comment,
quoting the section she's responding to. Pairs with from_will.py, which surfaces Will's
comments together with the fileId + commentId needed to reply here.

Auth: reuses the gdrive MCP OAuth creds (needs drive write scope — same as create_file).

Usage:
  # Reply to Will's comment on a specific section (BEST — lands on his highlighted text):
  drive_comment.py reply --file <fileId> --comment <commentId> --text "Agreed — I shipped X. Data: ..."

  # New comment on a doc, quoting the section it's about:
  drive_comment.py comment --file <fileId> --text "This maps to our crash-risk page." --quote "the section text"

  # List open comment threads on a doc (with ids), to decide what to reply to:
  drive_comment.py list --file <fileId>
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore")

from google.oauth2.credentials import Credentials  # noqa: E402
from google.auth.transport.requests import Request  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

OAUTH_KEYS = "/home/fields/.gdrive-oauth.keys.json"
SERVER_CREDS = "/home/fields/.gdrive-server-credentials.json"


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


def cmd_reply(a) -> int:
    svc = _drive()
    r = svc.replies().create(
        fileId=a.file, commentId=a.comment, fields="id,content,createdTime",
        body={"content": a.text},
    ).execute()
    print(f"replied on thread {a.comment}: {r.get('id')}")
    return 0


def cmd_comment(a) -> int:
    svc = _drive()
    content = a.text
    if a.quote:
        content = f'Re: "{a.quote[:180]}" — {a.text}'
    r = svc.comments().create(
        fileId=a.file, fields="id,content,createdTime", body={"content": content},
    ).execute()
    print(f"commented on {a.file}: {r.get('id')}")
    return 0


def cmd_list(a) -> int:
    svc = _drive()
    cs = svc.comments().list(
        fileId=a.file,
        fields="comments(id,content,author/displayName,createdTime,resolved,replies(author/displayName,content),quotedFileContent/value)",
    ).execute().get("comments", [])
    if not cs:
        print("(no comments on this doc)")
    for c in cs:
        q = (c.get("quotedFileContent") or {}).get("value", "")
        who = (c.get("author") or {}).get("displayName", "?")
        print(f"\n[{c['id']}] {who}{' [resolved]' if c.get('resolved') else ''}"
              f"{'  re: '+chr(34)+q[:80]+chr(34) if q else ''}")
        print(f"   {c.get('content','').strip()}")
        for rep in c.get("replies", []):
            print(f"     ↳ {(rep.get('author') or {}).get('displayName','?')}: {rep.get('content','').strip()[:120]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("reply")
    p.add_argument("--file", required=True)
    p.add_argument("--comment", required=True)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_reply)

    p = sub.add_parser("comment")
    p.add_argument("--file", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--quote", default="")
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser("list")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_list)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())

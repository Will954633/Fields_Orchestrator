#!/usr/bin/env python3
"""
task_board.py — append rows to the Samantha Task Board Google Sheet (Backlog,
Decision Log) via the Sheets API, using the same OAuth credentials running_doc.py
and drive_comment.py already use.

Note (2026-07-23): Sheets API was DISABLED in the OAuth app's GCP project
(fields-estate-ads / 6178359532) despite the token already carrying the
`spreadsheets` scope — this is why no prior session ever wrote here despite the
charter requiring it. Enabled via `gcloud services enable sheets.googleapis.com
--project=fields-estate-ads` (Will's gcloud CLI session, already authenticated).
Propagation took ~1-2 minutes after enabling.

Usage:
  python3 task_board.py backlog --priority P1 --task "..." --why "..." \
      --ladders "..." --risk "..." --needs-will "..." --status "..." --result "..."
  python3 task_board.py decision --action "..." --rationale "..." --outcome "..."
"""
from __future__ import annotations
import argparse
import json
import warnings

warnings.filterwarnings("ignore")

from google.oauth2.credentials import Credentials  # noqa: E402
from google.auth.transport.requests import Request  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

OAUTH_KEYS = "/home/fields/.gdrive-oauth.keys.json"
SERVER_CREDS = "/home/fields/.gdrive-server-credentials.json"
SHEET_ID = "1xy2w8ATjaOCAelEi0BBcKonZbE9FQXNWyAosfkot6jo"


def _creds():
    keys = json.load(open(OAUTH_KEYS))["installed"]
    tok = json.load(open(SERVER_CREDS))
    c = Credentials(
        token=tok.get("access_token"), refresh_token=tok.get("refresh_token"),
        token_uri=keys["token_uri"], client_id=keys["client_id"],
        client_secret=keys["client_secret"], scopes=(tok.get("scope") or "").split(),
    )
    if not c.valid:
        c.refresh(Request())
    return c


def _svc():
    return build("sheets", "v4", credentials=_creds(), cache_discovery=False)


def append_row(tab: str, row: list[str]):
    svc = _svc()
    svc.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range=f"{tab}!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    print(f"appended to {tab}: {row[:2]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backlog")
    b.add_argument("--priority", required=True)
    b.add_argument("--task", required=True)
    b.add_argument("--why", default="")
    b.add_argument("--ladders", default="")
    b.add_argument("--risk", default="")
    b.add_argument("--needs-will", default="")
    b.add_argument("--status", default="Open")
    b.add_argument("--result", default="")
    b.add_argument("--comment", default="")

    d = sub.add_parser("decision")
    d.add_argument("--date", default="")
    d.add_argument("--action", required=True)
    d.add_argument("--rationale", required=True)
    d.add_argument("--outcome", required=True)

    a = ap.parse_args()
    if a.cmd == "backlog":
        append_row("Backlog", [a.priority, a.task, a.why, a.ladders, a.risk,
                                a.needs_will, a.status, a.result, a.comment])
    elif a.cmd == "decision":
        import datetime
        date = a.date or datetime.datetime.now().strftime("%Y-%m-%d")
        append_row("Decision Log", [date, a.action, a.rationale, a.outcome])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Build the "Priority" tab (first tab) of the Live Leads Tracker — the calls and follow-ups
that are actually due, soonest first.

The "All Leads" tab is a ledger: everything that ever came in, newest at the top, nothing
ever removed. That answers "who have we got?" It does not answer "who do I ring today?",
which is the only question that matters at 9am. This tab is that answer and nothing else.

SOURCE OF TRUTH is system_monitor.crm_contacts.follow_up_at, set by
scripts/log_contact_touch.py when Will logs a call. One row per contact with a follow-up
due within LOOKAHEAD_DAYS (or overdue). No follow_up_at -> not on the tab. That is
deliberate: a lead earns a place here by someone deciding when to come back to it.

DONE column round-trip: the tab is rebuilt each run, so a tick would normally be wiped.
Instead the run READS column A first -- any row Will marked done has its follow_up_at
cleared in the CRM and drops off. Ticking the box is therefore a real write, not a note
to himself, and the same lead cannot resurface tomorrow.

⚠ Deliberately simple for now (Will, 2026-08-20): a flat due-date list. Priority scoring,
auto-scheduled follow-ups from behaviour, and SLA breaches are the obvious next layer and
belong in the backend, not in this renderer.

Usage:
  python3 scripts/priority_calls_to_sheet.py --dry-run
  python3 scripts/priority_calls_to_sheet.py
"""
from __future__ import annotations
import argparse
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.oauth2 import service_account          # noqa: E402
from googleapiclient.discovery import build        # noqa: E402

from shared.db import get_client                   # noqa: E402
from job_status import job_run                     # noqa: E402

SPREADSHEET_ID = "1mRjT_PmjTepF1rDajJlM553Umy47dKa4fHOclrzAKFs"
TAB = "Priority"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")
AEST = timezone(timedelta(hours=10))
LOOKAHEAD_DAYS = 14

HEADERS = ["Done", "Due", "When", "Who", "Phone", "Email", "How", "Why — what to do",
           "Last contact", "What we last sent", "Came from", "Preference"]
DONE_COL, EMAIL_COL = 0, 5
# A tick is anything a human would read as one; Sheets checkboxes serialise as "TRUE".
DONE_VALUES = {"true", "yes", "y", "done", "x", "✓", "✔"}


def get_sheets():
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


def ensure_tab_first(svc) -> int:
    """Return the Priority tab's sheetId, creating it if absent, and force it to index 0."""
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == TAB:
            sid = s["properties"]["sheetId"]
            if s["properties"].get("index") != 0:
                svc.spreadsheets().batchUpdate(
                    spreadsheetId=SPREADSHEET_ID,
                    body={"requests": [{"updateSheetProperties": {
                        "properties": {"sheetId": sid, "index": 0},
                        "fields": "index"}}]}).execute()
            return sid
    res = svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {
            "title": TAB, "index": 0,
            "gridProperties": {"rowCount": 200, "columnCount": len(HEADERS),
                               "frozenRowCount": 1}}}}]}).execute()
    return res["replies"][0]["addSheet"]["properties"]["sheetId"]


def harvest_done(svc, db) -> list[str]:
    """Clear follow_up_at for every row Will ticked Done. Returns the emails cleared."""
    try:
        rows = svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{TAB}!A2:L").execute().get("values", [])
    except Exception:
        return []
    cleared = []
    for r in rows:
        if len(r) <= EMAIL_COL:
            continue
        if str(r[DONE_COL]).strip().lower() not in DONE_VALUES:
            continue
        email = str(r[EMAIL_COL]).strip().lower()
        if not email:
            continue
        db.crm_contacts.update_one(
            {"email": email},
            {"$set": {"follow_up_at": None,
                      "follow_up_reason": "",
                      "follow_up_done_at": datetime.now(AEST).isoformat(timespec="seconds")}})
        cleared.append(email)
    return cleared


def last_sent(c: dict) -> str:
    comms = c.get("communications") or []
    if not comms:
        return "Nothing sent yet"
    out = []
    for comm in comms[-2:]:
        out.append(f"{str(comm.get('date'))[:10]} {comm.get('subject') or comm.get('type')}")
    return "; ".join(out)


def when_label(due: str, today: str) -> str:
    d = datetime.strptime(due, "%Y-%m-%d").date()
    t = datetime.strptime(today, "%Y-%m-%d").date()
    n = (d - t).days
    if n < 0:
        return f"OVERDUE by {abs(n)} day{'s' if abs(n) != 1 else ''}"
    return {0: "TODAY", 1: "Tomorrow"}.get(n, d.strftime("%a %-d %b"))


def build_rows(db, today: str) -> list[list[str]]:
    horizon = (datetime.strptime(today, "%Y-%m-%d").date()
               + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    cur = db.crm_contacts.find({"follow_up_at": {"$ne": None, "$lte": horizon}})
    rows = []
    for c in sorted(cur, key=lambda d: d.get("follow_up_at") or ""):
        due = c["follow_up_at"]
        attr = c.get("lead_attribution") or {}
        came_from = attr.get("campaign_name") or c.get("source") or ""
        rows.append([
            "", due, when_label(due, today),
            c.get("name") or "(no name)",
            # Leading apostrophe forces text: USER_ENTERED otherwise strips the "+" off
            # +61422403596 and leaves a number nobody can tap to dial.
            ("'" + c["phone"]) if c.get("phone") else "",
            c.get("email") or "",
            (c.get("follow_up_channel") or "call").upper(),
            c.get("follow_up_reason") or "",
            f"{str(c.get('last_contact_at'))[:10]} — {c.get('contact_status') or ''}"
            if c.get("last_contact_at") else "Never contacted",
            last_sent(c), came_from,
            c.get("contact_preference") or "",
        ])
    return rows


def format_tab(svc, sid: int, n_rows: int) -> None:
    reqs = [
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.13, "green": 0.22, "blue": 0.17},
                "textFormat": {"bold": True,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        {"autoResizeDimensions": {"dimensions": {
            "sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 1, "endIndex": len(HEADERS)}}},
    ]
    if n_rows:
        reqs += [
            # Done = real checkboxes, so ticking is one click and always serialises TRUE.
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": n_rows + 1,
                          "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"dataValidation": {"condition": {"type": "BOOLEAN"}}},
                "fields": "dataValidation"}},
            # Overdue and today shout; everything else stays quiet.
            {"addConditionalFormatRule": {"index": 0, "rule": {
                "ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": n_rows + 1,
                            "startColumnIndex": 2, "endColumnIndex": 3}],
                "booleanRule": {
                    "condition": {"type": "TEXT_CONTAINS",
                                  "values": [{"userEnteredValue": "OVERDUE"}]},
                    "format": {"backgroundColor": {"red": 0.96, "green": 0.80, "blue": 0.78},
                               "textFormat": {"bold": True}}}}}},
            {"addConditionalFormatRule": {"index": 0, "rule": {
                "ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": n_rows + 1,
                            "startColumnIndex": 2, "endColumnIndex": 3}],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ",
                                  "values": [{"userEnteredValue": "TODAY"}]},
                    "format": {"backgroundColor": {"red": 0.85, "green": 0.93, "blue": 0.85},
                               "textFormat": {"bold": True}}}}}},
        ]
    svc.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID,
                                   body={"requests": reqs}).execute()


def run(dry_run: bool) -> dict:
    db = get_client()["system_monitor"]
    today = datetime.now(AEST).strftime("%Y-%m-%d")

    # How many follow-ups exist AT ALL — the denominator the 7b assertion needs, so an
    # empty tab caused by a broken query is never mistaken for an empty diary.
    total_pending = db.crm_contacts.count_documents({"follow_up_at": {"$ne": None}})

    if dry_run:
        rows = build_rows(db, today)
        for r in rows:
            print(" | ".join(str(x)[:40] for x in r[1:8]))
        return {"rows": len(rows), "pending_total": total_pending, "cleared": 0}

    svc = get_sheets()
    sid = ensure_tab_first(svc)
    cleared = harvest_done(svc, db)          # honour ticks BEFORE rebuilding
    rows = build_rows(db, today)

    svc.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A1:L").execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS] + rows}).execute()
    format_tab(svc, sid, len(rows))

    return {"rows": len(rows), "pending_total": total_pending, "cleared": len(cleared)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.dry_run:
        print(run(True))
        return 0

    with job_run("priority_calls_to_sheet", cadence_hours=24,
                 title="Priority Calls tab (Live Leads Tracker)") as beat:
        res = run(False)
        beat.metrics = res
        # Rule 7b: follow-ups exist but none rendered = the query or the sheet write is
        # broken, not an empty diary. An empty diary is total_pending == 0.
        if res["pending_total"] > 0 and res["rows"] == 0:
            raise RuntimeError(
                f"{res['pending_total']} contacts have follow_up_at set but 0 rows "
                f"rendered — the Priority tab is silently empty.")
        beat.detail = (f"{res['rows']} follow-ups due (of {res['pending_total']} pending); "
                       f"{res['cleared']} marked done and cleared")
        print(beat.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

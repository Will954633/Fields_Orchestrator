#!/usr/bin/env python3
"""
mail_log_to_sheet.py — mirror system_monitor.mail_log onto the Live Leads Tracker
"Mail Log" tab, so Will can see every physical mail piece we have sent, exactly what
each address received, and its postage date, alongside the digital lead tabs.

mail_log (Mongo) is the source of truth; this tab is a full-rewrite mirror. Unlike
the All Leads / Priority tabs (insert-at-top + note harvesting), there is nothing to
harvest here — the record is authoritative in Mongo — so we simply clear and rewrite,
ordered newest batch first.

Auth mirrors the other sheet writers: floor-plan SA (the OAuth project has the Sheets
API disabled — see live_leads_tracker_sheet memory). Run standalone or from cron.
"""
from __future__ import annotations
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from google.oauth2 import service_account
from googleapiclient.discovery import build

from shared.db import get_client
from job_status import job_run

SPREADSHEET_ID = "1mRjT_PmjTepF1rDajJlM553Umy47dKa4fHOclrzAKFs"
TAB = "Mail Log"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")

HEADERS = ["Order", "Batch date", "Suburb", "Address", "Slug", "Flow", "A/B arm",
           "What we sent", "Envelope", "Posted date", "Lead source", "Drive folder"]
LAST_COL = chr(ord("A") + len(HEADERS) - 1)


def get_sheets():
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


def ensure_tab(svc) -> int:
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == TAB:
            return s["properties"]["sheetId"]
    res = svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {
            "title": TAB,
            "gridProperties": {"rowCount": 400, "columnCount": len(HEADERS),
                               "frozenRowCount": 1}}}}]}).execute()
    return res["replies"][0]["addSheet"]["properties"]["sheetId"]


def build_rows(db):
    docs = list(db["mail_log"].find({}))
    # newest batch first, then order, then address
    docs.sort(key=lambda d: (d.get("batch_date") or "", d.get("order_number") or "",
                             d.get("slug") or ""), reverse=True)
    rows = []
    for d in docs:
        rows.append([
            d.get("order_number", ""), d.get("batch_date", ""), d.get("suburb", ""),
            d.get("address", ""), d.get("slug", ""), d.get("flow_code", ""),
            d.get("ab_arm") or "", d.get("contents_str", ""), d.get("envelope", ""),
            d.get("posted_date") or "", d.get("lead_source") or "",
            d.get("drive_folder", ""),
        ])
    return rows


def main():
    with job_run("mail_log_to_sheet", cadence_hours=24,
                 title="Mail Log → Live Leads Tracker") as beat:
        db = get_client()["system_monitor"]
        svc = get_sheets()
        ensure_tab(svc)
        rows = build_rows(db)
        # clear then write (headers + all rows)
        svc.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A1:{LAST_COL}").execute()
        svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=f"{TAB}!A1",
            valueInputOption="RAW",
            body={"values": [HEADERS] + rows}).execute()
        beat.detail = f"{len(rows)} mail pieces mirrored"
        beat.metrics = {"pieces": len(rows)}
        if not rows:
            raise RuntimeError("mail_log is empty — nothing mirrored (upstream broken?)")
        print(f"wrote {len(rows)} rows to '{TAB}' tab")


if __name__ == "__main__":
    main()

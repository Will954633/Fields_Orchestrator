#!/usr/bin/env python3
"""
sheet_common.py — shared contract for the "Marketing Phone Calls" Google Sheet.

THE ONE RULE THIS FILE EXISTS TO ENFORCE
----------------------------------------
The caller types into this sheet. Their outcomes, comments and call-back dates are
the most valuable thing the whole system produces, and they exist NOWHERE else until
read_call_outcomes.py copies them out. So:

    * The sheet is NEVER rebuilt and NEVER cleared.
    * New day-blocks are INSERTED at the top (insertDimension), pushing every
      existing row — and its notes, comments and colours — down intact.
    * Columns K/L/M are HUMAN-OWNED. Nothing in this codebase may write them.
      There is a guard (assert_machine_range) that raises if a caller tries.
    * Machine columns are addressed by the hidden Call ID in column P, never by
      row position, because rows move every single day.

Layout (day-blocks newest-first, each preceded by a separator row):

      row 1  | header (frozen)
      row 2  | ── Fri 15 Aug 2026 · 25 calls ──          <- today's separator
      row 3+ |    today's calls
             | ── Thu 14 Aug 2026 · 25 calls ──          <- yesterday, pushed down
             |    yesterday's calls (with the caller's notes still on them)

See 00_SCOPING.md §8 for the full architecture and the legal contract.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Brisbane")

# The "Marketing Phone Calls" sheet Will shared. Owned by Will; the service
# account below has edit access (verified 2026-08-15).
CALL_SPREADSHEET_ID = "1txehsp26ZkF3t7wDEbewNJ35UWpyk3d286uc8oUQMP8"
TAB = "Call List"

# Service account. NOT the gdrive OAuth creds: that app is in Testing mode so its
# refresh token dies every ~7 days, which would silently break the nightly run.
# A service account never expires. It cannot CREATE a spreadsheet (no Drive quota)
# — Will owns the file and shares it in. Same pattern as live_leads_to_sheet.py.
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")

# ---------------------------------------------------------------------------
# Column contract. Index is 0-based; letter is what a human sees.
# ---------------------------------------------------------------------------
HEADERS = [
    "Call Date",        # A  0  machine, write-once
    "#",                # B  1  machine, write-once (priority within the day)
    "Name",             # C  2  machine, write-once
    "Phone",            # D  3  machine, write-once
    "Address",          # E  4  machine, write-once
    "Suburb",           # F  5  machine, write-once
    "Why now",          # G  6  machine, write-once (the hook)
    "Track",            # H  7  machine, write-once
    "Occupant?",        # I  8  machine, write-once — occupancy_evidence verdict
    "DNC washed",       # J  9  machine, write-once
    "Property",         # K 10  machine, write-once
    "☎ OUTCOME",        # L 11  HUMAN
    "☎ COMMENTS",       # M 12  HUMAN
    "☎ CALL BACK",      # N 13  HUMAN
    "Recording",        # O 14  machine, refreshed in place
    "Transcript",       # P 15  machine, refreshed in place
    "Call ID",          # Q 16  machine, hidden — the stable key
]

COL = {h: i for i, h in enumerate(HEADERS)}
OUTCOME_COL = COL["☎ OUTCOME"]        # 10
COMMENTS_COL = COL["☎ COMMENTS"]      # 11
CALLBACK_COL = COL["☎ CALL BACK"]     # 12
RECORDING_COL = COL["Recording"]      # 13
TRANSCRIPT_COL = COL["Transcript"]    # 14
CALL_ID_COL = COL["Call ID"]          # 15

# The three columns the caller owns. Writing these from code destroys their work.
HUMAN_COLS = frozenset({OUTCOME_COL, COMMENTS_COL, CALLBACK_COL})

# Machine columns refreshed in place after the row is created (one cell at a time,
# located via the hidden Call ID — never by row position).
REFRESHABLE_COLS = frozenset({RECORDING_COL, TRANSCRIPT_COL})


def col_letter(idx: int) -> str:
    """0-based column index -> A1 letter. Handles beyond Z for safety."""
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def assert_machine_range(a1_range: str) -> None:
    """Raise if an A1 range would touch a human-owned column.

    This is a real guard, not a comment. Every values().update in this package
    goes through it. A refactor that widens a write range gets an exception
    instead of silently erasing a week of the caller's notes.
    """
    m = re.search(r"!\$?([A-Z]+)\$?\d*(?::\$?([A-Z]+)\$?\d*)?$", a1_range.upper())
    if not m:
        raise ValueError(f"assert_machine_range: cannot parse range {a1_range!r}")

    def to_idx(letter: str) -> int:
        n = 0
        for ch in letter:
            n = n * 26 + (ord(ch) - 64)
        return n - 1

    start = to_idx(m.group(1))
    end = to_idx(m.group(2)) if m.group(2) else start
    touched = set(range(start, end + 1)) & HUMAN_COLS
    if touched:
        names = ", ".join(f"{col_letter(c)} ({HEADERS[c]})" for c in sorted(touched))
        raise RuntimeError(
            f"REFUSED: range {a1_range} would write human-owned column(s) {names}. "
            "The caller's outcomes/comments live only in the sheet until "
            "read_call_outcomes.py copies them out. Never write these."
        )


# ---------------------------------------------------------------------------
# Outcome dropdown. Kept short — a long list gets ignored under time pressure.
# "Do not contact again" is deliberately its own value: ACL s75(2) means no
# contact for 30 days after a request to stop, and we must be able to honour it
# mechanically rather than trusting a free-text comment to be re-read.
# ---------------------------------------------------------------------------
OUTCOMES = [
    "Connected — wants the analysis",
    "Connected — interested, call back",
    "Connected — not interested",
    "Connected — DO NOT CONTACT AGAIN",
    "Connected — already has an agent",
    "Connected — refused recording",
    "Wrong number / not the owner",
    "No answer",
    "Voicemail (no message left)",
    "Engaged / busy",
    "Skipped — out of hours",
]

# Outcomes that must suppress the number from every future list.
SUPPRESSING_OUTCOMES = frozenset({
    "Connected — DO NOT CONTACT AGAIN",
    "Connected — not interested",
    "Connected — refused recording",
})

TRACK_LABELS = {
    "A_warm": "Warm (gave us their number)",
    "B_intent": "Intent (gave us their address)",
    "C_openmarket": "Open market",
}


def get_sheets():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def set_env_from_file():
    """Load our own env — CLAUDE.md Rule 7 step 3. A cron line missing `set -a`
    exports nothing, and shared.db would still connect via config/settings.yaml,
    so the job would look healthy while every credential-dependent call failed."""
    from dotenv import load_dotenv
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(root, ".env"), override=False)


def tab_id(svc, ssid: str, title: str):
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None


def ensure_tab(svc, ssid: str) -> int:
    """Create the tab with header, freeze, widths and the outcome dropdown.
    Idempotent — safe to call every run. Never clears anything."""
    sid = tab_id(svc, ssid, TAB)
    if sid is None:
        resp = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
            "addSheet": {"properties": {
                "title": TAB,
                "gridProperties": {"rowCount": 5000, "columnCount": len(HEADERS),
                                   "frozenRowCount": 1},
            }}
        }]}).execute()
        sid = resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    # Widen the grid if HEADERS has grown since the tab was created. Without this,
    # adding a column makes every write to the new last column fail with "exceeds
    # grid limits" — and the tab is only ever created once, so the creation-time
    # columnCount goes stale the first time the schema changes.
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    for s in meta["sheets"]:
        p = s["properties"]
        if p["title"] == TAB and p["gridProperties"].get("columnCount", 0) < len(HEADERS):
            svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
                "updateSheetProperties": {
                    "properties": {"sheetId": sid,
                                   "gridProperties": {"columnCount": len(HEADERS)}},
                    "fields": "gridProperties.columnCount"}
            }]}).execute()

    # Header: write only if row 1 is empty, so a human-renamed header survives.
    rng = f"'{TAB}'!A1:{col_letter(len(HEADERS) - 1)}1"
    cur = svc.spreadsheets().values().get(spreadsheetId=ssid, range=rng).execute()
    if not cur.get("values"):
        svc.spreadsheets().values().update(
            spreadsheetId=ssid, range=rng, valueInputOption="RAW",
            body={"values": [HEADERS]}).execute()

    reqs = [
        # Bold + freeze the header.
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        # Hide the Call ID column — it is a key, not information for the caller.
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": CALL_ID_COL, "endIndex": CALL_ID_COL + 1},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        # Wrap the two long text columns so the caller can read the hook and
        # write a proper comment without the row becoming unreadable.
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1,
                      "startColumnIndex": COL["Why now"], "endColumnIndex": COL["Why now"] + 1},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                           "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1,
                      "startColumnIndex": COMMENTS_COL, "endColumnIndex": COMMENTS_COL + 1},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                           "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
    ]
    for idx, px in ((COL["Why now"], 380), (COMMENTS_COL, 420), (COL["Address"], 240),
                    (OUTCOME_COL, 230)):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": idx, "endIndex": idx + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})

    # Outcome dropdown, re-applied on every run over an OPEN-ENDED range (no
    # endRowIndex). No script in this repo has used dataValidation before, and it
    # is NOT verified that validation survives insertDimension with
    # inheritFromBefore:false — re-applying every run makes that question moot
    # instead of relying on an untested assumption. See 00_SCOPING.md §8.
    reqs.append({"setDataValidation": {
        "range": {"sheetId": sid, "startRowIndex": 1,
                  "startColumnIndex": OUTCOME_COL, "endColumnIndex": OUTCOME_COL + 1},
        "rule": {
            "condition": {"type": "ONE_OF_LIST",
                          "values": [{"userEnteredValue": o} for o in OUTCOMES]},
            "showCustomUi": True,
            # strict=False: never reject what the caller typed. A rejected keystroke
            # mid-call loses the note entirely; a non-standard value we can clean up
            # later. Losing the caller's words is the worse failure.
            "strict": False,
        }}})

    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()
    return sid


def read_grid(svc, ssid: str):
    """Return (rows, first_data_row_number). rows are raw lists, index 0 == sheet row 2."""
    rng = f"'{TAB}'!A2:{col_letter(len(HEADERS) - 1)}5000"
    vals = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=rng).execute().get("values", [])
    return vals, 2


def cell(row: list, idx: int) -> str:
    return row[idx].strip() if idx < len(row) else ""


def is_separator(row: list) -> bool:
    """Day-separator rows carry no Call ID. That is how we tell them apart."""
    return not cell(row, CALL_ID_COL)


def index_by_call_id(rows: list, first_row: int = 2) -> dict:
    """call_id -> sheet row number. The ONLY safe way to locate a row: every
    insert at the top moves every existing row down, so positions are never stable."""
    out = {}
    for i, r in enumerate(rows):
        cid = cell(r, CALL_ID_COL)
        if cid:
            out[cid] = first_row + i
    return out


def day_separator_row(day: datetime, n: int) -> list:
    label = f"──  {day.strftime('%a %-d %b %Y')}  ·  {n} call{'s' if n != 1 else ''}  ──"
    return [label] + [""] * (len(HEADERS) - 1)

#!/usr/bin/env python3
"""
call_list_to_sheet.py — push the next day's call list to the top of the
"Marketing Phone Calls" sheet, without ever disturbing what the caller has typed.

    python3 call_list_to_sheet.py --dry-run
    python3 call_list_to_sheet.py --limit 25
    python3 call_list_to_sheet.py --refresh-only     # just update Recording/Transcript

HOW THE NO-CLOBBER GUARANTEE WORKS
----------------------------------
1. We never clear, never rebuild, never write a full row range.
2. New rows arrive via `insertDimension` at startIndex=1 — i.e. directly under the
   frozen header. Google shifts every existing row down and carries its values,
   notes, comments and formatting with it. Yesterday's list, with the caller's
   comments on it, is still there — one block lower.
3. `inheritFromBefore: False` makes the new rows inherit format from the row BELOW
   (a data row), not from the bold header. Getting this backwards makes every new
   row bold.
4. Columns L/M/N are never in any write range. `assert_machine_range()` raises if a
   future edit widens a range over them.
5. Recording/Transcript are refreshed one cell at a time, located by the hidden
   Call ID in column Q — never by row number, because row numbers change daily.

Rule 7b: a run that had dialable candidates but wrote zero rows RAISES.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))

from sheet_common import (  # noqa: E402
    AEST, CALL_SPREADSHEET_ID, TAB, HEADERS, COL, CALL_ID_COL,
    RECORDING_COL, TRANSCRIPT_COL, TRACK_LABELS,
    assert_machine_range, col_letter, get_sheets, set_env_from_file,
    ensure_tab, read_grid, index_by_call_id, day_separator_row, cell,
)

LEDGER_DB, LEDGER_COLL = "system_monitor", "call_list_sheet_ledger"
QUEUE_COLL = "call_queue"
ACTIVITY_COLL = "call_activity"


def _db():
    from shared.db import get_client
    return get_client()["system_monitor"]


def mask_phone(p: str) -> str:
    d = "".join(ch for ch in (p or "") if ch.isdigit())
    return f"{d[:4]} xxx {d[-3:]}" if len(d) >= 7 else "xxxx"


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------
def pick_candidates(db, limit: int, track: str | None, now: datetime,
                    preview: bool = False):
    """Dialable == queued, DNC-clean, wash not expired, not suppressed.

    The DNC test is deliberately positive ("status == clean AND expires_at in the
    future"), never a negative ("not blocked"). An unwashed number and a number
    whose 30-day safe harbour has lapsed both fail it. DNCR Act 2006 s11(3) gives
    us the defence only for 30 days after OUR OWN submission, and s11(6) puts the
    evidential burden on us — so the default must be "not dialable".
    """
    q = {"status": "queued"}
    if not preview:
        # PREVIEW MODE SKIPS THIS AND ONLY THIS. Preview rows are written with a
        # "⛔ NOT WASHED — DO NOT DIAL" marker in the DNC column and a preview
        # banner on the day separator, are never marked `listed`, and never enter
        # the ledger — so they remain available to a real run after the wash.
        q["dnc.status"] = "clean"
        q["dnc.expires_at"] = {"$gt": now}
    if track:
        q["track"] = track
    cur = db[QUEUE_COLL].find(q).sort("score", -1)

    ledger = {d["_id"] for d in db[LEDGER_COLL].find({}, {"_id": 1})}
    out, seen_phone = [], set()
    for d in cur:
        if d["_id"] in ledger:
            continue
        # One call per phone per list, even if a number appears at two addresses.
        ph = d.get("phone", "")
        if ph in seen_phone:
            continue
        seen_phone.add(ph)
        out.append(d)
        if len(out) >= limit:
            break
    return out


def build_row(d: dict, day: datetime, rank: int) -> list:
    p = d.get("property") or {}
    hook = (d.get("hook") or {}).get("line", "")
    bits = []
    if p.get("beds"):
        bits.append(f"{p['beds']}bd")
    if p.get("baths"):
        bits.append(f"{p['baths']}ba")
    if p.get("land_sqm"):
        bits.append(f"{p['land_sqm']}m²")
    if p.get("last_sale_date"):
        held = f" ({p['years_held']}y held)" if p.get("years_held") else ""
        bits.append(f"last sold {p['last_sale_date']}{held}")

    washed = d.get("dnc", {}).get("washed_at")
    if isinstance(washed, datetime):
        washed_s = washed.astimezone(AEST).strftime("%-d %b")
    else:
        # Unwashed rows only reach the sheet via --preview. Say so loudly in the
        # cell itself, not just in a banner the caller may have scrolled past.
        washed_s = "⛔ NOT WASHED — DO NOT DIAL"

    row = [""] * len(HEADERS)
    row[COL["Call Date"]] = day.strftime("%Y-%m-%d")
    row[COL["#"]] = str(rank)
    row[COL["Name"]] = d.get("first_name") or d.get("person_name") or ""
    row[COL["Phone"]] = d.get("phone", "")
    row[COL["Address"]] = d.get("address", "")
    row[COL["Suburb"]] = (d.get("suburb") or "").title()
    # The time-sensitive intent reason leads, because it is the thing that decays:
    # "valued their own home 2 days ago" is why we are calling TODAY, whereas the
    # property hook is true any week. Both are shown — the hook is what the caller
    # actually opens with, the note is why this row is near the top.
    note = (d.get("intent_note") or "").strip()
    row[COL["Why now"]] = f"⚡ {note}\n{hook}" if note else hook
    row[COL["Track"]] = TRACK_LABELS.get(d.get("track", ""), d.get("track", ""))

    # Occupancy verdict (occupancy_evidence.py). The caller needs to know whether
    # they may be about to ask a stranger about a house they sold years ago — and
    # "current" is the WEAK direction of that inference, so the label says "likely",
    # never "confirmed". Confidence is shown so a 0.5 doesn't read like a 0.85.
    occ = d.get("occupancy") or {}
    verdict, conf = occ.get("verdict"), occ.get("confidence")
    row[COL["Occupant?"]] = {
        "current_likely": f"likely current ({conf})" if conf else "likely current",
        "prior_occupant": f"⚠ PRIOR OCCUPANT ({conf})" if conf else "⚠ PRIOR OCCUPANT",
        "unknown": f"unconfirmed ({conf})" if conf else "unconfirmed",
    }.get(verdict, "not assessed")

    row[COL["DNC washed"]] = washed_s
    row[COL["Property"]] = " · ".join(bits)
    # L, M, N deliberately left empty — the caller owns them (HUMAN_COLS).
    row[CALL_ID_COL] = d["_id"]
    return row


# ---------------------------------------------------------------------------
# The insert
# ---------------------------------------------------------------------------
def insert_day_block(svc, ssid, sheet_id, rows: list, day: datetime,
                     preview: bool = False):
    n = len(rows)
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
        "insertDimension": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": 1, "endIndex": 1 + n + 1},  # +1 for separator
            # Inherit format from the row BELOW, not the bold header.
            "inheritFromBefore": False,
        }
    }]}).execute()

    sep = day_separator_row(day, n)
    if preview:
        sep[0] = (f"⛔  PREVIEW — {n} candidate{'s' if n != 1 else ''} for review only. "
                  f"NOT DNC-WASHED. DO NOT DIAL ANY ROW IN THIS BLOCK.  ⛔")
    values = [sep] + rows
    last = col_letter(len(HEADERS) - 1)
    rng = f"'{TAB}'!A2:{last}{2 + n}"
    # Hard guard: this range spans L/M/N, so we must NOT send those cells.
    # We write column-group by column-group instead, skipping the human block.
    left_rng = f"'{TAB}'!A2:{col_letter(COL['Property'])}{2 + n}"
    right_rng = f"'{TAB}'!{col_letter(RECORDING_COL)}2:{last}{2 + n}"
    assert_machine_range(left_rng)
    assert_machine_range(right_rng)

    left = [v[:COL["Property"] + 1] for v in values]
    right = [v[RECORDING_COL:] for v in values]

    svc.spreadsheets().values().batchUpdate(spreadsheetId=ssid, body={
        # RAW, not USER_ENTERED: USER_ENTERED reinterprets unit addresses like
        # "1/35 Thornleigh Crescent" as dates, and mangles phone numbers with a
        # leading zero into integers.
        "valueInputOption": "RAW",
        "data": [{"range": left_rng, "values": left},
                 {"range": right_rng, "values": right}],
    }).execute()

    # Style the separator so the day boundary is obvious at a glance.
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2},
            "cell": {"userEnteredFormat": {
                "backgroundColor": ({"red": 0.65, "green": 0.11, "blue": 0.11} if preview
                                    else {"red": 0.20, "green": 0.24, "blue": 0.29}),
                "textFormat": {"bold": True, "foregroundColor":
                               {"red": 1, "green": 1, "blue": 1}}}},
            "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat"}},
        {"mergeCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
            "mergeType": "MERGE_ALL"}},
    ]}).execute()
    return rng


# ---------------------------------------------------------------------------
# In-place refresh of the two machine columns that change after the call
# ---------------------------------------------------------------------------
def refresh_call_artifacts(svc, ssid, db) -> int:
    """Fill Recording + Transcript for rows whose call has since happened.

    One cell per request, addressed via the hidden Call ID. Skips cells that are
    already correct so we don't burn quota rewriting identical values.
    """
    rows, first = read_grid(svc, ssid)
    by_id = index_by_call_id(rows, first)
    if not by_id:
        return 0

    acts = {a.get("call_queue_id"): a
            for a in db[ACTIVITY_COLL].find({"call_queue_id": {"$in": list(by_id)}})}
    if not acts:
        return 0

    data = []
    for cid, rownum in by_id.items():
        a = acts.get(cid)
        if not a:
            continue
        cur = rows[rownum - first]
        rec = a.get("recording_url") or ""
        rec_cell = f'=HYPERLINK("{rec}","▶ recording")' if rec else ""
        tr = a.get("transcript_summary") or (
            "transcript pending" if a.get("call_sid") else "")
        for colidx, newval in ((RECORDING_COL, rec_cell), (TRANSCRIPT_COL, tr)):
            if not newval or cell(cur, colidx) == newval:
                continue
            rng = f"'{TAB}'!{col_letter(colidx)}{rownum}"
            assert_machine_range(rng)
            data.append({"range": rng, "values": [[newval]]})

    if not data:
        return 0
    # USER_ENTERED confined to these two columns only, so =HYPERLINK parses.
    svc.spreadsheets().values().batchUpdate(spreadsheetId=ssid, body={
        "valueInputOption": "USER_ENTERED", "data": data}).execute()
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=CALL_SPREADSHEET_ID)
    ap.add_argument("--limit", type=int, default=25, help="calls in the day's block")
    ap.add_argument("--track", choices=["A_warm", "B_intent", "C_openmarket"])
    ap.add_argument("--for-date", help="YYYY-MM-DD (default: next calling day)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh-only", action="store_true",
                    help="only update Recording/Transcript, insert nothing")
    ap.add_argument("--preview", action="store_true",
                    help="show UNWASHED candidates for review. Rows are marked "
                         "DO NOT DIAL, are not marked listed, and do not enter the "
                         "ledger — so a real run can still list them after the wash.")
    args = ap.parse_args()

    set_env_from_file()
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from job_status import job_run  # noqa: E402

    with job_run("call_list_to_sheet", cadence_hours=24,
                 title="Direct-call daily list → sheet") as beat:
        db = _db()
        svc = get_sheets()
        now = datetime.now(AEST)

        if args.refresh_only:
            ensure_tab(svc, args.spreadsheet_id)
            n = refresh_call_artifacts(svc, args.spreadsheet_id, db)
            beat.detail = f"refreshed {n} cells"
            beat.metrics = {"cells_refreshed": n}
            print(f"refreshed {n} cells")
            return

        day = (datetime.strptime(args.for_date, "%Y-%m-%d").replace(tzinfo=AEST)
               if args.for_date else now + timedelta(days=1))
        # Never build a list for a Sunday — Telemarketing Standard s8(1)(e)
        # prohibits calling entirely, so a Sunday list is a list nobody may work.
        while day.weekday() == 6:
            day += timedelta(days=1)

        cands = pick_candidates(db, args.limit, args.track, now, preview=args.preview)
        queued_total = db[QUEUE_COLL].count_documents({"status": "queued"})

        if not cands and args.preview:
            print("no queued candidates at all — run build_call_list.py --build first")
            beat.detail = "preview: queue empty"
            return

        if not cands:
            # Rule 7b: distinguish "nothing to do" from "we could not do it".
            if queued_total:
                blocked = db[QUEUE_COLL].count_documents(
                    {"status": "queued", "dnc.status": {"$ne": "clean"}})
                raise RuntimeError(
                    f"{queued_total} candidates are queued but ZERO are dialable "
                    f"({blocked} have no current DNC wash). The list is not empty — "
                    "the wash pipeline is the blockage. Run dnc_wash.py --status.")
            print("queue is empty — nothing to list (this is success, not failure)")
            beat.detail = "queue empty"
            beat.metrics = {"rows_added": 0, "queued_total": 0}
            return

        rows = [build_row(d, day, i + 1) for i, d in enumerate(cands)]

        if args.dry_run:
            print(f"DRY RUN — would insert {len(rows)} calls for "
                  f"{day.strftime('%a %-d %b %Y')}:")
            for r in rows:
                print(f"  {r[COL['#']]:>3}. {r[COL['Name']]:<14} "
                      f"{mask_phone(r[COL['Phone']]):<14} {r[COL['Address']][:38]:<38} "
                      f"| {r[COL['Why now']][:60]}")
            beat.detail = f"dry-run {len(rows)}"
            return

        sheet_id = ensure_tab(svc, args.spreadsheet_id)
        insert_day_block(svc, args.spreadsheet_id, sheet_id, rows, day,
                         preview=args.preview)

        if args.preview:
            # Deliberately NO ledger write and NO status change. A preview must not
            # consume the candidates — after the wash lands, the real run must still
            # be able to list these same people.
            print(f"PREVIEW: wrote {len(rows)} candidates for review. "
                  f"NOT dialable, NOT ledgered, still 'queued'.\n"
                  f"  Nothing may be dialled until dnc_wash.py round-trips "
                  f"(DNCR Act 2006 s11(3)).")
            beat.detail = f"preview {len(rows)}"
            beat.metrics = {"preview_rows": len(rows), "queued_total": queued_total}
            return

        # Ledger + queue state AFTER the successful write, so a failed write is
        # simply retried next run rather than silently dropping the candidates.
        ts = now.isoformat()
        for d in cands:
            db[LEDGER_COLL].update_one(
                {"_id": d["_id"]},
                {"$setOnInsert": {"first_added": ts,
                                  "listed_for": day.strftime("%Y-%m-%d")}},
                upsert=True)
            db[QUEUE_COLL].update_one(
                {"_id": d["_id"]},
                {"$set": {"status": "listed",
                          "listed_on": day.strftime("%Y-%m-%d"),
                          "updated_at": now}})

        refreshed = refresh_call_artifacts(svc, args.spreadsheet_id, db)
        print(f"inserted {len(rows)} calls at top for {day.strftime('%a %-d %b %Y')}; "
              f"refreshed {refreshed} artifact cells")
        beat.detail = f"{len(rows)} calls listed for {day.strftime('%Y-%m-%d')}"
        beat.metrics = {"rows_added": len(rows), "queued_total": queued_total,
                        "cells_refreshed": refreshed}


if __name__ == "__main__":
    main()

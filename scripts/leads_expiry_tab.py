#!/usr/bin/env python3
"""Split "Listing Nearing Expiry" leads out of 'All Leads' into their own tabs.

Two destination tabs, and the split between them is LEGAL, not cosmetic:

  'Listing Nearing Expiry'  — still on the market with another agent, approaching
                              the ~90-day Form 6 decision point. NOT approachable:
                              the competitor's appointment is in force.

  'Off Market — Follow Up'  — no longer listed (withdrawn, or term expired).
                              Followable, but see the compliance column.

⚖ WHY THE TWO ARE NOT INTERCHANGEABLE (Property Occupations Regulation 2014 (Qld) s 21(3)):
it is an offence to SOLICIT an appointment while another agent's appointment is in force,
and the prohibited act is the APPROACH, not the signing. A WITHDRAWAL DOES NOT END THE
APPOINTMENT — a Form 6 ends only on expiry or written notice, and may roll on as an open
listing (POA s 108(3)). So "it came off the market" is NOT evidence that we may call.

  withdrawn  -> appointment MAY STILL BE IN FORCE  -> s 21(3) risk
  expired    -> term lapsed                        -> approachable

We detect withdrawal (the listing vanishing from Domain). We CANNOT observe any property's
Form 6 term — we hold it nowhere — so every row lands as `withdrawn` and NOTHING is marked
`expired` on evidence we do not have. The Compliance column carries the s 21(4) cure: the
written double-commission warning must appear in the FIRST outbound piece. QCAT exposure is
$34,540 individual / $172,700 corporation plus permanent disqualification.

⚠ The withdrawn flag is contaminated with real sales — 4 of 68 (5.9%) were confirmed sold
while flagged withdrawn, several with a sold_date EARLIER than their withdrawn_date. Re-check
sold status at the moment of contact, not when the row was written.

HIGHLIGHT PRESERVATION: Will hand-colours rows. The `values.append` + `deleteDimension` move
used by leads_came_to_market.py carries VALUES ONLY — a moved row arrives blank-white and the
manual highlight is destroyed silently. This script reads each source row's background colour
alongside its values and re-applies it at the row's new position, so a colour survives the
move. Rows that stay in 'All Leads' are never touched at all.

Usage:
    python3 scripts/leads_expiry_tab.py --dry-run
    python3 scripts/leads_expiry_tab.py
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from live_leads_to_sheet import (  # noqa: E402
    LIVE_SPREADSHEET_ID, TAB as LEADS_TAB, HEADERS as LEAD_HEADERS,
    get_sheets, tab_id,
)

EXPIRY_SOURCE = "Listing Nearing Expiry"
EXPIRY_TAB = "Listing Nearing Expiry"
OFFMARKET_TAB = "Off Market — Follow Up"
CAME_TO_MARKET_TAB = "Came to Market"   # existing tab; sold rows land here as history

# Extra columns on the destination tabs. LEAD_HEADERS is reused verbatim so the
# first 15 columns line up with 'All Leads' and a row can be moved between tabs
# without re-mapping fields.
EXPIRY_HEADERS = LEAD_HEADERS + ["Market Status", "Compliance"]

# The only value we can justify writing. "expired" requires a Form 6 term we do not hold.
STATUS_WITHDRAWN = "Withdrawn (not confirmed expired)"
COMPLIANCE_WITHDRAWN = (
    "s21(3): another agent's appointment MAY STILL BE IN FORCE — a withdrawal does not end "
    "it. Do not solicit without the s21(4) written double-commission warning in the first "
    "outbound piece. Re-check sold status before contact."
)
STATUS_LISTED = "On market with another agent"
COMPLIANCE_LISTED = (
    "s21(3): appointment IS in force — do NOT approach. Watch for the ~90-day decision point."
)


def _cell(row, i):
    return row[i] if i < len(row) else ""


def _norm(bg):
    """Background colour as a comparable triple, or None for blank/white."""
    if not bg:
        return None
    t = tuple(round(bg.get(k) if bg.get(k) is not None else 1.0, 3)
              for k in ("red", "green", "blue"))
    return None if all(v > 0.98 for v in t) else t


def ensure_tab(svc, ssid, title, headers, dry_run=False):
    sid = tab_id(svc, ssid, title)
    if sid is not None:
        return sid
    if dry_run:
        print(f"  (would create tab {title!r})")
        return None
    res = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"addSheet": {"properties": {"title": title,
                                     "gridProperties": {"rowCount": 1000,
                                                        "columnCount": len(headers)}}}}
    ]}).execute()
    sid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    svc.spreadsheets().values().update(
        spreadsheetId=ssid, range=f"'{title}'!A1",
        valueInputOption="RAW", body={"values": [headers]}).execute()
    print(f"  created tab {title!r}")
    return sid


def read_source_rows(svc, ssid):
    """Values + first-cell background colour for every populated row of 'All Leads'."""
    grid = svc.spreadsheets().get(
        spreadsheetId=ssid, ranges=[f"'{LEADS_TAB}'!A2:O10000"], includeGridData=True,
        fields="sheets/data/rowData/values(formattedValue,userEnteredFormat/backgroundColor)"
    ).execute()
    rowdata = (grid.get("sheets") or [{}])[0].get("data", [{}])[0].get("rowData", [])
    out = []
    for i, r in enumerate(rowdata):
        vals = r.get("values") or []
        values = [v.get("formattedValue", "") or "" for v in vals]
        if not any(values):
            continue
        bg = _norm((vals[0].get("userEnteredFormat") or {}).get("backgroundColor")) if vals else None
        out.append({"row": i + 2, "values": values, "colour": bg})
    return out


def run(spreadsheet_id=LIVE_SPREADSHEET_ID, dry_run=False):
    svc = get_sheets()
    ssid = spreadsheet_id
    src_i = LEAD_HEADERS.index("Source")

    rows = read_source_rows(svc, ssid)
    movers = [r for r in rows if _cell(r["values"], src_i) == EXPIRY_SOURCE]
    stayers = [r for r in rows if _cell(r["values"], src_i) != EXPIRY_SOURCE]

    coloured_moving = [r for r in movers if r["colour"]]
    coloured_staying = [r for r in stayers if r["colour"]]

    print(f"'{LEADS_TAB}': {len(rows)} data row(s)")
    print(f"  moving to '{EXPIRY_TAB}': {len(movers)}"
          f"  (of which hand-coloured: {len(coloured_moving)})")
    print(f"  staying in '{LEADS_TAB}': {len(stayers)}"
          f"  (of which hand-coloured: {len(coloured_staying)} — untouched)")

    if not movers:
        print("Nothing to move.")
        return {"moved": 0, "coloured": 0}

    ensure_tab(svc, ssid, EXPIRY_TAB, EXPIRY_HEADERS, dry_run=dry_run)
    # Created now so the destination exists the first time a row goes off-market,
    # rather than at the worst possible moment.
    ensure_tab(svc, ssid, OFFMARKET_TAB, EXPIRY_HEADERS, dry_run=dry_run)

    payload = [r["values"] + [""] * (len(LEAD_HEADERS) - len(r["values"]))
               + [STATUS_LISTED, COMPLIANCE_LISTED] for r in movers]

    if dry_run:
        print(f"\n(dry run) would append {len(payload)} row(s) to '{EXPIRY_TAB}' "
              f"and delete them from '{LEADS_TAB}'.")
        for r in coloured_moving:
            print(f"    colour {r['colour']} preserved for: "
                  f"{_cell(r['values'], LEAD_HEADERS.index('Suburb / Address'))[:50]}")
        return {"moved": len(movers), "coloured": len(coloured_moving)}

    # 1. Append values to the destination tab.
    before = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{EXPIRY_TAB}'!A2:A10000").execute().get("values", [])
    first_new_row = len(before) + 2
    svc.spreadsheets().values().append(
        spreadsheetId=ssid, range=f"'{EXPIRY_TAB}'!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": payload}).execute()

    # 2. Re-apply hand-picked colours at their NEW positions. Without this the move
    #    silently discards them (values.append writes values only).
    dest_sid = tab_id(svc, ssid, EXPIRY_TAB)
    reqs = []
    for offset, r in enumerate(movers):
        if not r["colour"]:
            continue
        rn = first_new_row + offset
        red, green, blue = r["colour"]
        reqs.append({"repeatCell": {
            "range": {"sheetId": dest_sid, "startRowIndex": rn - 1, "endRowIndex": rn,
                      "startColumnIndex": 0, "endColumnIndex": len(EXPIRY_HEADERS)},
            "cell": {"userEnteredFormat": {"backgroundColor": {
                "red": red, "green": green, "blue": blue}}},
            "fields": "userEnteredFormat.backgroundColor",
        }})
    if reqs:
        svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()
        print(f"  re-applied {len(reqs)} hand-picked highlight(s) on '{EXPIRY_TAB}'")

    # 3. Delete the moved rows from 'All Leads', BOTTOM-UP so each delete does not
    #    shift the index of the ones still to be removed.
    leads_sid = tab_id(svc, ssid, LEADS_TAB)
    del_reqs = [{"deleteDimension": {"range": {
        "sheetId": leads_sid, "dimension": "ROWS",
        "startIndex": r["row"] - 1, "endIndex": r["row"]}}}
        for r in sorted(movers, key=lambda x: -x["row"])]
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid,
                                   body={"requests": del_reqs}).execute()
    print(f"Moved {len(movers)} row(s) to '{EXPIRY_TAB}'.")
    return {"moved": len(movers), "coloured": len(reqs)}


def _suburb_of(address: str) -> str | None:
    """'12 Wayville Place, Robina, QLD 4226' -> 'robina'. Returns None if not a core suburb."""
    for s in ("robina", "varsity_lakes", "burleigh_waters"):
        if s.replace("_", " ") in (address or "").lower():
            return s
    return None


def sweep(spreadsheet_id=LIVE_SPREADSHEET_ID, dry_run=False):
    """Move rows off 'Listing Nearing Expiry' once the listing is no longer on the market.

    A near-expiry lead only makes sense while the home IS listed. When the campaign ends
    the lead does not evaporate — it becomes MORE interesting — but it also changes legal
    category, so it moves to a tab that carries the s 21(3) warning rather than silently
    staying on a list captioned "on market with another agent".

    ⚠ Rule 7b: a row is moved ONLY on a positive read of listing_status. A property we
    cannot find in Gold_Coast is left exactly where it is — "I could not look it up" and
    "it is off the market" must never produce the same action.
    """
    from shared.db import get_gold_coast_db  # local: keeps --dry-run of run() DB-free

    svc = get_sheets()
    ssid = spreadsheet_id
    gc = get_gold_coast_db()
    addr_i = LEAD_HEADERS.index("Suburb / Address")

    grid = svc.spreadsheets().get(
        spreadsheetId=ssid, ranges=[f"'{EXPIRY_TAB}'!A2:Q10000"], includeGridData=True,
        fields="sheets/data/rowData/values(formattedValue,userEnteredFormat/backgroundColor)"
    ).execute()
    rowdata = (grid.get("sheets") or [{}])[0].get("data", [{}])[0].get("rowData", [])

    movers, unresolved = [], 0
    for i, r in enumerate(rowdata):
        vals = r.get("values") or []
        values = [v.get("formattedValue", "") or "" for v in vals]
        if not any(values):
            continue
        address = _cell(values, addr_i)
        suburb = _suburb_of(address)
        if not suburb:
            unresolved += 1
            continue
        doc = gc[suburb].find_one({"address": address}, {"listing_status": 1})
        if not doc:
            unresolved += 1        # unknown != off-market. Leave it alone.
            continue
        st = doc.get("listing_status")
        if st in ("withdrawn", "sold"):
            bg = _norm((vals[0].get("userEnteredFormat") or {}).get("backgroundColor")) if vals else None
            movers.append({"row": i + 2, "values": values, "colour": bg,
                           "address": address, "status": st})

    print(f"'{EXPIRY_TAB}': {len(movers)} row(s) no longer on the market "
          f"({unresolved} could not be resolved — left in place)")
    for m in movers:
        print(f"    {m['status']:<10} {m['address'][:52]}"
              + ("   [highlighted]" if m["colour"] else ""))
    if not movers or dry_run:
        if dry_run and movers:
            print(f"(dry run) would move {len(movers)} row(s) to '{OFFMARKET_TAB}'")
        return {"moved": 0 if dry_run else 0, "candidates": len(movers),
                "unresolved": unresolved}

    # Route by what actually happened. A SOLD home is not a follow-up lead — it
    # transacted, and parking it on a tab captioned "Follow Up" rebuilds the exact
    # defect this work exists to remove: contactable-looking rows that must not be
    # contacted. Sold goes to the existing 'Came to Market' tab as history; only
    # WITHDRAWN reaches the follow-up list.
    ensure_tab(svc, ssid, OFFMARKET_TAB, EXPIRY_HEADERS)
    reqs, moved_total = [], 0
    for dest, group in (
            (OFFMARKET_TAB, [m for m in movers if m["status"] == "withdrawn"]),
            (CAME_TO_MARKET_TAB, [m for m in movers if m["status"] == "sold"])):
        if not group:
            continue
        before = svc.spreadsheets().values().get(
            spreadsheetId=ssid, range=f"'{dest}'!A2:A10000").execute().get("values", [])
        first_new_row = len(before) + 2
        payload = []
        for m in group:
            v = (m["values"] + [""] * len(EXPIRY_HEADERS))[:len(LEAD_HEADERS)]
            if dest == OFFMARKET_TAB:
                payload.append(v + [STATUS_WITHDRAWN, COMPLIANCE_WITHDRAWN])
            else:
                payload.append(v + ["Sold", "Sold to another buyer — NOT a lead."])
        svc.spreadsheets().values().append(
            spreadsheetId=ssid, range=f"'{dest}'!A1",
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": payload}).execute()
        moved_total += len(group)

        dest_sid = tab_id(svc, ssid, dest)
        ncols = len(EXPIRY_HEADERS) if dest == OFFMARKET_TAB else len(LEAD_HEADERS) + 2
        for offset, m in enumerate(group):
            if not m["colour"]:
                continue
            rn = first_new_row + offset
            red, green, blue = m["colour"]
            reqs.append({"repeatCell": {
                "range": {"sheetId": dest_sid, "startRowIndex": rn - 1, "endRowIndex": rn,
                          "startColumnIndex": 0, "endColumnIndex": ncols},
                "cell": {"userEnteredFormat": {"backgroundColor": {
                    "red": red, "green": green, "blue": blue}}},
                "fields": "userEnteredFormat.backgroundColor"}})
        print(f"  -> {len(group)} row(s) to '{dest}'")
    if reqs:
        svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": reqs}).execute()

    exp_sid = tab_id(svc, ssid, EXPIRY_TAB)
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [
        {"deleteDimension": {"range": {"sheetId": exp_sid, "dimension": "ROWS",
                                       "startIndex": m["row"] - 1, "endIndex": m["row"]}}}
        for m in sorted(movers, key=lambda x: -x["row"])]}).execute()
    print(f"Moved {len(movers)} row(s) to '{OFFMARKET_TAB}' "
          f"({len(reqs)} highlight(s) carried).")
    return {"moved": len(movers), "candidates": len(movers), "unresolved": unresolved}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sweep", action="store_true",
                    help="move no-longer-listed rows to the off-market follow-up tab")
    a = ap.parse_args()
    if a.sweep:
        sweep(spreadsheet_id=a.spreadsheet_id, dry_run=a.dry_run)
    else:
        run(spreadsheet_id=a.spreadsheet_id, dry_run=a.dry_run)


if __name__ == "__main__":
    main()

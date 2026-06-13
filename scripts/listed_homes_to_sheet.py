#!/usr/bin/env python3
"""
Append newly-LISTED homes to the "Market Tracking" Google Sheet — one "*_Listed" tab
per suburb (Robina_Listed, Varsity Lakes_Listed, Burleigh Waters_Listed).

This is the mirror of scripts/sold_homes_to_sheet.py for the for-sale side. It reuses
that script's proven helpers (auth, address dedupe, attribute extraction, hyperlinking)
and only changes four things:
  * source filter  -> listing_status == "for_sale"   (not "sold")
  * date anchor    -> first_listed_timestamp          (not sold_date), default 30d window
  * price column   -> the raw asking "price" string   (e.g. "Auction", "Offers Over $X")
  * tabs + ledger  -> "*_Listed" tabs, listed_sheet_ledger collection

Behaviour matches the sold job: new homes are inserted at the TOP (row 2, under the
header) so existing rows, notes, comments and formatting shift DOWN — the sheet is never
rebuilt. Each home is added at most once, ever (dedupe = sheet addresses ∪ ledger), so a
row deleted by hand is not resurrected. The Listed tab is a growing LOG of homes as they
come to market — a row stays put even after the home later sells.

Columns auto-filled (A–G); editorial columns (H–K) left blank for manual entry:
  A Address          <- address (hyperlinked to its Domain page)
  B Listed Date      <- first_listed_timestamp, formatted DD/MM
  C Asking Price     <- raw `price` string verbatim ("Contact Agent" if genuinely empty)
  D Bed/Bath         <- bedrooms/bathrooms
  E Floor Area       <- floor_plan_analysis.internal_floor_area (internal, excl garage)
  F Lot Size         <- floor_plan_analysis.total_land_area / valuation land_size_sqm
  G Number of levels <- property_valuation_data...number_of_stories

Usage:
  python3 scripts/listed_homes_to_sheet.py --dry-run          # show what would be added
  python3 scripts/listed_homes_to_sheet.py                    # add to the live sheet
  python3 scripts/listed_homes_to_sheet.py --days 30          # lookback window (default 30)
  python3 scripts/listed_homes_to_sheet.py --spreadsheet-id X # target a test copy
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # scripts/

# Reuse the battle-tested helpers from the sold job (importing it runs no code — it is
# guarded by `if __name__ == "__main__"`). We only redefine what genuinely differs.
import sold_homes_to_sheet as sold
from sold_homes_to_sheet import (
    get_sheets, norm_addr, fmt_date, parse_sold_date,
    floor_area, lot_size, levels, is_house, is_unit_address, bed_bath,
    hyperlink, tab_id, existing_addresses, set_env_from_file,
)

from shared.db import get_client

# ---- config -------------------------------------------------------------------
LIVE_SPREADSHEET_ID = "1tVBi4KNFTSUHw8kK272H9kEZZmGF4IIp2WhfwfqY9iI"
DB_NAME = "Gold_Coast"

# collection in Gold_Coast  ->  tab title in the sheet
SUBURB_TABS = {
    "robina":          "Robina_Listed",
    "varsity_lakes":   "Varsity Lakes_Listed",
    "burleigh_waters": "Burleigh Waters_Listed",
}

HEADERS = ["Address", "Listed Date", "Asking Price", "Bed/Bath", "Floor Area",
           "Lot Size", "Number of levels", "Special features", "Last Sale Year",
           "Last sale price", "Notes"]
AEST = timezone(timedelta(hours=10))

# Independent ledger so listed/sold dedupe never collide (keyed by tab|norm_addr anyway).
LEDGER_DB = "system_monitor"
LEDGER_COLL = "listed_sheet_ledger"


# ---- listed-specific helpers --------------------------------------------------
def asking_price(doc) -> str:
    """The advertised asking price, verbatim — Domain serves this as free text
    ("Auction", "Offers Over $1,649,000", "Price Guide - $1.3M - $1.4M", "$2,950,000").
    We never reformat or invent a figure; the only fallback, for the rare genuinely
    empty value, is "Contact Agent" — exactly what Domain itself shows in that case."""
    p = (doc.get("price") or "").strip()
    return p or "Contact Agent"


def build_row(doc):
    """The 7 auto-filled cells (A–G)."""
    return [
        doc.get("address", ""),
        fmt_date(doc.get("first_listed_timestamp")),
        asking_price(doc),
        bed_bath(doc),
        floor_area(doc) or "",
        lot_size(doc) or "",
        levels(doc) or "",
    ]


def ensure_header(svc, ssid, title):
    """Write the Listed header row if the tab is empty (freshly-created tabs are)."""
    row1 = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{title}'!A1:K1").execute().get("values", [])
    if not row1 or not any(c.strip() for c in (row1[0] if row1 else [])):
        svc.spreadsheets().values().update(
            spreadsheetId=ssid, range=f"'{title}'!A1",
            valueInputOption="RAW", body={"values": [HEADERS]}).execute()
        return True
    return False


def load_ledger(client, tab):
    return {d["norm_addr"] for d in
            client[LEDGER_DB][LEDGER_COLL].find({"tab": tab}, {"norm_addr": 1})}


def record_ledger(client, tab, address, ts):
    na = norm_addr(address)
    client[LEDGER_DB][LEDGER_COLL].update_one(
        {"_id": f"{tab}|{na}"},
        {"$set": {"tab": tab, "norm_addr": na, "address": address},
         "$setOnInsert": {"first_added": ts}},
        upsert=True)


# ---- main ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--days", type=int, default=30, help="lookback window for first_listed")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all-types", action="store_true", help="include units/townhouses")
    ap.add_argument("--no-alert", action="store_true", help="suppress the Telegram summary")
    args = ap.parse_args()

    set_env_from_file()
    svc = get_sheets()
    client = get_client()
    db = client[DB_NAME]
    cutoff = datetime.now(AEST).replace(tzinfo=None) - timedelta(days=args.days)

    total_added = 0
    per_tab = {}
    for coll, tab in SUBURB_TABS.items():
        sheet_id = tab_id(svc, args.spreadsheet_id, tab)
        if sheet_id is None:
            print(f"[{tab}] tab not found — skipping")
            continue
        if not args.dry_run:
            if ensure_header(svc, args.spreadsheet_id, tab):
                print(f"[{tab}] wrote header row (tab was empty)")

        seen = existing_addresses(svc, args.spreadsheet_id, tab) | load_ledger(client, tab)
        candidates = []
        skipped_unit = 0
        for doc in db[coll].find({"listing_status": "for_sale"}):
            addr = doc.get("address", "")
            ld = parse_sold_date(doc.get("first_listed_timestamp"))
            if ld is None or ld < cutoff:
                continue
            if norm_addr(addr) in seen:
                continue
            if not args.all_types and (is_unit_address(addr) or not is_house(doc)):
                skipped_unit += 1
                continue
            candidates.append((ld, doc))

        # newest first -> ends up at the very top after insert
        candidates.sort(key=lambda x: x[0], reverse=True)
        rows, links, used = [], [], set()
        for ld, doc in candidates:
            na = norm_addr(doc.get("address", ""))
            if na in used:
                continue
            rows.append(build_row(doc))
            links.append(doc.get("listing_url") or doc.get("url") or "")
            used.add(na)

        skip_note = f"  (skipped: {skipped_unit} unit/townhouse)" if skipped_unit else ""
        if not rows:
            print(f"[{tab}] nothing new{skip_note}")
            continue

        print(f"[{tab}] {len(rows)} new listing(s){skip_note}:")
        for r in rows:
            print(f"    {r[1]}  {r[0]}  {r[2]}  {r[3]}  {r[4]}m²  lot {r[5]}  {r[6]}lvl")

        if args.dry_run:
            continue

        # insert blank rows under the header
        n = len(rows)
        svc.spreadsheets().batchUpdate(spreadsheetId=args.spreadsheet_id, body={"requests": [{
            "insertDimension": {
                "range": {"sheetId": sheet_id, "dimension": "ROWS",
                          "startIndex": 1, "endIndex": 1 + n},
                "inheritFromBefore": False,
            }
        }]}).execute()
        # column A: address hyperlinked (USER_ENTERED so the formula parses);
        # columns B–G plain text (RAW so "08/06" / asking strings aren't coerced)
        col_a = [[hyperlink(links[i], rows[i][0])] for i in range(n)]
        svc.spreadsheets().values().update(
            spreadsheetId=args.spreadsheet_id, range=f"'{tab}'!A2",
            valueInputOption="USER_ENTERED", body={"values": col_a}).execute()
        svc.spreadsheets().values().update(
            spreadsheetId=args.spreadsheet_id, range=f"'{tab}'!B2",
            valueInputOption="RAW", body={"values": [r[1:] for r in rows]}).execute()
        ts = datetime.now(AEST).isoformat()
        for r in rows:
            record_ledger(client, tab, r[0], ts)
        total_added += n
        per_tab[tab] = n

    client.close()
    print(f"\nDone. {total_added} row(s) added{' (dry run — nothing written)' if args.dry_run else ''}.")

    if total_added and not args.dry_run and not args.no_alert:
        notify(per_tab, total_added, args.spreadsheet_id)


def notify(per_tab, total_added, ssid):
    """Best-effort Telegram summary — never let a notification failure break the run."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from telegram_notify import send_message
        url = f"https://docs.google.com/spreadsheets/d/{ssid}/edit"
        breakdown = ", ".join(f"{t} {n}" for t, n in per_tab.items() if n)
        send_message(f"🆕 Market Tracking: {total_added} new listing(s) added "
                     f"({breakdown}).\n{url}", parse_mode="")
    except Exception as e:
        print(f"(telegram summary skipped: {e})")


if __name__ == "__main__":
    main()

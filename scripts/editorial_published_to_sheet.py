#!/usr/bin/env python3
"""
Append newly-PUBLISHED property editorial to the "Market Tracking" Google Sheet —
one combined "Editorial_Published" tab (all target suburbs), so Will has one place
to see every property page whose editorial has gone live (and therefore is now
eligible for Google indexing — see the editorial indexing gate, fix-history
2026-07-24 [SEO-EDITORIAL-GATE]).

Sibling of scripts/listed_homes_to_sheet.py / sold_homes_to_sheet.py; reuses their
proven helpers (auth, address dedupe, hyperlinking, tab lookup, insert-at-top).
Differences:
  * source filter -> listing_status == "for_sale" AND ai_analysis.status == "published"
  * date anchor   -> ai_analysis.published_at (ISO-8601 'Z'), default 30d window
  * link target   -> the FIELDS property page, /property/<url_slug> (not Domain)
  * tab + ledger  -> single "Editorial_Published" tab, editorial_sheet_ledger collection

Behaviour matches the sold/listed jobs: new rows are inserted at the TOP (row 2, under
the header) so existing rows/notes/formatting shift DOWN — the sheet is never rebuilt.
Each address is added at most once, ever (dedupe = sheet addresses ∪ ledger), so a row
deleted by hand is not resurrected. The tab is a growing LOG of published editorial.

Columns (auto-filled A–E):
  A Address       <- address, hyperlinked to https://fieldsestate.com.au/property/<slug>
  B Suburb        <- suburb
  C Published     <- ai_analysis.published_at, formatted DD/MM
  D Editorial Hook<- ai_analysis.meta_title (the SERP/social headline)
  E Page URL      <- plain https://fieldsestate.com.au/property/<slug> (easy copy/paste)

Usage:
  python3 scripts/editorial_published_to_sheet.py --dry-run     # show what would be added
  python3 scripts/editorial_published_to_sheet.py               # add to the live sheet
  python3 scripts/editorial_published_to_sheet.py --days 3650   # full backfill of all published
  python3 scripts/editorial_published_to_sheet.py --spreadsheet-id X  # target a test copy
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # scripts/

# Reuse the battle-tested helpers from the sold job (importing runs no code — it is
# guarded by `if __name__ == "__main__"`). We only redefine what genuinely differs.
from sold_homes_to_sheet import (
    get_sheets, norm_addr, hyperlink, tab_id, existing_addresses, set_env_from_file,
)

from shared.db import get_client

# ---- config -------------------------------------------------------------------
LIVE_SPREADSHEET_ID = "1tVBi4KNFTSUHw8kK272H9kEZZmGF4IIp2WhfwfqY9iI"
DB_NAME = "Gold_Coast"
SITE = "https://fieldsestate.com.au"
TAB = "Editorial_Published"

# collections in Gold_Coast to scan  ->  suburb label shown in column B
SUBURBS = {
    "robina":          "Robina",
    "varsity_lakes":   "Varsity Lakes",
    "burleigh_waters": "Burleigh Waters",
}

HEADERS = ["Address", "Suburb", "Published", "Editorial Hook", "Page URL"]
AEST = timezone(timedelta(hours=10))

LEDGER_DB = "system_monitor"
LEDGER_COLL = "editorial_sheet_ledger"


# ---- helpers ------------------------------------------------------------------
def parse_pub(ts):
    """ai_analysis.published_at -> naive datetime (AEST-agnostic; used only for the
    lookback comparison, which is done against a naive cutoff). Accepts ISO-8601 with
    a trailing 'Z' or an offset, or a datetime. Returns None if unparseable."""
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def fmt_pub(ts) -> str:
    d = parse_pub(ts)
    return f"{d.day:02d}/{d.month:02d}" if d else ""


def page_url(doc) -> str:
    slug = doc.get("url_slug") or str(doc.get("_id"))
    return f"{SITE}/property/{slug}"


def ensure_tab(svc, ssid, title):
    """Return the sheetId for `title`, creating the tab if it doesn't exist yet."""
    sid = tab_id(svc, ssid, title)
    if sid is not None:
        return sid
    resp = svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
        "addSheet": {"properties": {"title": title}}
    }]}).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def ensure_header(svc, ssid, title):
    row1 = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{title}'!A1:E1").execute().get("values", [])
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
    ap.add_argument("--days", type=int, default=30,
                    help="lookback window on published_at (default 30; use a big number to backfill)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-alert", action="store_true", help="suppress the Telegram summary")
    args = ap.parse_args()

    set_env_from_file()
    svc = get_sheets()
    client = get_client()
    db = client[DB_NAME]
    cutoff = datetime.now(AEST).replace(tzinfo=None) - timedelta(days=args.days)

    if not args.dry_run:
        ensure_tab(svc, args.spreadsheet_id, TAB)
        if ensure_header(svc, args.spreadsheet_id, TAB):
            print(f"[{TAB}] wrote header row (tab was empty/new)")
        seen = existing_addresses(svc, args.spreadsheet_id, TAB) | load_ledger(client, TAB)
    else:
        seen = load_ledger(client, TAB)

    candidates = []
    for coll, suburb_label in SUBURBS.items():
        for doc in db[coll].find(
                {"listing_status": "for_sale", "ai_analysis.status": "published"}):
            addr = doc.get("address", "")
            if not addr:
                continue
            pub = parse_pub((doc.get("ai_analysis") or {}).get("published_at"))
            if pub is None or pub < cutoff:
                continue
            if norm_addr(addr) in seen:
                continue
            candidates.append((pub, suburb_label, doc))

    # newest first -> ends up at the very top after insert
    candidates.sort(key=lambda x: x[0], reverse=True)
    rows, links, used = [], [], set()
    for pub, suburb_label, doc in candidates:
        na = norm_addr(doc.get("address", ""))
        if na in used:
            continue
        ai = doc.get("ai_analysis") or {}
        url = page_url(doc)
        rows.append([doc.get("address", ""), suburb_label,
                     fmt_pub(ai.get("published_at")), ai.get("meta_title", ""), url])
        links.append(url)
        used.add(na)

    if not rows:
        print(f"[{TAB}] nothing new (window {args.days}d).")
        client.close()
        return

    print(f"[{TAB}] {len(rows)} newly-published editorial page(s):")
    for r in rows:
        print(f"    {r[2]}  {r[0]}  [{r[1]}]  {r[3]}")

    if args.dry_run:
        client.close()
        print("\n(dry run — nothing written)")
        return

    sheet_id = tab_id(svc, args.spreadsheet_id, TAB)
    n = len(rows)
    # insert blank rows under the header
    svc.spreadsheets().batchUpdate(spreadsheetId=args.spreadsheet_id, body={"requests": [{
        "insertDimension": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": 1, "endIndex": 1 + n},
            "inheritFromBefore": False,
        }
    }]}).execute()
    # column A: address hyperlinked to the Fields page (USER_ENTERED so the formula parses)
    col_a = [[hyperlink(links[i], rows[i][0])] for i in range(n)]
    svc.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!A2",
        valueInputOption="USER_ENTERED", body={"values": col_a}).execute()
    # columns B–E plain text (RAW so DD/MM and hook strings aren't coerced)
    svc.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!B2",
        valueInputOption="RAW", body={"values": [r[1:] for r in rows]}).execute()

    ts = datetime.now(AEST).isoformat()
    for r in rows:
        record_ledger(client, TAB, r[0], ts)
    client.close()
    print(f"\nDone. {n} row(s) added to '{TAB}'.")

    if not args.no_alert:
        notify(n, args.spreadsheet_id)


def notify(n, ssid):
    """Best-effort Telegram summary — never let a notification failure break the run."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from telegram_notify import send_message
        url = f"https://docs.google.com/spreadsheets/d/{ssid}/edit"
        send_message(f"📝 {n} newly-published editorial page(s) added to the "
                     f"Editorial_Published tab.\n{url}", parse_mode="")
    except Exception as e:
        print(f"(telegram summary skipped: {e})")


if __name__ == "__main__":
    main()

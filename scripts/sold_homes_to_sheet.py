#!/usr/bin/env python3
"""
Append newly-sold homes to the "Market Tracking" Google Sheet — one tab per suburb.

New sold homes are inserted as rows at the TOP of each suburb tab (row 2, directly
under the header) via the Sheets API: insertDimension + values.update. Existing rows,
cell notes, comments, formatting and any blank separator rows simply shift DOWN — the
sheet is preserved over time, never rebuilt. Dedupes by normalised address so a home is
never added twice (run it as often as you like; it only adds what's genuinely new).

Columns auto-filled (A–G). The editorial columns (Special features, Last Sale Year,
Last sale price, Notes) are left blank for manual entry and never touched.

  A Address          <- address
  B Sale Date        <- sold_date, formatted DD/MM
  C Sale Price       <- sale_price (e.g. "1,350,000")
  D Bed/Bath         <- bedrooms/bathrooms (e.g. "3/2")
  E Floor Area       <- floor_plan_analysis.internal_floor_area  (internal, excl garage)
  F Lot Size         <- floor_plan_analysis.total_land_area / valuation land_size_sqm
  G Number of levels <- property_valuation_data...number_of_stories

Usage:
  python3 scripts/sold_homes_to_sheet.py --dry-run          # show what would be added
  python3 scripts/sold_homes_to_sheet.py                    # add to the live sheet
  python3 scripts/sold_homes_to_sheet.py --days 30          # wider lookback window
  python3 scripts/sold_homes_to_sheet.py --spreadsheet-id X # target a test copy
"""
from __future__ import annotations
import argparse
import os
import re
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2 import service_account
from googleapiclient.discovery import build

from shared.db import get_client

# ---- config -------------------------------------------------------------------
LIVE_SPREADSHEET_ID = "1tVBi4KNFTSUHw8kK272H9kEZZmGF4IIp2WhfwfqY9iI"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")
DB_NAME = "Gold_Coast"

# collection in Gold_Coast  ->  tab title in the sheet
# Tabs renamed 2026-06-14 ("Robina" -> "Robina_Sold") for symmetry with the new
# "*_Listed" tabs populated by listed_homes_to_sheet.py. The sold_sheet_ledger tab
# keys were migrated to match in the same change.
SUBURB_TABS = {
    "robina":          "Robina_Sold",
    "varsity_lakes":   "Varsity Lakes_Sold",
    "burleigh_waters": "Burleigh Waters_Sold",
}

HEADERS = ["Address", "Sale Date", "Sale Price", "Bed/Bath", "Floor Area",
           "Lot Size", "Number of levels", "Special features", "Last Sale Year",
           "Last sale price", "Notes"]
AEST = timezone(timedelta(hours=10))

_ABBR = {
    "st": "street", "str": "street", "rd": "road", "dr": "drive", "drv": "drive",
    "ave": "avenue", "av": "avenue", "ct": "court", "crt": "court", "cres": "crescent",
    "cr": "crescent", "cres.": "crescent", "blvd": "boulevard", "bvd": "boulevard",
    "pl": "place", "pde": "parade", "ln": "lane", "cl": "close", "tce": "terrace",
    "hwy": "highway", "wy": "way", "qld": "", "queensland": "",
}


# ---- auth ---------------------------------------------------------------------
def get_sheets():
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


# ---- address / value helpers --------------------------------------------------
def norm_addr(a: str) -> str:
    """Normalise an address for dedupe: lowercase, expand street-type abbreviations,
    drop punctuation / state / postcode. '9 Rosebud St, Robina' == '9 Rosebud Street,
    Robina, QLD 4226'."""
    if not a:
        return ""
    a = a.lower().replace("/", " ")
    a = re.sub(r"[^a-z0-9 ]", " ", a)
    toks = [t for t in a.split() if not re.fullmatch(r"\d{4}", t)]
    toks = [_ABBR.get(t, t) for t in toks]
    return " ".join(t for t in toks if t).strip()


def fmt_date(sold_date) -> str:
    """sold_date (str 'YYYY-MM-DD' or datetime) -> 'DD/MM'."""
    if isinstance(sold_date, datetime):
        return f"{sold_date.day:02d}/{sold_date.month:02d}"
    s = str(sold_date)[:10]
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return f"{d.day:02d}/{d.month:02d}"
    except ValueError:
        return s


def parse_sold_date(sold_date):
    if isinstance(sold_date, datetime):
        return sold_date.replace(tzinfo=None)
    try:
        return datetime.strptime(str(sold_date)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def price_str(doc) -> str:
    """The CONFIRMED realised sale price ONLY — a clean number like '1,350,000', taken
    strictly from `sale_price`/`sold_price`. We never fall back to `price`: that field is
    the last *advertised/asking* price, so when the sale price is withheld it would put an
    asking figure in the Sale Price column. If there is no confirmed sale price, return ''
    and the home is skipped (a withheld sale is not invented)."""
    for key in ("sale_price", "sold_price"):
        v = doc.get(key)
        if not v:
            continue
        s = str(v).strip().lstrip("$").replace(" ", "")
        if re.fullmatch(r"\d[\d,]*", s):
            return s
    return ""


def is_unit_address(addr: str) -> bool:
    """Unit/townhouse if the street-number segment (before the first comma) has a '/'."""
    head = (addr or "").split(",")[0]
    return "/" in head


def _num(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def floor_area(doc):
    """Internal floor area read from the floor plan (excludes garage)."""
    fpa = doc.get("floor_plan_analysis") or {}
    node = fpa.get("internal_floor_area") or {}
    return _num(node.get("value"))


def lot_size(doc):
    fpa = doc.get("floor_plan_analysis") or {}
    node = fpa.get("total_land_area") or {}
    n = _num(node.get("value"))
    if n:
        return n
    # fallback: valuation subject features
    feats = (((doc.get("valuation_data") or {}).get("subject_property") or {})
             .get("features") or {}).get("basic") or {}
    return _num(feats.get("land_size_sqm"))


def levels(doc):
    pov = (doc.get("property_valuation_data") or {}).get("property_overview") or {}
    n = _num(pov.get("number_of_stories"))
    if n:
        return n
    feats = (((doc.get("valuation_data") or {}).get("subject_property") or {})
             .get("features") or {}).get("basic") or {}
    return _num(feats.get("number_of_stories"))


def is_house(doc) -> bool:
    pt = (doc.get("property_type") or doc.get("classified_property_type") or "").lower()
    return "house" in pt


def bed_bath(doc) -> str:
    b, ba = doc.get("bedrooms"), doc.get("bathrooms")
    if b is None and ba is None:
        return ""
    return f"{b if b is not None else ''}/{ba if ba is not None else ''}"


WITHHELD = "Withheld"


def build_row(doc):
    """The 7 auto-filled cells (A–G). When Domain withholds the sale price, the Sale
    Price cell is 'Withheld' (never an asking price) and the home is still listed so the
    sale can be tracked and the price filled in by hand later."""
    return [
        doc.get("address", ""),
        fmt_date(doc.get("sold_date")),
        price_str(doc) or WITHHELD,
        bed_bath(doc),
        floor_area(doc) or "",
        lot_size(doc) or "",
        levels(doc) or "",
    ]


def hyperlink(url: str, label: str) -> str:
    """A1-cell value that links the address text to its Domain page. Falls back to plain
    text when there's no URL. Read back via the API it still returns the address label,
    so address dedupe keeps working."""
    lab = (label or "").replace('"', '""')
    return f'=HYPERLINK("{url}","{lab}")' if url else (label or "")


# ---- sheet ops ----------------------------------------------------------------
def tab_id(svc, ssid, title):
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None


def ensure_header(svc, ssid, title):
    """Write the header row if the tab is empty (e.g. a fresh Burleigh Waters tab)."""
    row1 = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{title}'!A1:K1").execute().get("values", [])
    if not row1 or not any(c.strip() for c in (row1[0] if row1 else [])):
        svc.spreadsheets().values().update(
            spreadsheetId=ssid, range=f"'{title}'!A1",
            valueInputOption="RAW", body={"values": [HEADERS]}).execute()
        return True
    return False


def existing_addresses(svc, ssid, title):
    vals = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{title}'!A2:A1000").execute().get("values", [])
    return {norm_addr(r[0]) for r in vals if r and r[0].strip()}


# A home is added to a tab at most ONCE, ever — tracked in this ledger so that a row the
# user deletes by hand is NOT resurrected on the next run. Dedupe = sheet ∪ ledger.
LEDGER_DB = "system_monitor"
LEDGER_COLL = "sold_sheet_ledger"


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
def set_env_from_file():
    """Load COSMOS_CONNECTION_STRING etc. from .env so the script runs standalone
    (e.g. under cron) without needing the env pre-sourced."""
    if os.environ.get("COSMOS_CONNECTION_STRING"):
        return
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--days", type=int, default=7, help="lookback window for sold_date")
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
        for doc in db[coll].find({"listing_status": "sold"}):
            addr = doc.get("address", "")
            sd = parse_sold_date(doc.get("sold_date"))
            if sd is None or sd < cutoff:
                continue
            if norm_addr(addr) in seen:
                continue
            if not args.all_types and (is_unit_address(addr) or not is_house(doc)):
                skipped_unit += 1
                continue
            candidates.append((sd, doc))

        # newest first -> ends up at the very top after insert
        candidates.sort(key=lambda x: x[0], reverse=True)
        rows, links, used = [], [], set()
        withheld = 0
        for sd, doc in candidates:
            na = norm_addr(doc.get("address", ""))
            if na in used:
                continue
            row = build_row(doc)
            if row[2] == "Withheld":
                withheld += 1
            rows.append(row)
            links.append(doc.get("listing_url") or "")
            used.add(na)

        extra = []
        if withheld:
            extra.append(f"{withheld} price withheld")
        if skipped_unit:
            extra.append(f"{skipped_unit} unit/townhouse skipped")
        skip_note = f"  ({', '.join(extra)})" if extra else ""

        if not rows:
            print(f"[{tab}] nothing new{skip_note}")
            continue

        print(f"[{tab}] {len(rows)} new sold home(s){skip_note}:")
        for r in rows:
            print(f"    {r[1]}  {r[0]}  ${r[2]}  {r[3]}  {r[4]}m²  lot {r[5]}  {r[6]}lvl")

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
        # column A: address hyperlinked to its Domain page (USER_ENTERED so the
        # formula is parsed); columns B–G: plain text (RAW so "08/06" / "1,350,000"
        # are not coerced into dates/numbers)
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
        send_message(f"🏠 Market Tracking: {total_added} new sold home(s) added "
                     f"({breakdown}).\n{url}", parse_mode="")
    except Exception as e:
        print(f"(telegram summary skipped: {e})")


if __name__ == "__main__":
    main()

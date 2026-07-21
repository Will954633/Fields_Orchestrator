#!/usr/bin/env python3
"""
Add newly-captured leads to the "Live Leads Tracker" Google Sheet (single "All Leads" tab).

Three sources, unified into one row schema:
  - Facebook Lead Ads   (system_monitor.fb_leads, excl. is_test)
  - Analyse Your Home   (system_monitor.property_reports; AYH captures no contact info
                         by design -- see memory ayh_conversions_no_contact -- so name/
                         email/phone are blank but the address + engagement signals are
                         real, e.g. visit_count, PostHog attribution channel)
  - Off-Market Report   (system_monitor.offmarket_orders, the $15 unlock -- requires
                         consent + a real payment, so contact info there IS reliable)

Internal/test noise is excluded: is_test docs, will@fieldsestate.com.au / test@tester.com.au
contacts, is_internal-flagged AYH visits, and known diagnostic-test slugs.

New leads are inserted as rows at the TOP (row 2, under the header) via insertDimension +
values.update -- exactly the pattern used by sold_homes_to_sheet.py -- so existing rows,
any manual notes/status edits, and formatting all shift down intact; the sheet is never
rebuilt. Dedupe = sheet-independent ledger (system_monitor.live_leads_sheet_ledger) keyed
by a stable per-source lead id, so a row Will deletes by hand is never resurrected.

Usage:
  python3 scripts/live_leads_to_sheet.py --dry-run
  python3 scripts/live_leads_to_sheet.py
  python3 scripts/live_leads_to_sheet.py --spreadsheet-id X   # target a test copy
"""
from __future__ import annotations
import argparse
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.oauth2 import service_account
from googleapiclient.discovery import build

from shared.db import get_client

# ---- config ---------------------------------------------------------------
LIVE_SPREADSHEET_ID = "1mRjT_PmjTepF1rDajJlM553Umy47dKa4fHOclrzAKFs"
TAB = "All Leads"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")

TEST_EMAILS = {"will@fieldsestate.com.au", "test@tester.com.au"}
TEST_SLUGS = {"7-huntingdale-crescent-robina", "5-fulham-place-robina"}

HEADERS = ["Date", "Source", "Name", "Email", "Phone", "Suburb / Address",
           "Details", "Campaign / Channel", "Status"]
AEST = timezone(timedelta(hours=10))

LEDGER_DB = "system_monitor"
LEDGER_COLL = "live_leads_sheet_ledger"


# ---- auth -------------------------------------------------------------------
def get_sheets():
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


# ---- ledger ------------------------------------------------------------------
def load_ledger(client):
    return {d["_id"] for d in client[LEDGER_DB][LEDGER_COLL].find({}, {"_id": 1})}


def record_ledger(client, lead_id, ts):
    client[LEDGER_DB][LEDGER_COLL].update_one(
        {"_id": lead_id}, {"$setOnInsert": {"first_added": ts}}, upsert=True)


# ---- per-source row builders --------------------------------------------------
def fb_lead_rows(db):
    for d in db.fb_leads.find({}):
        if d.get("is_test"):
            continue
        fields = d.get("fields", {})
        email = (fields.get("email") or "").lower()
        if email in TEST_EMAILS:
            continue
        details_parts = []
        for k in ("bedrooms", "bathrooms", "timeframe", "owns_gc_home",
                  "selling_timeframe", "property_address"):
            if fields.get(k):
                details_parts.append(f"{k}={fields[k]}")
        campaign = d.get("campaign_name", "")
        if d.get("ad_name"):
            campaign += f" / {d['ad_name']}"
        yield {
            "lead_id": f"fb_leads:{d['_id']}",
            "date": (d.get("created_time") or "")[:10],
            "source": "Facebook Lead Ad",
            "name": fields.get("full_name", ""),
            "email": fields.get("email", ""),
            "phone": fields.get("phone_number", ""),
            "suburb_address": fields.get("area") or fields.get("suburb")
                or fields.get("property_address", ""),
            "details": "; ".join(details_parts),
            "campaign": campaign,
            "status": d.get("contact_status", "new"),
        }


def ayh_rows(db):
    for d in db.property_reports.find({}):
        owner = d.get("owner") or {}
        if owner.get("is_internal"):
            continue
        if (owner.get("email") or "").lower() in TEST_EMAILS:
            continue
        if d.get("source") in ("diagnostic_test", "fb_lead_ayh", "offmarket_report"):
            continue
        if d.get("slug") in TEST_SLUGS:
            continue
        visit_count = owner.get("visit_count", 0) or 0
        if visit_count < 1:
            continue
        attribution = owner.get("attribution") or {}
        channel = attribution.get("channel_type", "")
        ft = attribution.get("first_touch") or {}
        details_parts = [f"visits={visit_count}"]
        if channel:
            details_parts.append(f"channel={channel}")
        if ft.get("landing_page"):
            details_parts.append(f"landing={ft['landing_page']}")
        if ft.get("utm_campaign"):
            details_parts.append(f"utm_campaign={ft['utm_campaign']}")
        address = d.get("address") or d.get("suburb")
        if not address and d.get("slug"):
            address = d["slug"].replace("-", " ").title()
        status = d.get("state", "")
        if not status and d.get("valuation_finalised_at"):
            status = "recommendation signed off"
            rec = d.get("recommendation") or {}
            if rec.get("listing_price"):
                details_parts.append(f"listing_price=${rec['listing_price']:,}")
        created = d.get("created_at")
        yield {
            "lead_id": f"property_reports:{d['_id']}",
            "date": created.strftime("%Y-%m-%d") if created else "",
            "source": "Analyse Your Home",
            "name": "",
            "email": owner.get("email") or "",
            "phone": owner.get("phone") or "",
            "suburb_address": address or "",
            "details": "; ".join(details_parts),
            "campaign": ft.get("utm_campaign", "") or ft.get("referrer", "") or "",
            "status": status,
        }


def offmarket_rows(db):
    for d in db.offmarket_orders.find({}):
        buyer = d.get("buyer") or {}
        if (buyer.get("email") or "").lower() in TEST_EMAILS:
            continue
        if not d.get("consent"):
            continue
        details_parts = [
            f"amount=${(d.get('amount') or 0) / 100:.2f}",
            f"confidence={d.get('confidence', '')}",
            f"payment_status={d.get('payment_status', '')}",
            f"refund_status={d.get('refund_status', '')}",
            f"owner_match={d.get('owner_match')}",
        ]
        created = d.get("created_at")
        name = f"{buyer.get('first_name', '')} {buyer.get('last_name', '')}".strip()
        yield {
            "lead_id": f"offmarket_orders:{d['order_id']}",
            "date": created.strftime("%Y-%m-%d") if created else "",
            "source": "Off-Market Report ($15 unlock)",
            "name": name,
            "email": buyer.get("email") or "",
            "phone": buyer.get("phone") or "",
            "suburb_address": d.get("subject_address") or d.get("suburb") or "",
            "details": "; ".join(details_parts),
            "campaign": d.get("arm", ""),
            "status": d.get("status", ""),
        }


# ---- sheet ops ----------------------------------------------------------------
def tab_id(svc, ssid, title):
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None


def row_values(lead):
    return [lead["date"], lead["source"], lead["name"], lead["email"], lead["phone"],
            lead["suburb_address"], lead["details"], lead["campaign"], lead["status"]]


# ---- main -----------------------------------------------------------------
def set_env_from_file():
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
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-alert", action="store_true")
    args = ap.parse_args()

    set_env_from_file()
    svc = get_sheets()
    client = get_client()
    db = client["system_monitor"]

    sheet_id = tab_id(svc, args.spreadsheet_id, TAB)
    if sheet_id is None:
        print(f"Tab '{TAB}' not found in spreadsheet {args.spreadsheet_id}")
        sys.exit(1)

    seen = load_ledger(client)

    all_leads = list(fb_lead_rows(db)) + list(ayh_rows(db)) + list(offmarket_rows(db))
    candidates = [l for l in all_leads if l["lead_id"] not in seen]
    # newest first -> ends up at the very top after insert
    candidates.sort(key=lambda l: l["date"], reverse=True)

    if not candidates:
        print("Nothing new.")
        client.close()
        return

    print(f"{len(candidates)} new lead(s):")
    for l in candidates:
        print(f"    {l['date']}  {l['source']:<28}  {l['suburb_address']}")

    if args.dry_run:
        client.close()
        return

    n = len(candidates)
    svc.spreadsheets().batchUpdate(spreadsheetId=args.spreadsheet_id, body={"requests": [{
        "insertDimension": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": 1, "endIndex": 1 + n},
            "inheritFromBefore": False,
        }
    }]}).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!A2",
        valueInputOption="RAW", body={"values": [row_values(l) for l in candidates]}).execute()

    ts = datetime.now(AEST).isoformat()
    for l in candidates:
        record_ledger(client, l["lead_id"], ts)

    client.close()
    print(f"\nDone. {n} row(s) added.")

    if not args.no_alert:
        notify(n, candidates, args.spreadsheet_id)


def notify(n, candidates, ssid):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from telegram_notify import send_message
        url = f"https://docs.google.com/spreadsheets/d/{ssid}/edit"
        by_source = {}
        for l in candidates:
            by_source[l["source"]] = by_source.get(l["source"], 0) + 1
        breakdown = ", ".join(f"{s} {c}" for s, c in by_source.items())
        send_message(f"New lead(s): {n} added to Live Leads Tracker ({breakdown}).\n{url}",
                     parse_mode="")
    except Exception as e:
        print(f"(telegram summary skipped: {e})")


if __name__ == "__main__":
    main()

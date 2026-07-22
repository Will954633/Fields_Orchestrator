#!/usr/bin/env python3
"""
Add newly-captured leads to the "Live Leads Tracker" Google Sheet (single "All Leads" tab).

Three sources, unified into one row schema:
  - Facebook Lead Ads   (system_monitor.fb_leads, excl. is_test)
  - Analyse Your Home   (system_monitor.property_reports; AYH captures no contact info
                         by design -- see memory ayh_conversions_no_contact -- so name/
                         email/phone are blank but the address + engagement signals are
                         real, e.g. visit_count, PostHog attribution channel)
  - Off-Market Report   Two flavours, merged: (1) system_monitor.offmarket_orders, the
                         $15 unlock -- requires consent + a real payment, contact info IS
                         reliable; (2) PostHog `offmarket_report_view` -- every distinct
                         visitor who OPENED an /off-market/:slug page, whether or not they
                         paid. (1) started empty (the only order on record is Will's own
                         test) so (2) is the real signal for this channel today -- see
                         memory offmarket_paid_report ("no FB ads, organic traffic only").
                         No contact info for (2) (anonymous page view), filtered to
                         genuine AU visitors only (see City/Country below); a visitor who
                         later buys is upgraded from a "viewed" row to an "orders" row
                         (never both, keyed off posthog_distinct_id).

Internal/test noise is excluded: is_test docs, will@fieldsestate.com.au / test@tester.com.au
contacts, is_internal-flagged AYH visits, and known diagnostic-test slugs.

City/Country columns confirm genuine (Australian) traffic: AYH and off-market leads carry
a PostHog distinct_id, looked up via HogQL against $geoip_city_name/$geoip_country_name
(same mechanism as crm_sync.py's bot filtering). Facebook Lead Ads have no on-site session
so there's no per-lead geoip -- those rows are labelled as inferred from the ad account's
Australia-geo-targeted campaigns, not measured, so it's never confused with a real hit.

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.oauth2 import service_account
from googleapiclient.discovery import build

from shared.db import get_client
from crm_sync import posthog_query, INTERNAL_IDS, BOT_CITIES
from scripts.property_reports import occupancy_classifier as occ

# ---- config ---------------------------------------------------------------
LIVE_SPREADSHEET_ID = "1mRjT_PmjTepF1rDajJlM553Umy47dKa4fHOclrzAKFs"
TAB = "All Leads"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")
GC_DB = "Gold_Coast"
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

TEST_EMAILS = {"will@fieldsestate.com.au", "test@tester.com.au"}
TEST_SLUGS = {"7-huntingdale-crescent-robina", "5-fulham-place-robina"}

# Facebook Lead Ads have no on-site PostHog session, so there is no per-lead geoip.
# The ad account only runs Australia-geo-targeted campaigns (see memory ads_reference:
# HOUSING neighbourhood targeting on Robina/Varsity Lakes/Burleigh Waters) -- flagged as
# inferred, not measured, so it's never confused with a verified PostHog geoip hit.
FB_LOCATION_NOTE = "AU (inferred — geo-targeted FB campaign, no on-site session)"

HEADERS = ["Date", "Source", "Name", "Email", "Phone", "City", "Country",
           "Suburb / Address", "Details", "Campaign / Channel", "Status",
           "Selling Plan", "Lead ID"]
# Selling Plan (col L, 0-indexed 11) and Lead ID (col M, 0-indexed 12) are the
# only two auto-refreshed-in-place columns (see LIVE-LEADS-SHEET-AUTOUPDATE
# fix-history, 2026-07-21) -- everything else is written once, at first add,
# and never touched again so Will's manual edits (Status, notes, etc.) are
# never clobbered. Lead ID is hidden -- it exists purely so a later run can
# find "this exact row" again to refresh its Selling Plan cell.
SELLING_PLAN_COL = 11  # 0-indexed -> column L
LEAD_ID_COL = 12       # 0-indexed -> column M
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
            "posthog_distinct_id": None,
            "suburb_address": fields.get("area") or fields.get("suburb")
                or fields.get("property_address", ""),
            "details": "; ".join(details_parts),
            "campaign": campaign,
            "status": d.get("contact_status", "new"),
        }


def selling_plan_details(d: dict) -> str:
    """Format a property_reports doc's selling_plan.activity_log (added 2026-07-21,
    see fix-history SELLING-PLAN-CRM-LOGGING) into a single readable string for the
    sheet's Details column -- the exact question + the seller's exact answer, so
    Will has the specific data on hand for follow-up (e.g. "list-month: September;
    settlement-days: 45 days; staging: Yes - full styling"). Uses the question text
    + answerLabel already stored per-entry (no need to duplicate the question/option
    text tables that live in property-plan-submit.mjs). Last answer per question wins
    (a seller can change their mind -- the sheet should show where they landed, not
    every intermediate edit); the full history remains in Mongo if ever needed."""
    log = ((d.get("selling_plan") or {}).get("activity_log")) or []
    if not log:
        return ""
    latest_by_question = {}
    for entry in log:
        latest_by_question[entry.get("questionId")] = entry
    parts = []
    for entry in latest_by_question.values():
        label = entry.get("answerLabel")
        if isinstance(label, list):
            label = ", ".join(label)
        answer = label or entry.get("freeText") or "(free text only)"
        parts.append(f"{entry.get('question', entry.get('questionId'))} → {answer}")
    return "; ".join(parts)


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
            "posthog_distinct_id": attribution.get("posthog_distinct_id") or owner.get("posthog_distinct_id"),
            "suburb_address": address or "",
            "details": "; ".join(details_parts),
            "campaign": ft.get("utm_campaign", "") or ft.get("referrer", "") or "",
            "status": status,
            "selling_plan": selling_plan_details(d),
        }


def _slug_to_address(slug: str) -> str:
    return slug.replace("-", " ").title()


def resolve_gc_doc(gc_db, slug: str):
    """Find the Gold_Coast property doc for an off-market slug -- tries each of the
    3 core suburb collections by url_slug (same convention as backfill_offmarket_slugs.py)."""
    for suburb in CORE_SUBURBS:
        d = gc_db[suburb].find_one({"url_slug": slug})
        if d:
            return d
    return None


def years_since(date_str):
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return round((datetime.now() - d).days / 365.25, 1)
    except (ValueError, TypeError):
        return None


def occupancy_for_slug(gc_db, slug: str) -> dict:
    """Free path only (stored timeline, no Bright Data cost) -- this runs nightly over
    every off-market view, so a paid fresh pull per lead is not justified here. Returns
    the occupancy_classifier result dict, or an 'unknown'/no-data result if the address
    can't be resolved. Gold_Coast has no 'for_rent' listing_status (only for_sale/sold/
    under_contract/withdrawn) -- tenancy is only visible via the Domain Rental-listing
    events inside the timeline, which is exactly what classify_from_timeline reads."""
    gc_doc = resolve_gc_doc(gc_db, slug)
    if not gc_doc:
        return occ.classify_from_timeline([])
    events = occ.normalise_stored_timeline(gc_doc)
    result = occ.classify_from_timeline(events)
    result["currently_for_sale"] = gc_doc.get("listing_status") == "for_sale"
    return result


def occupancy_details(o: dict) -> str:
    parts = [f"occupancy={o.get('type', 'unknown')}"]
    ev = o.get("evidence") or {}
    if ev.get("last_sale_date"):
        yrs = years_since(ev["last_sale_date"])
        parts.append(f"last_sale={ev['last_sale_date']}" + (f" ({yrs}y held)" if yrs is not None else ""))
        if ev.get("last_sale_price"):
            parts.append(f"last_sale_price=${ev['last_sale_price']:,}")
    if o.get("currently_for_sale"):
        parts.append("currently_for_sale=True")
    return "; ".join(parts)


def offmarket_rows(db, gc_db):
    """Off-market leads = anyone who opened an /off-market/:slug page. Paid orders are
    the reliable-contact subset; PostHog `offmarket_report_view` covers everyone else who
    merely viewed (the channel's only real signal today -- see module docstring).

    Every address is run through occupancy_classifier (free stored-timeline path) so the
    list only contains genuine off-market OWNER properties -- not a rental someone was
    searching as a prospective tenant. A property whose latest timeline event is a Rental
    listing after its last sale (occupancy type == 'investor', i.e. currently tenanted) is
    filtered out of view-leads entirely. Purchase rows are never filtered on occupancy (a
    real payment is its own strong signal) but are enriched with the same detail."""
    purchased_by_distinct_id = {}
    for d in db.offmarket_orders.find({}):
        buyer = d.get("buyer") or {}
        if (buyer.get("email") or "").lower() in TEST_EMAILS:
            continue
        if not d.get("consent"):
            continue
        did = d.get("posthog_distinct_id")
        if did:
            purchased_by_distinct_id[did] = True
        details_parts = [
            f"amount=${(d.get('amount') or 0) / 100:.2f}",
            f"confidence={d.get('confidence', '')}",
            f"payment_status={d.get('payment_status', '')}",
            f"refund_status={d.get('refund_status', '')}",
            f"owner_match={d.get('owner_match')}",
        ]
        plan = ""
        if d.get("slug"):
            details_parts.append(occupancy_details(occupancy_for_slug(gc_db, d["slug"])))
            pr_doc = db.property_reports.find_one({"slug": d["slug"]}, {"selling_plan": 1})
            if pr_doc:
                plan = selling_plan_details(pr_doc)
        created = d.get("created_at")
        name = f"{buyer.get('first_name', '')} {buyer.get('last_name', '')}".strip()
        yield {
            "lead_id": f"offmarket_orders:{d['order_id']}",
            "date": created.strftime("%Y-%m-%d") if created else "",
            "source": "Off-Market Report",
            "name": name,
            "email": buyer.get("email") or "",
            "phone": buyer.get("phone") or "",
            "posthog_distinct_id": did,
            "suburb_address": d.get("subject_address") or d.get("suburb") or "",
            "details": "; ".join(details_parts),
            "campaign": d.get("arm", ""),
            "status": f"purchased — {d.get('status', '')}",
            "selling_plan": plan,
        }

    rows = posthog_query("""
SELECT distinct_id,
       min(timestamp) as first_seen,
       count() as views,
       groupUniqArray(properties.$pathname) as paths,
       argMax(properties.$geoip_city_name, timestamp) as city,
       argMax(properties.$geoip_country_name, timestamp) as country,
       argMax(properties.$device_type, timestamp) as device,
       argMax(properties.$browser, timestamp) as browser,
       argMax(properties.$referring_domain, timestamp) as referrer
FROM events
WHERE event = 'offmarket_report_view' AND timestamp > now() - INTERVAL 180 DAY
GROUP BY distinct_id
""")
    for did, first_seen, views, paths, city, country, device, browser, referrer in rows:
        if did in purchased_by_distinct_id:
            continue  # already emitted above as a purchase row
        if did in INTERNAL_IDS:
            continue
        if country != "Australia":
            continue
        if city and city in BOT_CITIES:
            continue
        slugs = [p.rsplit("/", 1)[-1] for p in (paths or []) if p]
        if not slugs:
            continue
        addresses = [_slug_to_address(s) for s in slugs]
        # Occupancy on the primary (first-viewed) address -- a currently-tenanted
        # property (rental listed after its last sale) means this was most likely a
        # prospective renter, not a genuine off-market/seller lead. Filter it out.
        primary_occ = occupancy_for_slug(gc_db, slugs[0])
        if primary_occ.get("type") == "investor":
            continue
        details_parts = [f"views={views}", f"device={device or ''}", f"browser={browser or ''}",
                          occupancy_details(primary_occ)]
        if len(addresses) > 1:
            details_parts.append(f"also_viewed={'; '.join(addresses[1:])}")
        yield {
            "lead_id": f"offmarket_view:{did}",
            "date": first_seen[:10] if first_seen else "",
            "source": "Off-Market Report",
            "name": "",
            "email": "",
            "phone": "",
            "posthog_distinct_id": did,
            "suburb_address": addresses[0] if addresses else "",
            "details": "; ".join(details_parts),
            "campaign": referrer or "",
            "status": "viewed — no purchase",
        }


# ---- geoip (PostHog $geoip_city_name / $geoip_country_name by distinct_id) -----
def lookup_geoip(distinct_ids: set[str]) -> dict[str, tuple[str, str]]:
    """Batch HogQL lookup of the most recent city/country PostHog recorded for each
    distinct_id. Only AYH / off-market leads carry a distinct_id (an on-site session);
    Facebook Lead Ads never do (see FB_LOCATION_NOTE)."""
    ids = [i for i in distinct_ids if i]
    if not ids:
        return {}
    id_list = ", ".join("'" + i.replace("'", "") + "'" for i in ids)
    rows = posthog_query(f"""
SELECT distinct_id,
       argMax(properties.$geoip_city_name, timestamp) as city,
       argMax(properties.$geoip_country_name, timestamp) as country
FROM events
WHERE distinct_id IN ({id_list})
GROUP BY distinct_id
""")
    return {r[0]: (r[1] or "", r[2] or "") for r in rows}


def city_country_for(lead, geoip: dict[str, tuple[str, str]]) -> tuple[str, str]:
    if lead["source"] == "Facebook Lead Ad":
        return "", FB_LOCATION_NOTE
    did = lead.get("posthog_distinct_id")
    if did and did in geoip:
        city, country = geoip[did]
        return city, country or "Unknown"
    return "", "Unknown (no PostHog session recorded)"


# ---- sheet ops ----------------------------------------------------------------
def tab_id(svc, ssid, title):
    meta = svc.spreadsheets().get(spreadsheetId=ssid).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None


def row_values(lead, city, country):
    return [lead["date"], lead["source"], lead["name"], lead["email"], lead["phone"],
            city, country, lead["suburb_address"], lead["details"], lead["campaign"],
            lead["status"], lead.get("selling_plan", ""), lead["lead_id"]]


def hide_lead_id_column(svc, ssid, sheet_id):
    """Idempotent -- hides column M (Lead ID). Harmless to call every run."""
    try:
        svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": [{
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": LEAD_ID_COL, "endIndex": LEAD_ID_COL + 1},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }]}).execute()
    except Exception as e:
        print(f"(could not hide Lead ID column: {e})")


def refresh_selling_plans(svc, ssid, all_leads, already_ledgered: set[str], dry_run=False):
    """Update-in-place: for leads ALREADY in the sheet (added on a previous run),
    re-check whether their computed Selling Plan text has changed (new answer, or
    an existing answer changed) and, if so, overwrite ONLY that lead's Selling Plan
    cell -- never touches Name/Email/Status/Details, so any manual edit Will has
    made elsewhere on the row is untouched. Brand-new leads being inserted this same
    run already get their current Selling Plan written as part of the normal insert,
    so this only needs to consider leads NOT in this run's insert batch.

    Added 2026-07-21 (LIVE-LEADS-SHEET-AUTOUPDATE) so a seller's plan answers stay
    current on the sheet automatically as they come in, not just at first-add."""
    current = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{TAB}'!L2:M10000").execute().get("values", [])
    # row 2 in the sheet == index 0 here
    row_by_lead_id = {}
    for i, row in enumerate(current):
        plan_cell = row[0] if len(row) > 0 else ""
        lead_id_cell = row[1] if len(row) > 1 else ""
        if lead_id_cell:
            row_by_lead_id[lead_id_cell] = (i + 2, plan_cell)

    updates = []
    for lead in all_leads:
        if lead["lead_id"] not in already_ledgered:
            continue  # being freshly inserted this run (or truly new) -- not this function's job
        new_plan = lead.get("selling_plan", "")
        if not new_plan:
            continue  # nothing to say -- never overwrite a populated cell with blank
        hit = row_by_lead_id.get(lead["lead_id"])
        if hit is None:
            continue  # lead predates the Lead ID column (never rebuilt) -- can't locate it
        row_num, existing_plan = hit
        if existing_plan == new_plan:
            continue
        updates.append({"range": f"'{TAB}'!L{row_num}", "values": [[new_plan]]})

    if not updates:
        return 0
    print(f"{len(updates)} existing lead(s) have new/changed selling-plan data.")
    if dry_run:
        return len(updates)
    svc.spreadsheets().values().batchUpdate(spreadsheetId=ssid, body={
        "valueInputOption": "RAW", "data": updates,
    }).execute()
    return len(updates)


# ---- main -----------------------------------------------------------------
def set_env_from_file():
    # python-dotenv, not a hand-rolled parser (standardised 2026-07-23).
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(env_path, override=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spreadsheet-id", default=LIVE_SPREADSHEET_ID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-alert", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                     help="wipe the tab and rewrite every genuine lead from scratch "
                          "(e.g. after a schema/column change) instead of the normal "
                          "insert-only-new behaviour; re-seeds the ledger too")
    args = ap.parse_args()

    set_env_from_file()
    svc = get_sheets()
    client = get_client()
    db = client["system_monitor"]
    gc_db = client[GC_DB]

    sheet_id = tab_id(svc, args.spreadsheet_id, TAB)
    if sheet_id is None:
        print(f"Tab '{TAB}' not found in spreadsheet {args.spreadsheet_id}")
        sys.exit(1)

    all_leads = list(fb_lead_rows(db)) + list(ayh_rows(db)) + list(offmarket_rows(db, gc_db))

    if args.rebuild:
        candidates = sorted(all_leads, key=lambda l: l["date"], reverse=True)
        if args.dry_run:
            print(f"[rebuild] would rewrite {len(candidates)} lead(s)")
            client.close()
            return
        geoip = lookup_geoip({l.get("posthog_distinct_id") for l in candidates})
        values = [HEADERS] + [row_values(l, *city_country_for(l, geoip)) for l in candidates]
        svc.spreadsheets().values().clear(spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!A1:Z10000").execute()
        svc.spreadsheets().values().update(
            spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!A1",
            valueInputOption="RAW", body={"values": values}).execute()
        ts = datetime.now(AEST).isoformat()
        client[LEDGER_DB][LEDGER_COLL].delete_many({})
        for l in candidates:
            record_ledger(client, l["lead_id"], ts)
        hide_lead_id_column(svc, args.spreadsheet_id, sheet_id)
        client.close()
        print(f"[rebuild] wrote {len(candidates)} lead(s), ledger re-seeded.")
        return

    seen = load_ledger(client)
    candidates = [l for l in all_leads if l["lead_id"] not in seen]
    # newest first -> ends up at the very top after insert
    candidates.sort(key=lambda l: l["date"], reverse=True)

    refreshed = refresh_selling_plans(svc, args.spreadsheet_id, all_leads, seen, dry_run=args.dry_run)

    if not candidates:
        print("Nothing new." if not refreshed else f"No new leads; {refreshed} selling-plan update(s) applied.")
        client.close()
        return

    print(f"{len(candidates)} new lead(s):")
    for l in candidates:
        print(f"    {l['date']}  {l['source']:<28}  {l['suburb_address']}")

    if args.dry_run:
        client.close()
        return

    geoip = lookup_geoip({l.get("posthog_distinct_id") for l in candidates})

    n = len(candidates)
    svc.spreadsheets().batchUpdate(spreadsheetId=args.spreadsheet_id, body={"requests": [{
        "insertDimension": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": 1, "endIndex": 1 + n},
            "inheritFromBefore": False,
        }
    }]}).execute()
    values = []
    for l in candidates:
        city, country = city_country_for(l, geoip)
        values.append(row_values(l, city, country))
    svc.spreadsheets().values().update(
        spreadsheetId=args.spreadsheet_id, range=f"'{TAB}'!A2",
        valueInputOption="RAW", body={"values": values}).execute()

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

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
import base64
import hashlib
import hmac
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
from test_addresses import TEST_ADDRESS_SLUGS, is_test_address
from scripts.property_reports import occupancy_classifier as occ

# seller-intent enrichment (own-listing status/days-on-market + live listings viewed)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "samantha"))
import seller_intent as sim  # noqa: E402

# Conjunction guard: exclude other agencies' listings we're running a
# buyer-acquisition conjunction on from any seller-prospecting sheet output.
try:
    from scripts.conjunction_register import is_conjunction  # noqa: E402
except Exception:  # noqa: BLE001
    def is_conjunction(_x):  # type: ignore
        return False

# ---- config ---------------------------------------------------------------
LIVE_SPREADSHEET_ID = "1mRjT_PmjTepF1rDajJlM553Umy47dKa4fHOclrzAKFs"
TAB = "All Leads"
SA_KEY = os.environ.get("GOOGLE_VISION_SA_KEY", "/home/fields/.gcp-floor-plan-vision.json")
GC_DB = "Gold_Coast"
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

TEST_EMAILS = {"will@fieldsestate.com.au", "test@tester.com.au"}
# Will's test addresses live in the shared registry (scripts/test_addresses.py) so
# every lead surface blocks the same set. Kept under this name for the importers
# (leads_prune_nonleads, build_call_list) that already reference TEST_SLUGS.
TEST_SLUGS = set(TEST_ADDRESS_SLUGS)

# property_reports docs that exist for reasons OTHER than a person asking us for a
# report. A doc here is not a lead and must never reach the sheet — several did, and
# were sitting in the mailer-ready pool on 2026-08-17 ready to be posted to.
#
#   *_test_* / nollm_demo_* / *_comparison_*  our own test + demo builds
#   offmarket_ladder_prewarm                  speculative pre-build, nobody asked
#   offmarket_v4_mint                         a minted stub, nobody asked
#
# Kept as leads deliberately: sms_claim, offmarket_deck_cta, facebook, fb_leads —
# each of those IS a real person doing something.
NOT_A_LEAD_SOURCES = {
    "diagnostic_test", "fb_lead_ayh", "offmarket_report",
    "offmarket_direct_test_v1", "offmarket_ladder_prewarm", "offmarket_v4_mint",
    "nollm_demo_for_will", "home_reco_correction",
}
# Substring guard so the NEXT one-off test source doesn't silently leak onto the
# sheet the way offmarket_direct_test_v1 and nollm_comparison_2026-08-12 did.
NOT_A_LEAD_PATTERNS = ("test", "demo", "prewarm", "mint", "comparison", "diagnostic")


def is_not_a_lead(d: dict) -> str | None:
    """Reason this property_reports doc is not a lead, or None if it is one."""
    owner = d.get("owner") or {}
    if d.get("is_test"):
        return "is_test"
    if owner.get("is_internal"):
        return "owner.is_internal"
    if (owner.get("email") or "").lower() in TEST_EMAILS:
        return "test email"
    if is_test_address(d.get("slug"), d.get("address")):
        return "test address"
    src = (d.get("source") or "").lower()
    if src in NOT_A_LEAD_SOURCES:
        return f"source={d.get('source')}"
    if any(p in src for p in NOT_A_LEAD_PATTERNS):
        return f"source~{d.get('source')}"
    return None

# Facebook Lead Ads have no on-site PostHog session, so there is no per-lead geoip.
# The ad account only runs Australia-geo-targeted campaigns (see memory ads_reference:
# HOUSING neighbourhood targeting on Robina/Varsity Lakes/Burleigh Waters) -- flagged as
# inferred, not measured, so it's never confused with a verified PostHog geoip hit.
FB_LOCATION_NOTE = "AU (inferred — geo-targeted FB campaign, no on-site session)"

HEADERS = ["Date", "Source", "Name", "Email", "Phone", "City", "Country",
           "Suburb / Address", "Details", "Campaign / Channel", "Status",
           "Selling Plan", "Lead ID", "Situation", "PostHog"]

# PostHog's person page accepts a distinct_id directly in the path (that's what its own
# UI links to) and opens on the person's event feed — so this is a one-click jump from a
# row to "everything this person actually did". Facebook Lead Ads have no on-site session
# and so no distinct_id; those cells stay blank rather than linking somewhere useless.
POSTHOG_PROJECT_ID = "348370"
POSTHOG_PERSON_URL = "https://us.posthog.com/project/" + POSTHOG_PROJECT_ID + "/person/{did}"

# For AYH / property-report leads that have a bound CRM contact, the same column links
# instead to the friendly read-only CRM page (crm-contact.mjs) — address + full on-site
# behaviour + attribution on one page — which is more useful than the raw PostHog feed
# (and the distinct_id is still shown inside that page). Signed link, same HMAC scheme as
# priority_calls_to_sheet.crm_link. See fix-history [REPORT-LEAD-CRM-BIND].
CRM_SITE = "https://fieldsestate.com.au"


def crm_contact_link(contact_id) -> str:
    """Signed /api/v1/crm-contact URL. '' if the secret is unset (never a dead link)."""
    secret = os.environ.get("REPORT_LINK_SECRET", "")
    if not secret or not contact_id:
        return ""
    cid = str(contact_id)
    key = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"crm:{cid}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")[:16]
    return f"{CRM_SITE}/api/v1/crm-contact?id={cid}&k={key}"
# Selling Plan (col L, 0-indexed 11) and Lead ID (col M, 0-indexed 12) are the
# only two auto-refreshed-in-place columns (see LIVE-LEADS-SHEET-AUTOUPDATE
# fix-history, 2026-07-21) -- everything else is written once, at first add,
# and never touched again so Will's manual edits (Status, notes, etc.) are
# never clobbered. Lead ID is hidden -- it exists purely so a later run can
# find "this exact row" again to refresh its Selling Plan cell.
SELLING_PLAN_COL = 11  # 0-indexed -> column L
LEAD_ID_COL = 12       # 0-indexed -> column M (hidden)
SITUATION_COL = 13     # 0-indexed -> column N (new; auto-refreshed in place like Selling Plan)
POSTHOG_COL = 14       # 0-indexed -> column O (auto-refreshed in place; HYPERLINK formula)
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
        # `test_market` is what fb-lead-puller.py actually writes for out-of-market
        # copy-test leads; `is_test` is the generic flag. Check BOTH — reading only
        # `is_test` put 7 Brisbane test leads on the callable sheet (2026-08-20).
        if d.get("is_test") or d.get("test_market"):
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
        if is_not_a_lead(d):
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
            "crm_contact_id": owner.get("crm_contact_id"),
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
-- ⚠ BOTH deck generations. `offmarket_report_view` is fired only by the V1/V3 decks;
-- V4 fires `offmarket_v4_view` instead. V4 became the sole renderer around 2026-08-11,
-- so this query silently stopped producing ANY new off-market lead rows while
-- /off-market pageviews held flat at 10-19 users/day (78 V4 viewers in the 6 days to
-- 2026-08-15, none of whom reached this sheet). Keep the old name for history.
WHERE event IN ('offmarket_report_view', 'offmarket_v4_view')
  AND timestamp > now() - INTERVAL 180 DAY
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


# ---- worklist-only leads (sources not covered by fb/ayh/offmarket generators) --
SOURCE_LABELS = {
    "analyse_your_home": "Analyse Your Home", "footer_subscribe": "Newsletter (footer)",
    "form_submission": "Form Submission", "posthog_sync": "Site Engagement",
    "direct_appraisal_request": "Direct Appraisal Request", "price_alert": "Price Alert",
    "five_property_friday": "5 Property Friday", "website_feedback": "Website Feedback",
    "launch_form": "Launch Form", "lead": "Lead",
    "site_behavior": "Site Behaviour (anon)",
    "listing_expiry": "Listing Nearing Expiry",
}
# Collections already emitted by fb_lead_rows / ayh_rows / offmarket_rows — a worklist
# lead touching any of these is already on the sheet under its source-specific Lead ID.
COVERED_ORIGIN_COLLECTIONS = {"fb_leads", "property_reports", "offmarket_orders"}


def worklist_only_rows(db):
    """Emit a row for every REAL lead_worklist lead not covered by the three source
    generators — newsletter subscribers, direct appraisal requests, 5-Property-Friday,
    website feedback, etc. Deduped by lead_id 'worklist:<lead_key>' via the ledger. The
    Situation column (computed downstream) carries the seller-intent context."""
    for d in db["lead_worklist"].find({}):
        if d.get("is_test"):
            continue
        origin_colls = {o.get("collection") for o in (d.get("origins") or [])}
        if origin_colls & COVERED_ORIGIN_COLLECTIONS:
            continue
        if str(d.get("lead_key", "")).startswith("offmarket_view:"):
            continue
        # CONJUNCTION GUARD (Guard A, render side): a worklist row for a
        # conjunction property (another agency's listing) must never surface as
        # a seller-prospecting lead. This catches rows captured BEFORE the
        # upstream guard in seller_intent.listing_expiry_monitor existed — e.g.
        # the pre-existing listing:93-burleigh-street-burleigh-waters row.
        # See fix-history [CONJUNCTION-REGISTER-AND-GUARDS] (2026-08-20).
        if is_conjunction(d.get("address")) or is_conjunction(
                str(d.get("lead_key", "")).removeprefix("listing:")):
            continue
        srcs = d.get("sources") or []
        label = " / ".join(dict.fromkeys(SOURCE_LABELS.get(s, s.replace("_", " ").title())
                                         for s in srcs)) or "Website Lead"
        ex = d.get("extra") or {}
        occ = d.get("occupancy") or {}
        details = []
        if occ.get("type") and occ["type"] != "unknown":
            details.append(f"occupancy={occ['type']}")
        if d.get("years_held"):
            details.append(f"held={d['years_held']}y")
        for k in ("buy_timeline", "sell_timeline", "timeline", "value_range",
                  "subscriber_status", "signal"):
            if ex.get(k):
                details.append(f"{k}={ex[k]}")
        yield {
            "lead_id": f"worklist:{d['lead_key']}",
            "date": (str(d.get("first_seen") or "")[:10]),
            "source": label,
            "name": d.get("name") or "",
            "email": d.get("email") or "",
            "phone": d.get("phone") or "",
            "posthog_distinct_id": ex.get("posthog_distinct_id"),
            "suburb_address": d.get("address") or "",
            "details": "; ".join(details),
            "campaign": ", ".join(srcs),
            "status": "",  # left blank for Will to triage
        }


# ---- seller-intent "Situation" column ---------------------------------------
def build_worklist_index(db):
    """Index lead_worklist so any source-row can be matched to its CRM record."""
    by_origin, by_key, by_email = {}, {}, {}
    for d in db["lead_worklist"].find({}):
        if d.get("lead_key"):
            by_key[d["lead_key"]] = d
        em = (d.get("email") or "").lower()
        if em:
            by_email[em] = d
        for o in d.get("origins") or []:
            by_origin[(o.get("collection"), str(o.get("id")))] = d
    return by_origin, by_key, by_email


def _worklist_doc_for(lead, idx):
    by_origin, by_key, by_email = idx
    lid = lead.get("lead_id", "")
    if lid.startswith("worklist:"):
        return by_key.get(lid[len("worklist:"):])
    if ":" in lid:
        coll, rid = lid.split(":", 1)
        d = by_origin.get((coll, rid))
        if d:
            return d
    if lid in by_key:
        return by_key[lid]
    em = (lead.get("email") or "").lower()
    if em and em in by_email:
        return by_email[em]
    return None


def hotness_label(si: dict) -> str:
    """Render the two things `hotness` mixes together as two visible numbers.

    seller_intent's `hotness` is a single unbounded tally of two unrelated inputs:
    what the person DID (behavioral_score — sessions, page views, valuations built,
    price alerts, address searches) and what is happening to their PROPERTY
    (listing_bonus — +22 listing near expiry, +14 withdrawn, +12 stale, -6 freshly
    listed). Collapsed into one number they can't be told apart, so a lead with real
    engagement and one with an expiring listing and zero engagement look alike.

    Worse, the single number reads like a warmth grade when it's actually a count:
    "hot 2" means "one session, nothing else" — the floor, not "slightly warm". On
    2026-08-01, 100 of 259 scored leads sat at exactly 2 and 180 were at <= 2, while
    the scale ran to 164. Split so a follow-up call can see which half is driving it.
    """
    intent = si.get("behavioral_score")
    if intent is None:  # nothing to split — fall back to the old single number
        return f"hot {si['hotness']}" if si.get("hotness") else ""
    bonus = si.get("listing_bonus")
    if bonus is None:
        # Docs scored before 2026-08-01 have no listing_bonus, but hotness is
        # bscore + listing_bonus by construction, so this recovers it exactly.
        bonus = (si.get("hotness") or 0) - intent
    parts = []
    if intent:
        parts.append(f"intent {intent}")
    if bonus:
        parts.append(f"listing {bonus:+d}")
    return " · ".join(parts)


def format_situation(doc, si) -> str:
    """The verbose seller-intent story (behavioral + PropRadar), with a hotness/moment
    header, so a follow-up can be fully tailored. Falls back to a terse compose for any
    lead not yet enriched with a story."""
    si = si or {}
    story = si.get("story")
    if story:
        head = []
        pri = doc.get("priority")
        if pri and pri not in ("low", "test", None):
            head.append(pri.upper())
        hot = hotness_label(si)
        if hot:
            head.append(hot)
        prefix = f"[NOW] {si['moment']}. " if si.get("moment") else ""
        headstr = (" · ".join(head) + " — ") if head else ""
        return f"{prefix}{headstr}{story}"
    parts = []
    pri = doc.get("priority")
    if pri and pri not in ("low", "test", None):
        parts.append(f"PRIORITY {pri.upper()}")
    own = si.get("own_property") or {}
    st = own.get("listing_status")
    if st:
        s = f"Own home {str(st).replace('_', ' ')}"
        if own.get("days_on_market") is not None:
            s += f", {own['days_on_market']}d on market"
        if own.get("price"):
            s += f" ({own['price']})"
        if own.get("agency"):
            s += f" via {own['agency']}"
        parts.append(s)
    viewed = si.get("current_listings_viewed") or []
    if viewed:
        vs = "; ".join(
            f"{v.get('address')} [{v.get('price') or '?'}"
            + (f", {v['days_on_market']}d" if v.get("days_on_market") is not None else "") + "]"
            for v in viewed[:3])
        parts.append(f"Also viewing live listings: {vs}")
    occ = doc.get("occupancy") or {}
    ot = occ.get("type")
    if ot and ot != "unknown":
        yh = doc.get("years_held")
        parts.append(str(ot).replace("_", " ") + (f", held {yh}y" if yh else ""))
    label = si.get("label")
    concl = si.get("conclusion")
    if concl and label and label != "no_cross_signal":
        parts.append("→ " + concl)
    elif doc.get("reason"):
        parts.append("→ " + doc["reason"])
    return " | ".join(p for p in parts if p)


def situation_for(lead, idx, sm, gc_db, suburb_index) -> str:
    """Prefer the STORED seller_intent (computed nightly at 02:00 with a PropRadar budget)
    so the sheet never re-hits PropRadar for every lead. Compute live (bounded PropRadar)
    only for a lead not yet enriched — i.e. one added since the last nightly run."""
    doc = _worklist_doc_for(lead, idx)
    if not doc:
        return ""
    si = doc.get("seller_intent")
    if not si or not si.get("story"):
        try:
            si = sim.analyze(doc, sm, gc_db, suburb_index, pr_budget=[3])
        except Exception:
            si = doc.get("seller_intent") or {}
    return format_situation(doc, si)


def _cell(v):
    """Coerce any value to something the Sheets API will accept in a cell.

    A multi-select answer on a Facebook lead form comes back as a LIST, not a string
    (e.g. area = ["burleigh_waters", "open_to_all_three", "varsity_lakes", "robina"]).
    Sheets rejects the whole batch on a nested list -- "Invalid values[3][7]: list_value"
    -- so ONE such lead failed the entire Live Leads Tracker write and blocked both
    downstream chain steps (2026-08-30). Coerce here, at the boundary, so no future
    field of any shape can poison the batch the same way.
    """
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x) for x in v)
    if v is None:
        return ""
    return v if isinstance(v, (str, int, float, bool)) else str(v)


def row_values(lead, city, country):
    # Column O (PostHog) is left blank here on purpose: this batch is written with
    # valueInputOption=RAW, which would store a =HYPERLINK() formula as literal text.
    # RAW is the right choice for the rest of the row -- USER_ENTERED would reinterpret
    # unit addresses like "1/35 Thornleigh Crescent" as dates. refresh_posthog_links()
    # fills O separately with USER_ENTERED, confining formula parsing to the one column
    # that only ever holds our formula.
    return [_cell(x) for x in
            (lead["date"], lead["source"], lead["name"], lead["email"], lead["phone"],
             city, country, lead["suburb_address"], lead["details"], lead["campaign"],
             lead["status"], lead.get("selling_plan", ""), lead["lead_id"],
             lead.get("situation", ""), "")]


def refresh_posthog_links(svc, ssid, all_leads, dry_run=False):
    """Fill column O with a clickable link to each lead's PostHog person page.

    Runs over EVERY lead (not just new ones) so it backfills existing rows and picks up
    a distinct_id that was attached after the row was first written. Matched by the
    hidden Lead ID in column M -- the same safe mechanism as refresh_situations -- and
    only ever writes column O. The visible text is the full distinct_id, so it can be
    copied straight out of the sheet, not just clicked."""
    current = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{TAB}'!M2:O10000").execute().get("values", [])
    row_by_lead_id = {}
    for i, row in enumerate(current):
        lid = row[0] if len(row) > 0 else ""
        existing = row[2] if len(row) > 2 else ""
        if lid:
            row_by_lead_id[lid] = (i + 2, existing)

    updates = []
    for lead in all_leads:
        did = lead.get("posthog_distinct_id")
        crm_url = crm_contact_link(lead.get("crm_contact_id"))
        if not did and not crm_url:
            continue  # e.g. Facebook Lead Ads -- no on-site session, nothing to link to
        hit = row_by_lead_id.get(lead["lead_id"])
        if hit is None:
            continue
        row_num, existing = hit
        # A bound CRM contact wins: link to the friendly CRM page (address + behaviour +
        # attribution). We OVERWRITE an existing PostHog link here so rows written before
        # the report-lead bind get upgraded -- but skip if already showing "CRM ↗".
        if crm_url:
            if existing == "CRM ↗":
                continue
            updates.append({"range": f"'{TAB}'!O{row_num}",
                            "values": [[f'=HYPERLINK("{crm_url}","CRM ↗")']]})
            continue
        if existing:
            continue  # already linked; the person page URL never changes
        url = POSTHOG_PERSON_URL.format(did=did)
        updates.append({"range": f"'{TAB}'!O{row_num}",
                        "values": [[f'=HYPERLINK("{url}","{did}")']]})

    if not updates:
        return 0
    print(f"PostHog person links: filling {len(updates)} row(s).")
    if dry_run:
        return len(updates)
    svc.spreadsheets().values().batchUpdate(spreadsheetId=ssid, body={
        "valueInputOption": "USER_ENTERED", "data": updates}).execute()
    return len(updates)


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


# Soft orange — "they've gone to market with someone else; park this one."
LISTED_ORANGE = {"red": 0.98, "green": 0.80, "blue": 0.60}
_WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}


def _is_our_orange(bg) -> bool:
    """True only for a fill this script painted. Any OTHER colour is assumed to be
    Will's own manual highlight and is left strictly alone."""
    if not bg:
        return False
    return all(abs((bg.get(k) if bg.get(k) is not None else 1.0) - LISTED_ORANGE[k]) < 0.02
               for k in ("red", "green", "blue"))


def _is_blank(bg) -> bool:
    if not bg:
        return True
    return all((bg.get(k) if bg.get(k) is not None else 1.0) > 0.98 for k in ("red", "green", "blue"))


def just_listed_now(doc) -> bool:
    """Has this lead put their home on the market with another agent?

    Deliberately NOT keyed on seller_intent's `just_listed`, which is a one-run
    TRANSITION flag (not-listed last run -> listed this run). Painting on that alone
    would make the row flash orange for a single night and clear itself, which is
    useless to anyone reading the sheet the next morning.

    Keyed instead on the `on_market_fresh` STATE, which persists for as long as the
    fact does: "listed <69 days ago, comfortably inside the competitor's ~90-day
    exclusive agency term — NOT a lead yet, don't approach now." The highlight then
    clears itself the moment the listing ages into on_market_stale / on_market_expiring
    — which is exactly when they become a prime lead again. So orange appearing means
    "stop calling", and orange disappearing means "start calling".
    """
    si = (doc or {}).get("seller_intent") or {}
    return bool(si.get("label") == "on_market_fresh" or si.get("just_listed"))


def refresh_listed_highlight(svc, ssid, sheet_id, all_leads, idx, dry_run=False):
    """Paint whole rows orange for leads that have just listed with another agent,
    and un-paint them once that stops being true. Only ever touches the row's
    background colour — never a cell value — so manual notes/status edits are safe."""
    grid = svc.spreadsheets().get(
        spreadsheetId=ssid, ranges=[f"'{TAB}'!A2:A10000"], includeGridData=True,
        fields="sheets/data/rowData/values/userEnteredFormat/backgroundColor").execute()
    rows = (grid.get("sheets") or [{}])[0].get("data", [{}])[0].get("rowData", [])
    current_bg = []
    for r in rows:
        vals = r.get("values") or [{}]
        current_bg.append((vals[0].get("userEnteredFormat") or {}).get("backgroundColor"))

    lead_ids = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{TAB}'!M2:M10000").execute().get("values", [])

    want_orange = {l["lead_id"] for l in all_leads if just_listed_now(_worklist_doc_for(l, idx))}

    paint, clear = [], []
    for i, row in enumerate(lead_ids):
        lid = row[0] if row else ""
        if not lid:
            continue
        bg = current_bg[i] if i < len(current_bg) else None
        if lid in want_orange:
            if _is_blank(bg):          # never overwrite a colour Will chose himself
                paint.append(i + 2)
        elif _is_our_orange(bg):       # no longer freshly listed -> hand the row back
            clear.append(i + 2)

    if not paint and not clear:
        return 0
    print(f"Listed-with-another-agent highlight: {len(paint)} row(s) to orange, "
          f"{len(clear)} back to blank.")
    if dry_run:
        return len(paint) + len(clear)

    requests = []
    for rows_, colour in ((paint, LISTED_ORANGE), (clear, _WHITE)):
        for rn in rows_:
            requests.append({"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": rn - 1, "endRowIndex": rn,
                          "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                "cell": {"userEnteredFormat": {"backgroundColor": colour}},
                "fields": "userEnteredFormat.backgroundColor",
            }})
    svc.spreadsheets().batchUpdate(spreadsheetId=ssid, body={"requests": requests}).execute()
    return len(paint) + len(clear)


def ensure_headers(svc, ssid, dry_run=False):
    """Idempotently make sure the late-added headers exist: N1 'Situation' (absent on
    pre-2026-07-28 sheets) and O1 'PostHog' (absent pre-2026-08-01)."""
    for cell, want in (("N1", "Situation"), ("O1", "PostHog")):
        cur = svc.spreadsheets().values().get(
            spreadsheetId=ssid, range=f"'{TAB}'!{cell}").execute().get("values", [])
        if cur and cur[0] and cur[0][0] == want:
            continue
        if dry_run:
            print(f"(would set {cell} = '{want}')")
            continue
        svc.spreadsheets().values().update(
            spreadsheetId=ssid, range=f"'{TAB}'!{cell}",
            valueInputOption="RAW", body={"values": [[want]]}).execute()


def refresh_situations(svc, ssid, all_leads, already_ledgered, dry_run=False):
    """Update-in-place col N (Situation) for leads ALREADY on the sheet — backfills the
    new column on first run and keeps it current as seller-intent evolves (own listing's
    days-on-market ticks up, new live listings viewed). Matches rows by the hidden Lead ID
    (col M), the same safe mechanism as refresh_selling_plans; never touches any other cell,
    so Will's manual Status/notes edits are preserved."""
    current = svc.spreadsheets().values().get(
        spreadsheetId=ssid, range=f"'{TAB}'!M2:N10000").execute().get("values", [])
    row_by_lead_id = {}
    for i, row in enumerate(current):
        lead_id_cell = row[0] if len(row) > 0 else ""
        sit_cell = row[1] if len(row) > 1 else ""
        if lead_id_cell:
            row_by_lead_id[lead_id_cell] = (i + 2, sit_cell)
    updates = []
    for lead in all_leads:
        if lead["lead_id"] not in already_ledgered:
            continue
        new_sit = lead.get("situation", "")
        if not new_sit:
            continue
        hit = row_by_lead_id.get(lead["lead_id"])
        if hit is None:
            continue
        row_num, existing = hit
        if existing == new_sit:
            continue
        updates.append({"range": f"'{TAB}'!N{row_num}", "values": [[new_sit]]})
    if not updates:
        return 0
    print(f"{len(updates)} existing lead(s) have new/changed Situation.")
    if dry_run:
        return len(updates)
    svc.spreadsheets().values().batchUpdate(spreadsheetId=ssid, body={
        "valueInputOption": "RAW", "data": updates}).execute()
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

    all_leads = (list(fb_lead_rows(db)) + list(ayh_rows(db)) + list(offmarket_rows(db, gc_db))
                 + list(worklist_only_rows(db)))

    # Leads already moved to the "Came to Market" tab must never come back. The normal
    # path is protected by the insert ledger, but --rebuild WIPES that ledger and
    # rewrites every lead from source — which would silently undo every sweep. This is
    # the only guard that survives a rebuild. See scripts/leads_came_to_market.py.
    gone = {d["lead_id"]
            for coll in ("leads_came_to_market", "leads_pruned_nonleads")
            for d in db[coll].find({}, {"lead_id": 1}) if d.get("lead_id")}
    if gone:
        before = len(all_leads)
        all_leads = [l for l in all_leads if l["lead_id"] not in gone]
        if before != len(all_leads):
            print(f"({before - len(all_leads)} lead(s) held back — already on "
                  f"'Came to Market')")

    # Attach the seller-intent "Situation" line to every lead (own-listing status +
    # days-on-market + the live listings they viewed + tailored follow-up conclusion).
    wl_idx = build_worklist_index(db)
    suburb_index = sim.build_suburb_index(gc_db)
    for l in all_leads:
        l["situation"] = situation_for(l, wl_idx, db, gc_db, suburb_index)

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
        # values().clear() wipes VALUES but not FORMATTING, and a rebuild re-orders every
        # row — so any existing orange would end up sitting on whichever lead now occupies
        # that row number. Strip all backgrounds first, then re-derive from scratch.
        svc.spreadsheets().batchUpdate(spreadsheetId=args.spreadsheet_id, body={"requests": [{
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                "cell": {"userEnteredFormat": {"backgroundColor": _WHITE}},
                "fields": "userEnteredFormat.backgroundColor",
            }}]}).execute()
        refresh_posthog_links(svc, args.spreadsheet_id, candidates)
        refresh_listed_highlight(svc, args.spreadsheet_id, sheet_id, candidates, wl_idx)
        client.close()
        print(f"[rebuild] wrote {len(candidates)} lead(s), ledger re-seeded.")
        return

    seen = load_ledger(client)
    candidates = [l for l in all_leads if l["lead_id"] not in seen]
    # newest first -> ends up at the very top after insert
    candidates.sort(key=lambda l: l["date"], reverse=True)

    refreshed = refresh_selling_plans(svc, args.spreadsheet_id, all_leads, seen, dry_run=args.dry_run)
    ensure_headers(svc, args.spreadsheet_id, dry_run=args.dry_run)
    refreshed_sit = refresh_situations(svc, args.spreadsheet_id, all_leads, seen, dry_run=args.dry_run)

    if not candidates:
        linked = refresh_posthog_links(svc, args.spreadsheet_id, all_leads, dry_run=args.dry_run)
        painted = refresh_listed_highlight(svc, args.spreadsheet_id, sheet_id, all_leads,
                                           wl_idx, dry_run=args.dry_run)
        msg = "Nothing new."
        if refreshed or refreshed_sit or linked or painted:
            msg = (f"No new leads; {refreshed} selling-plan + {refreshed_sit} situation "
                   f"+ {linked} posthog-link + {painted} highlight update(s) applied.")
        print(msg)
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

    # After the insert, so the rows just added get their link + highlight in the same run.
    refresh_posthog_links(svc, args.spreadsheet_id, all_leads)
    refresh_listed_highlight(svc, args.spreadsheet_id, sheet_id, all_leads, wl_idx)

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

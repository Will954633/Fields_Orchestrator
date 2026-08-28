#!/usr/bin/env python3
"""
fb-lead-puller.py — Pull Facebook/Instagram Instant Form (lead ad) submissions
into MongoDB and notify Will via Telegram.

Polling design (no webhook): every run, fetch leads for each ACTIVE leadgen form
on the Page, dedupe by lead id against system_monitor.fb_leads, store new ones,
and send a Telegram alert per new lead. Meta retains leads on the form, so polling
+ dedupe captures everything even if a run is missed.

Requires: FACEBOOK_ADS_TOKEN (system-user token w/ leads_retrieval + pages access),
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, COSMOS_CONNECTION_STRING.

Usage:
    python3 scripts/fb-lead-puller.py            # pull + store + notify
    python3 scripts/fb-lead-puller.py --dry-run  # pull + print, no writes/notify
    python3 scripts/fb-lead-puller.py --no-notify
Schedule (suggested): every 15 min via cron.
"""
import os, sys, argparse, requests, re
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client  # noqa: E402
import crm_lead_sync  # noqa: E402
import fpf_send  # noqa: E402

PAGE_ID = "889412530933297"
API = "https://graph.facebook.com/v18.0"
TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]

# AYH forms are fulfilled (address -> mini-site -> email) via a Netlify function.
AYH_FORM_IDS = {"1735418400974915"}
FULFIL_URL = "https://fieldsestate.com.au/.netlify/functions/ayh-lead-fulfil"

# Seller-intent Instant-Form lead ads (Home Owner Lead Funnel, 2026-07-28).
# These capture full_name + email + phone_number + a selling-intent qualifier so
# Will can CALL them. The generic notify() below is hardcoded for buyer forms and
# would fire an empty, mislabelled alert (no name/phone) for these — so route them
# to notify_seller() which surfaces the phone number and the selling answer.
# Populated as forms are created (see 03_Facebook/Home_Owner_Lead_Funnel_Search).
SELLER_FORM_IDS = {
    "1961613607744103",  # GC Seller Intent (report) — name+email+phone
    "1689297792302611",  # GC Sold-Price Alerts — name+email+phone
    "1307646261451971",  # GC Seller Intent (report+address)
    "2542687336206872",  # Independent Listing Analysis (carousel) — name+email+phone
                         # Missing until 2026-08-20: its 4 leads (all with phones) fell
                         # through to the generic buyer notify(), which renders neither
                         # name nor phone, so Will got an email-only alert for four
                         # phone-bearing seller leads.
    "3247679548765163",  # Independent Listing Analysis (carousel) v1 — ...-copy
                         # A duplicate of the form above with its own ID; inherited the
                         # same gap. Added 2026-08-28.
    # Property Narratives Instant Form campaign (owner-intent angles, name+phone,
    # 2026-08-25). Uncategorised on launch -> generic buyer notify() -> 3 leads /
    # $81 spend fired contactless alerts. Added 2026-08-28.
    "942432315543625",   # Fields Narratives — Nearby Sold (name+phone)
    "1580988970376517",  # Fields Narratives — Price Reduction (name+phone)
    "1010229908733472",  # Fields Narratives — Scarcity (name+phone)
    "3039075966262793",  # Fields Narratives — Value Gap (name+phone)
}

# OUT-OF-MARKET copy-test forms (SEQ ex-GC). Captured SILENTLY as signal only:
# NO Telegram alert, NO CRM sync, NO fulfilment — these leads receive NOTHING
# post-submission (Will, 2026-07-28: a GC report in a Brisbane inbox would burn the
# brand). We only tally count + selling-intent answer per angle. Not callable.
TEST_FORM_IDS = {
    "2116153228999527",  # TEST Seller Report (report) v2
    "1066797086300513",  # TEST Sold-Price Alerts v2
    "2861236714240026",  # TEST Seller Report (report+address) v2
}

# "Before You List" — free printed hardcover, POSTED (2026-07-28). Physical-only:
# name+email+phone+postal address. Route to the print-and-post queue (tagged by
# A/B/C arm) so Will can dispatch a book; a mailed hardcover has a real per-unit
# cost, so implausible/blank addresses are flagged needs_review, not auto-posted.
BYL_FORM_IDS = {"1797190291266790"}
CORE_POSTCODES = {"4220", "4226", "4227"}  # Burleigh Waters, Robina, Varsity Lakes


def page_token():
    r = requests.get(f"{API}/{PAGE_ID}", params={"fields": "access_token", "access_token": TOKEN}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def active_forms(ptoken):
    r = requests.get(f"{API}/{PAGE_ID}/leadgen_forms",
                     params={"fields": "id,name,status", "access_token": ptoken, "limit": 100}, timeout=20)
    r.raise_for_status()
    return [f for f in r.json().get("data", []) if f.get("status") == "ACTIVE"]


# Attribution fields on the lead node — present when the lead came from an ad
# (absent / is_organic=true for leads from an organic form post). Requesting them
# explicitly is required; the /leads edge returns only id+created_time+field_data
# by default. This is what lets Brain 2 join a lead back to its ad + spend.
LEAD_FIELDS = ("id,created_time,field_data,ad_id,ad_name,adset_id,adset_name,"
               "campaign_id,campaign_name,platform,is_organic")


def form_leads(form_id, ptoken):
    """Yield all leads for a form (paginated)."""
    url = f"{API}/{form_id}/leads"
    params = {"access_token": ptoken, "limit": 100, "fields": LEAD_FIELDS}
    while url:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for lead in data.get("data", []):
            yield lead
        url = (data.get("paging") or {}).get("next")
        params = None  # 'next' already has all params


def flatten(lead):
    out = {}
    for f in lead.get("field_data", []):
        vals = f.get("values") or []
        out[f.get("name")] = vals[0] if len(vals) == 1 else vals
    return out


def notify(fields, form_name, created, campaign_name=None, ad_name=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    owns = str(fields.get("owns_gc_home", "")).lower() == "yes"
    # Source line: which ad/campaign this lead came from (lets us tell the
    # carousel lead ad apart from the single-image one — they share nothing but
    # both feed a Buyer-Brief-style form). Absent = organic form post.
    source = campaign_name or ad_name
    src_line = f"📣 _{source}_" if source else "📣 _Organic (no ad)_"
    lines = ["🎯 *New buyer lead*" + ("  — OWNS A GC HOME 🏠" if owns else ""),
             f"_{form_name}_", src_line, ""]
    # SAFETY NET (2026-08-28): surface name + phone on ANY lead that carries them,
    # even a form we never categorised. This function used to render only the buyer
    # qualifier fields below, so an uncategorised name+phone form (owner/seller
    # angle mislabelled as buyer) fired an alert with NO contact detail at all —
    # uncallable. That bit twice: the Listing-Analysis form on 2026-08-20 and the
    # Property Narratives (name+phone) forms on 2026-08-25 (3 leads, $81 spent).
    # Explicit categorisation (SELLER_FORM_IDS etc.) still gives the richer
    # "call them / selling intent" alert; this just guarantees no lead is ever
    # contactless. See fix-history [TELEGRAM-GENERIC-NOTIFY-NO-CONTACT].
    _name = fields.get("full_name") or fields.get("name")
    _phone = fields.get("phone_number") or fields.get("phone")
    if _name:
        lines.append(f"• *Name:* {_name}")
    if _phone:
        lines.append(f"• *📞 Phone:* {_phone}")
    label = {"area": "Area", "bedrooms": "Beds", "bathrooms": "Baths",
             "timeframe": "Timeframe", "owns_gc_home": "Owns GC home", "email": "Email"}
    for k in ["email", "area", "bedrooms", "bathrooms", "timeframe", "owns_gc_home"]:
        if k in fields:
            lines.append(f"• *{label.get(k, k)}:* {fields[k]}")
    lines.append("")
    lines.append(f"_{created}_")
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "Markdown"}, timeout=20)
    except Exception as e:
        print(f"  telegram notify failed: {e}", file=sys.stderr)


def notify_seller(fields, form_name, created, campaign_name=None, ad_name=None):
    """Seller-intent lead alert — surfaces the PHONE NUMBER and selling answer so
    Will can call promptly. Distinct from the buyer notify() (which renders neither)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    # selling intent may arrive under a few possible keys depending on the form
    intent = (fields.get("selling_intent") or fields.get("selling_timeframe")
              or fields.get("thinking_of_selling") or "?")
    hot = str(intent).lower().startswith(("yes", "now", "within", "0", "1", "2", "3"))
    name = fields.get("full_name") or fields.get("name") or "?"
    phone = fields.get("phone_number") or fields.get("phone") or "?"
    source = campaign_name or ad_name
    src_line = f"📣 _{source}_" if source else "📣 _Organic (no ad)_"
    lines = ["🏷️ *New SELLER lead — call them*" + ("  🔥 SELLING INTENT" if hot else ""),
             f"_{form_name}_", src_line, "",
             f"• *Name:* {name}",
             f"• *📞 Phone:* {phone}",
             f"• *Email:* {fields.get('email','?')}",
             f"• *Selling?:* {intent}"]
    for k in ("property_address", "address", "suburb"):
        if fields.get(k):
            lines.append(f"• *{k.replace('_',' ').title()}:* {fields[k]}")
            break
    lines += ["", f"_{created}_"]
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "Markdown"}, timeout=20)
    except Exception as e:
        print(f"  telegram notify failed: {e}", file=sys.stderr)


def fulfil_ayh(fields):
    """Resolve address -> mini-site -> email via the Netlify fulfilment function."""
    payload = {"address": fields.get("property_address", ""),
               "suburb": fields.get("suburb", ""),
               "email": fields.get("email", "")}
    try:
        r = requests.post(FULFIL_URL, json=payload, timeout=45)
        return r.json()
    except Exception as e:
        return {"ok": False, "reason": f"call_failed:{e}"}


def notify_ayh(fields, form_name, created, result):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    addr = fields.get("property_address", "?")
    email = fields.get("email", "?")
    if result.get("ok"):
        head = "🏡 *New AYH lead — report emailed*"
        tail = f"Report: fieldsestate.com.au/your-home/{result.get('slug')}"
    else:
        head = "⚠️ *New AYH lead — NEEDS MANUAL HANDLING*"
        tail = f"Reason: `{result.get('reason')}` — resolve/send by hand."
    lines = [head, f"_{form_name}_", "",
             f"• *Address:* {addr}", f"• *Suburb:* {fields.get('suburb','?')}",
             f"• *Selling?:* {fields.get('selling_timeframe','?')}", f"• *Email:* {email}",
             "", tail, f"_{created}_"]
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "Markdown"}, timeout=20)
    except Exception as e:
        print(f"  telegram notify failed: {e}", file=sys.stderr)


def fulfil_byl(fields, doc, coll):
    """Queue a 'Before You List' lead for print-and-post, tagged by A/B/C arm.
    Returns (queue_doc, needs_review)."""
    name = fields.get("full_name") or fields.get("name") or ""
    email = fields.get("email") or ""
    phone = fields.get("phone_number") or fields.get("phone") or ""
    address = (fields.get("postal_address")
               or next((v for k, v in fields.items() if "address" in k.lower()), "") or "")
    m = re.search(r"BYL\s+([ABC])\b", doc.get("adset_name") or "")
    arm = m.group(1) if m else "?"
    pc = next(iter(re.findall(r"\b(\d{4})\b", str(address))), None)
    needs_review = (not str(address).strip()) or (pc is None)
    q = {"book": "before_you_list", "campaign": "before_you_list", "arm": arm,
         "name": name, "email": email, "mobile": phone, "address": address,
         "status": "needs_review" if needs_review else "queued_for_post",
         "lead_id": doc["_id"], "source_form_id": doc["form_id"],
         "created_at": datetime.now(timezone.utc).isoformat()}
    coll.database["print_post_queue"].insert_one(q)
    return q, needs_review


def notify_byl(fields, form_name, created, arm, address, needs_review):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    head = "📕 *Before You List — post the book*" + ("  ⚠️ CHECK ADDRESS" if needs_review else "")
    lines = [head, f"_{form_name}_  ·  arm *{arm}*", "",
             f"• *Name:* {fields.get('full_name', '?')}",
             f"• *📞 Phone:* {fields.get('phone_number', '?')}",
             f"• *Email:* {fields.get('email', '?')}",
             f"• *📮 Address:* {address or '— none given —'}", "", f"_{created}_"]
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "Markdown"}, timeout=20)
    except Exception as e:
        print(f"  telegram notify failed: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args()

    ptoken = page_token()
    forms = active_forms(ptoken)
    print(f"[{datetime.now(timezone.utc).isoformat()}] active forms: {[f['name'] for f in forms]}")

    coll = None
    if not args.dry_run:
        coll = get_client()["system_monitor"]["fb_leads"]

    new_count = 0
    for form in forms:
        for lead in form_leads(form["id"], ptoken):
            lid = lead["id"]
            fields = flatten(lead)
            if args.dry_run:
                print(f"  [dry] {lid} {fields}")
                continue
            if coll.find_one({"_id": lid}):
                continue  # already processed
            doc = {"_id": lid, "form_id": form["id"], "form_name": form["name"],
                   "created_time": lead.get("created_time"), "fields": fields,
                   # ad attribution (None when organic form post) — Brain 2 join keys
                   "ad_id": lead.get("ad_id"), "ad_name": lead.get("ad_name"),
                   "adset_id": lead.get("adset_id"), "adset_name": lead.get("adset_name"),
                   "campaign_id": lead.get("campaign_id"),
                   "campaign_name": lead.get("campaign_name"),
                   "platform": lead.get("platform"), "is_organic": lead.get("is_organic"),
                   "raw": lead, "pulled_at": datetime.now(timezone.utc).isoformat()}
            new_count += 1
            print(f"  NEW lead {lid}: {fields.get('email')}")
            if form["id"] in AYH_FORM_IDS:
                result = fulfil_ayh(fields)
                doc["fulfilment"] = result
                print(f"    AYH fulfil -> {result}")
                coll.insert_one(doc)
                if not args.no_notify:
                    notify_ayh(fields, form["name"], lead.get("created_time"), result)
            elif form["id"] in TEST_FORM_IDS:
                # out-of-market signal only: store tagged, NO notify / CRM / fulfilment
                # Write BOTH flags. `test_market` is the descriptive one; `is_test` is
                # the flag every downstream consumer already filters on, and writing
                # only the former is how 7 of these reached Will's callable sheet.
                doc["test_market"] = True
                doc["is_test"] = True
                coll.insert_one(doc)
                print(f"    [test-market] captured silently (no follow-up)")
            elif form["id"] in SELLER_FORM_IDS:
                coll.insert_one(doc)
                if not args.no_notify:
                    notify_seller(fields, form["name"], lead.get("created_time"),
                                  lead.get("campaign_name"), lead.get("ad_name"))
            elif form["id"] in BYL_FORM_IDS:
                coll.insert_one(doc)
                q, needs_review = fulfil_byl(fields, doc, coll)
                print(f"    BYL -> print_post_queue (arm {q['arm']}, {q['status']})")
                if not args.no_notify:
                    notify_byl(fields, form["name"], lead.get("created_time"),
                               q["arm"], q["address"], needs_review)
            else:
                coll.insert_one(doc)
                if not args.no_notify:
                    notify(fields, form["name"], lead.get("created_time"),
                           lead.get("campaign_name"), lead.get("ad_name"))
                # Five Property Friday: welcome (+ same-day 5 if Friday) via tracked path
                if form["id"] in fpf_send.BUYER_BRIEF_FORMS:
                    try:
                        fpf_send.handle_lead(doc)
                    except Exception as e:
                        print(f"    FPF send failed: {e}", file=sys.stderr)
            # sync into the CRM (email-keyed contact with brief + attribution)
            # — skip out-of-market TEST leads: signal only, must receive NOTHING and
            #   must NOT enter the callable CRM / lead worklist.
            if not doc.get("test_market"):
                try:
                    crm_lead_sync.upsert_lead(coll.database, doc)
                except Exception as e:
                    print(f"    CRM upsert failed: {e}", file=sys.stderr)

    print(f"done — {new_count} new lead(s)")


if __name__ == "__main__":
    main()

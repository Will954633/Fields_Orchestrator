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
import os, sys, argparse, requests
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client  # noqa: E402
import crm_lead_sync  # noqa: E402

PAGE_ID = "889412530933297"
API = "https://graph.facebook.com/v18.0"
TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]

# AYH forms are fulfilled (address -> mini-site -> email) via a Netlify function.
AYH_FORM_IDS = {"1735418400974915"}
FULFIL_URL = "https://fieldsestate.com.au/.netlify/functions/ayh-lead-fulfil"


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


def notify(fields, form_name, created):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    owns = str(fields.get("owns_gc_home", "")).lower() == "yes"
    lines = ["🎯 *New buyer lead*" + ("  — OWNS A GC HOME 🏠" if owns else ""),
             f"_{form_name}_", ""]
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
                   "adset_id": lead.get("adset_id"), "campaign_id": lead.get("campaign_id"),
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
            else:
                coll.insert_one(doc)
                if not args.no_notify:
                    notify(fields, form["name"], lead.get("created_time"))
            # sync into the CRM (email-keyed contact with brief + attribution)
            try:
                crm_lead_sync.upsert_lead(coll.database, doc)
            except Exception as e:
                print(f"    CRM upsert failed: {e}", file=sys.stderr)

    print(f"done — {new_count} new lead(s)")


if __name__ == "__main__":
    main()

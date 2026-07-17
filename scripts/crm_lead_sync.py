#!/usr/bin/env python3
"""
crm_lead_sync.py — Feed FB leads + email engagement into system_monitor.crm_contacts.

Complements crm_sync.py (the PostHog→CRM pipeline). That pipeline only creates
contacts from website visitors keyed by PostHog distinct_id — so FB lead-ad leads,
who never touch the site, get no CRM record. This module upserts contacts BY EMAIL
(merging with any existing PostHog contact that shares the email) with the lead's
brief, ad attribution, tags, and email open/click engagement.

Used by:
  - fb-lead-puller.py       -> upsert_lead() on each new lead
  - email-track.mjs         -> real-time engagement (JS mirror of record_engagement)
  - this script's backfill  -> `python3 scripts/crm_lead_sync.py --backfill`
"""
import os, sys, re, argparse
from datetime import datetime, timezone
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client

BRIEF_KEYS = ["area", "bedrooms", "bathrooms", "timeframe", "owns_gc_home",
              "property_address", "suburb", "selling_timeframe"]
BASE_LEAD_SCORE = 25   # a form submission is a strong intent signal
OPEN_PTS, CLICK_PTS = 3, 10


def _now():
    return datetime.now(timezone.utc).isoformat()


def _slug(url):
    m = re.search(r"/property/([a-z0-9-]+)", url or "")
    return m.group(1) if m else None


def upsert_lead(db, lead):
    """Create/update an email-keyed crm_contacts record from an fb_leads doc."""
    f = lead.get("fields", {}) or {}
    email = (f.get("email") or "").strip().lower()
    if not email:
        return None
    brief = {k: f[k] for k in BRIEF_KEYS if f.get(k) not in (None, "")}
    tags = ["fb_lead"]
    if lead.get("form_name"):
        tags.append(lead["form_name"])
    if str(f.get("owns_gc_home", "")).lower() == "yes":
        tags.append("owns_gc_home")
    if f.get("timeframe"):
        tags.append(f"timeframe:{f['timeframe']}")
    if f.get("area"):
        tags.append(f"area:{f['area']}")
    qual = "FB lead — " + ", ".join(f"{k}={v}" for k, v in brief.items())
    db["crm_contacts"].update_one(
        {"email": email},
        {
            "$setOnInsert": {
                "email": email, "created_at": _now(),
                "first_seen": lead.get("created_time"),
                "status": "lead", "source": "fb_lead_ad",
                "engagement_score": BASE_LEAD_SCORE,
            },
            "$set": {
                "phone": f.get("phone"),
                "updated_at": _now(),
                "last_seen": lead.get("created_time"),
                "lead_brief": brief,
                "qualification_reason": qual,
                "lead_attribution": {
                    "campaign_name": lead.get("campaign_name"),
                    "adset_id": lead.get("adset_id"),
                    "ad_id": lead.get("ad_id"),
                    "platform": lead.get("platform"),
                    "is_organic": lead.get("is_organic"),
                },
            },
            "$addToSet": {"tags": {"$each": [t for t in tags if t]},
                          "fb_lead_ids": lead["_id"]},
        },
        upsert=True,
    )
    return email


def record_engagement(db, email, kind, target, at):
    """Real-time bump on an open/click (called from the JS mirror in email-track.mjs
    for live events; also used by backfill via recompute below)."""
    email = (email or "").strip().lower()
    if not email or kind not in ("open", "click"):
        return
    field = "clicks" if kind == "click" else "opens"
    pts = CLICK_PTS if kind == "click" else OPEN_PTS
    tags = [f"email_{'clicked' if kind == 'click' else 'opened'}"]
    sl = _slug(target)
    if kind == "click" and sl:
        tags.append(f"clicked:{sl}")
    db["crm_contacts"].update_one(
        {"email": email},
        {"$set": {"last_seen": at, "updated_at": _now()},
         "$inc": {f"email_engagement.{field}": 1, "engagement_score": pts},
         "$addToSet": {"tags": {"$each": tags}}},
        upsert=False,
    )


def backfill(db):
    n_leads = sum(1 for lead in db["fb_leads"].find() if upsert_lead(db, lead))
    # Engagement: recompute totals from email_events, SET them (idempotent).
    sends = {s["send_id"]: s for s in db["email_sends"].find()}
    agg = defaultdict(lambda: {"opens": 0, "clicks": 0, "targets": set(), "last": None})
    for e in db["email_events"].find():
        s = sends.get(e.get("send_id"))
        if not s:
            continue
        to = (s.get("to") or "").strip().lower()
        if not to or to == "will@fieldsestate.com.au":
            continue
        a = agg[to]
        a["opens" if e["kind"] == "open" else "clicks"] += 1
        if e["kind"] == "click" and e.get("target"):
            a["targets"].add(e["target"])
        a["last"] = str(e.get("at"))
    n_eng = 0
    for email, a in agg.items():
        tags = []
        if a["opens"]:
            tags.append("email_opened")
        if a["clicks"]:
            tags.append("email_clicked")
        tags += [f"clicked:{_slug(t)}" for t in a["targets"] if _slug(t)]
        upd = {"$set": {"email_engagement": {"opens": a["opens"], "clicks": a["clicks"],
                                             "last_activity": a["last"]}, "last_seen": a["last"]},
               "$inc": {"engagement_score": a["opens"] * OPEN_PTS + a["clicks"] * CLICK_PTS}}
        if tags:
            upd["$addToSet"] = {"tags": {"$each": tags}}
        db["crm_contacts"].update_one({"email": email}, upd, upsert=False)
        n_eng += 1
    print(f"backfill: {n_leads} leads upserted, {n_eng} contacts engagement-synced")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    args = ap.parse_args()
    db = get_client()["system_monitor"]
    if args.backfill:
        backfill(db)
    else:
        print("import upsert_lead/record_engagement, or run with --backfill")

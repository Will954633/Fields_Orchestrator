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
              "property_address", "suburb", "selling_timeframe", "selling_intent"]
# The buyer price-band question. Meta slugifies the form label into the field
# key, so the exact key depends on the question wording — match any key that
# looks like a "price range you're looking in" question rather than pinning one
# literal string (a reworded form would silently drop the band again otherwise).
PRICE_KEY_RE = re.compile(r"price.*(range|looking|budget)|budget", re.I)
BASE_LEAD_SCORE = 25   # a form submission is a strong intent signal
OPEN_PTS, CLICK_PTS = 3, 10


def _now():
    return datetime.now(timezone.utc).isoformat()


def parse_price_range(val):
    """Parse an FB price-band answer into (min, max) whole dollars, either bound
    None when open-ended. Handles the slugified shapes Meta emits, e.g.
    '1.3_-_1.6m' -> (1300000, 1600000), 'under_$1m' -> (None, 1000000),
    'over_$2m' -> (2000000, None). Returns (None, None) on anything unparseable."""
    if not val:
        return None, None
    s = str(val).lower().replace("_", " ").replace(",", "")
    # Capture each number with its own trailing unit so mixed bands like
    # "800k - 1m" parse correctly; a unit-less number inherits the last unit seen
    # in the string (e.g. "1.3 - 1.6m" -> both millions).
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*([mk]?)", s)
    matches = [(n, u) for n, u in matches if n]
    if not matches:
        return None, None
    fallback = next((u for _, u in reversed(matches) if u), "")
    def to_dollars(n, u):
        u = u or fallback
        return int(round(float(n) * (1_000_000 if u == "m" else 1_000 if u == "k" else 1)))
    dollars = [to_dollars(n, u) for n, u in matches]
    if any(w in s for w in ("under", "below", "less than", "up to")):
        return None, max(dollars)
    if any(w in s for w in ("over", "above", "more than", "plus", "+")):
        return min(dollars), None
    if len(dollars) >= 2:
        return min(dollars), max(dollars)
    return dollars[0], dollars[0]


def _slug(url):
    m = re.search(r"/property/([a-z0-9-]+)", url or "")
    return m.group(1) if m else None


def upsert_lead(db, lead):
    """Create/update a crm_contacts record from an fb_leads doc.

    Keyed by email when present, else by phone. A phone-only lead used to get NO
    record at all (`if not email: return None`) — which silently dropped every
    name+phone seller lead (Owner Market / Narratives forms capture no email by
    design). It now upserts on `{"phone": ...}` instead so those leads are captured.
    Returns the match value used (email or phone) or None if neither exists / test.
    """
    f = lead.get("fields", {}) or {}
    email = (f.get("email") or "").strip().lower()
    phone = f.get("phone_number") or f.get("phone")
    # Out-of-market copy-test leads get NO CRM record at all — that is the design
    # (Will, 2026-07-28: they receive nothing post-submit). Guard added 2026-08-20;
    # without it --backfill happily manufactures contacts for Brisbane test leads.
    if lead.get("is_test") or lead.get("test_market"):
        return None
    if not email and not phone:
        return None
    # A seller ad (Owner Market / SMS-link forms) collects the owner's own address.
    # That is the single most valuable field a seller lead can give us and it was
    # being dropped on the floor — capture it as the person's property_address.
    home_address = (f.get("home_address") or f.get("property_address") or "").strip()
    brief = {k: f[k] for k in BRIEF_KEYS if f.get(k) not in (None, "")}
    if home_address:
        brief["home_address"] = home_address
    # Buyer price band. The form key is a slug of the question label; find it by
    # shape, keep the raw answer, and derive structured min/max dollars so the
    # personalised link can filter the feed to their budget.
    price_raw = next((f[k] for k in f
                      if PRICE_KEY_RE.search(k) and f.get(k) not in (None, "")), None)
    if price_raw:
        pmin, pmax = parse_price_range(price_raw)
        brief["price_range"] = price_raw
        if pmin is not None:
            brief["price_min"] = pmin
        if pmax is not None:
            brief["price_max"] = pmax
    tags = ["fb_lead"]
    if lead.get("form_name"):
        tags.append(lead["form_name"])
    if str(f.get("owns_gc_home", "")).lower() == "yes":
        tags.append("owns_gc_home")
    if home_address:
        tags.append("gave_home_address")
    if f.get("timeframe"):
        tags.append(f"timeframe:{f['timeframe']}")
    if f.get("area"):
        tags.append(f"area:{f['area']}")
    qual = "FB lead — " + ", ".join(f"{k}={v}" for k, v in brief.items())
    match = {"email": email} if email else {"phone": phone}
    set_fields = {
        # The Meta form field is `phone_number`; `phone` has NEVER existed on a
        # single fb_leads doc. Reading the wrong key wrote None onto every FB
        # contact for a year — and because this is $set, not $setOnInsert, it
        # also wiped any phone the contact had from another source.
        "phone": phone,
        # Same class of omission as the phone: the form captures full_name and
        # nothing ever wrote it, so every FB contact rendered as "(no name)".
        **({"name": f["full_name"]} if f.get("full_name") else {}),
        "updated_at": _now(),
        "last_seen": lead.get("created_time"),
        "lead_brief": brief,
        "qualification_reason": qual,
        "lead_attribution": {
            "campaign_name": lead.get("campaign_name"),
            # The SPECIFIC ad — the field Will needs to know which creative pulled
            # the lead. Was never stored before; only the campaign was.
            "ad_name": lead.get("ad_name"),
            "adset_id": lead.get("adset_id"),
            "adset_name": lead.get("adset_name"),
            "ad_id": lead.get("ad_id"),
            "form_name": lead.get("form_name"),
            "platform": lead.get("platform"),
            "is_organic": lead.get("is_organic"),
        },
    }
    if home_address:
        set_fields["property_address"] = home_address
    db["crm_contacts"].update_one(
        match,
        {
            "$setOnInsert": {
                # phone lives in $set (it must update existing records too), so it
                # must NOT also appear here or Mongo rejects the conflicting path.
                **({"email": email} if email else {}), "created_at": _now(),
                "first_seen": lead.get("created_time"),
                "status": "lead", "source": "fb_lead_ad",
                "engagement_score": BASE_LEAD_SCORE,
            },
            "$set": set_fields,
            "$addToSet": {"tags": {"$each": [t for t in tags if t]},
                          "fb_lead_ids": lead["_id"]},
        },
        upsert=True,
    )
    return email or phone


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

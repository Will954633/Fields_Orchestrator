#!/usr/bin/env python3
"""
messenger_leads_sync.py — pull the Facebook Page Messenger inbox into crm_contacts.

THE GAP THIS CLOSES
-------------------
People who message the Page (Fields Real Estate) directly were captured NOWHERE. The
Messenger webhook (netlify/functions/messenger-webhook.mjs) only logs `m.me/?ref=<slug>`
ad-click *referrals*, and even that collection (system_monitor.messenger_leads) had never
been created — a plain "hi, is this place still for sale?" fell straight through. So real,
warm, reachable leads (Wayne Ineson, David Armstrong, Rochelle Collins, ...) existed only
in the Meta inbox and never reached the Live Leads Tracker. Found 2026-09-04 when Will
asked why Messenger leads weren't on the Priority tab.

WHAT IT DOES
-----------
Reads Page conversations via the Graph API (Page token derived from the long-lived
FACEBOOK_ADS_TOKEN system-user token) and upserts each into system_monitor.crm_contacts
keyed by `messenger_psid`. A Messenger lead has a name + Page-Scoped ID but no phone/email,
so it is reachable via Messenger only: `follow_up_channel="messenger"`, and a one-click
thread link is stored so Will can reply from the Priority tab.

These contacts have no posthog id and no email/phone, so crm_sync's PostHog replace_one
never matches them — they persist untouched between runs (same reason FB-lead-ad contacts
survive).

Rule 7 / 7b: self-registers a heartbeat; the zero-output path (conversations pulled but
nothing upserted) raises rather than silently reporting success.

Usage:
  python3 scripts/messenger_leads_sync.py --dry-run
  python3 scripts/messenger_leads_sync.py
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv                       # noqa: E402
load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client                     # noqa: E402
from job_status import job_run                       # noqa: E402

PAGE_ID = "889412530933297"
GRAPH = "https://graph.facebook.com/v21.0"
# Deactivated / unreachable accounts show as "Facebook user" — their PSID can't be
# messaged, so they are not leads. Everything with a real display name is kept and
# triaged by Will on the sheet (even a "this looks like a scam" reply is a real person).
SKIP_NAMES = {"facebook user"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=45) as r:
        return json.load(r)


def page_token() -> str:
    tok = os.environ.get("FACEBOOK_ADS_TOKEN")
    if not tok:
        raise RuntimeError("FACEBOOK_ADS_TOKEN not set")
    data = _get(f"{GRAPH}/{PAGE_ID}?fields=access_token&access_token={urllib.parse.quote(tok)}")
    pt = data.get("access_token")
    if not pt:
        raise RuntimeError(f"could not derive Page token: {data}")
    return pt


def fetch_conversations(ptoken: str) -> list[dict]:
    """All conversations with the last few messages, following pagination."""
    fields = ("participants,updated_time,message_count,snippet,"
              "messages.limit(6){message,from,created_time}")
    url = (f"{GRAPH}/{PAGE_ID}/conversations?fields={urllib.parse.quote(fields)}"
           f"&limit=100&access_token={urllib.parse.quote(ptoken)}")
    out: list[dict] = []
    while url:
        data = _get(url)
        out.extend(data.get("data", []))
        url = (data.get("paging") or {}).get("next")
    return out


def parse_conversation(conv: dict) -> dict | None:
    """Reduce a Graph conversation to the contact facts we store, or None to skip."""
    parts = (conv.get("participants") or {}).get("data", [])
    other = next((p for p in parts if p.get("id") != PAGE_ID), None)
    if not other:
        return None
    name = (other.get("name") or "").strip()
    psid = other.get("id")
    if not psid or name.lower() in SKIP_NAMES:
        return None

    msgs = (conv.get("messages") or {}).get("data", [])
    # Messages come newest-first. Find the most recent INBOUND (from the lead) one —
    # that, not our outbound reply, is the real "last heard from them" timestamp.
    last_inbound_at = None
    last_inbound_text = None
    for m in msgs:
        if (m.get("from") or {}).get("id") != PAGE_ID:
            last_inbound_at = m.get("created_time")
            last_inbound_text = m.get("message")
            break
    # Whether they have EVER sent us a message (vs. a thread we opened) — a thread with
    # zero inbound messages is us cold-messaging them, not an inbound lead.
    has_inbound = any((m.get("from") or {}).get("id") != PAGE_ID for m in msgs)

    return {
        "psid": psid,
        "name": name,
        "updated_time": conv.get("updated_time"),
        "message_count": conv.get("message_count"),
        "snippet": conv.get("snippet"),
        "last_inbound_at": last_inbound_at,
        "last_inbound_text": last_inbound_text,
        "has_inbound": has_inbound,
    }


def thread_link(psid: str) -> str:
    # Opens the conversation in the Page inbox for a logged-in Page admin.
    return f"https://www.facebook.com/{PAGE_ID}/inbox/{psid}"


def _norm_name(n: str) -> str:
    return " ".join((n or "").lower().split())


def find_existing_by_name(db, name: str):
    """A Messenger participant often ALSO filled in a lead-ad form, so a contactable
    contact (real phone/email) for the same person may already exist. If EXACTLY ONE
    such contact shares this normalised name, return it so we merge the thread onto it
    rather than creating a second, contact-less row. Ambiguous (0 or >1) -> None, and we
    keep the Messenger contact separate rather than risk a false merge."""
    nn = _norm_name(name)
    if not nn:
        return None
    matches = [d for d in db.crm_contacts.find(
        {"$or": [{"email": {"$nin": [None, ""]}}, {"phone": {"$nin": [None, ""]}}]},
        {"name": 1})
        if _norm_name(d.get("name")) == nn]
    return matches[0] if len(matches) == 1 else None


def upsert(db, c: dict) -> str:
    messenger = {
        "psid": c["psid"],
        "thread_link": thread_link(c["psid"]),
        "message_count": c.get("message_count"),
        "last_inbound_at": c.get("last_inbound_at"),
        "last_inbound_text": c.get("last_inbound_text"),
        "snippet": c.get("snippet"),
        "has_inbound": c.get("has_inbound"),
    }
    # Merge onto an existing form-lead contact for the same person when unambiguous, so
    # they appear as ONE row carrying both their phone/email AND the Messenger thread.
    existing = find_existing_by_name(db, c["name"])
    if existing is not None:
        db.crm_contacts.update_one(
            {"_id": existing["_id"]},
            {"$set": {"messenger": messenger, "messenger_psid": c["psid"],
                      "updated_at": _now()},
             "$addToSet": {"tags": {"$each": ["messenger", "fb_messenger"]}}})
        return c["psid"]

    set_fields = {
        "name": c["name"],
        "updated_at": _now(),
        "last_seen": c.get("last_inbound_at") or c.get("updated_time"),
        "follow_up_channel": "messenger",
        "contact_preference": "Messenger",
        "qualification_reason": (
            "Facebook Messenger — " + (c.get("last_inbound_text") or c.get("snippet") or
                                       "conversation with the Page")),
        "messenger": messenger,
    }
    db.crm_contacts.update_one(
        {"messenger_psid": c["psid"]},
        {"$setOnInsert": {"created_at": _now(),
                          "first_seen": c.get("updated_time"),
                          "status": "lead", "source": "messenger",
                          "engagement_score": 25},
         "$set": set_fields,
         "$addToSet": {"tags": {"$each": ["messenger", "fb_messenger"]}}},
        upsert=True)
    return c["psid"]


def run(dry_run: bool) -> dict:
    ptoken = page_token()
    convs = fetch_conversations(ptoken)
    parsed = [p for p in (parse_conversation(c) for c in convs) if p]
    # Only ingest conversations where they actually messaged us — a thread we opened with
    # zero replies is not an inbound lead.
    leads = [p for p in parsed if p["has_inbound"]]

    db = get_client()["system_monitor"]
    if dry_run:
        for p in leads:
            print(f"  {p['name']:<24} psid={p['psid']} "
                  f"last_in={str(p.get('last_inbound_at'))[:10]} "
                  f"msg={(p.get('last_inbound_text') or p.get('snippet') or '')[:50]!r}")
        return {"conversations": len(convs), "leads": len(leads), "upserted": 0}

    upserted = sum(1 for p in leads if upsert(db, p))
    return {"conversations": len(convs), "leads": len(leads), "upserted": upserted}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.dry_run:
        print(run(True))
        return 0

    with job_run("messenger_leads_sync", cadence_hours=24,
                 title="Facebook Messenger → CRM") as beat:
        res = run(False)
        beat.metrics = res
        # Rule 7b: we pulled inbound-bearing conversations but wrote none => the upsert
        # path is broken, not an empty inbox. An empty inbox is leads == 0.
        if res["leads"] > 0 and res["upserted"] == 0:
            raise RuntimeError(
                f"{res['leads']} Messenger conversations found but 0 upserted "
                f"into crm_contacts — the sync is silently dropping leads.")
        beat.detail = (f"{res['upserted']} Messenger contacts synced "
                       f"(of {res['leads']} inbound threads, {res['conversations']} total)")
        print(beat.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

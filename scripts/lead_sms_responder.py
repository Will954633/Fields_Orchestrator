#!/usr/bin/env python3
"""
lead_sms_responder.py — first-touch SMS to new property-narrative Instant Form leads.

Flow: fb-lead-puller.py captures leads into system_monitor.fb_leads (existing, scheduled).
This reads leads from our 4 narrative forms that haven't had a first SMS yet, sends a
per-narrative, consented, compliance-guarded first SMS via JustCall, marks the lead, and
logs it. The lead consented by submitting the form asking for the breakdown, so this is
NOT cold contact — but every message identifies Fields and offers STOP (Spam Act 2003).

Replies land in the JustCall inbox (native two-way) — Will handles the conversation from
the snippet sheet. This script only owns the FIRST touch.

SAFE BY DEFAULT: prints what it would send. Use --send to actually send.

Usage:
    python3 scripts/lead_sms_responder.py                 # DRY-RUN (prints, no send)
    python3 scripts/lead_sms_responder.py --send          # live send to new leads
    python3 scripts/lead_sms_responder.py --test +61XXXXXXXXX   # one test SMS to a number
    python3 scripts/lead_sms_responder.py --send --limit 1

Compliance: no advice, no "buyer's agent", no predictions; factual figures only;
conjunction/no-buyer-fee framing; sender identified; STOP offered. (CLAUDE.md rule 5.)
"""
import os, sys, argparse, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_env():
    from dotenv import load_dotenv
    load_dotenv("/home/fields/Fields_Orchestrator/.env", override=False)

BASE = "https://api.justcall.io/v2.1"

# form_id -> narrative first-SMS template. {first} = lead first name.
# Figures are FACTUAL (asking price, observed reduction, scarcity count) — the valuation
# dollar figure stays out of the first touch and is delivered conversationally.
TEMPLATES = {
    "3039075966262793": (  # Value Gap — 2 Leafy Close
        "Hi {first}, it's Will from Fields — thanks for enquiring about the southern Gold "
        "Coast home priced below comparable sales. I've pulled the full like-for-like: eight "
        "recent sales against the $1,389,000 asking. Reply YES and I'll send it straight "
        "through. (Reply STOP to opt out.)"),
    "1580988970376517": (  # Price Reduction — 4 Yerrecoin Pl
        "Hi {first}, it's Will from Fields — re the home that's come down $164,000 since March "
        "(now $1,585,000). I can send the full price history and how it compares to nearby "
        "sales. Want it? Reply YES. (Reply STOP to opt out.)"),
    "1010229908733472": (  # Scarcity — 12 Sittella Cr
        "Hi {first}, it's Will from Fields — re the homes with 600m2+ land, a pool and a "
        "walkable school (only nine for sale right now). Tell me your must-haves and I'll send "
        "the ones that fit. (Reply STOP to opt out.)"),
    "942432315543625": (  # Nearby Sold — 11 Belmore Cl
        "Hi {first}, it's Will from Fields — re the home asking $1,275,000 where a smaller "
        "place nearby sold for $310,000 more earlier this year. I can send the side-by-side. "
        "Reply YES. (Reply STOP to opt out.)"),
}


def jc_auth():
    key = os.environ.get("JUSTCALL_API_KEY"); sec = os.environ.get("JUSTCALL_API_SECRET")
    if not key or not sec:
        raise RuntimeError("JUSTCALL_API_KEY / JUSTCALL_API_SECRET missing from .env")
    return f"{key}:{sec}"  # raw colon-separated, per shipped justcall-sms.mjs


def send_sms(to, body):
    num = os.environ.get("JUSTCALL_SMS_NUMBER")
    if not num:
        raise RuntimeError("JUSTCALL_SMS_NUMBER missing from .env")
    r = requests.post(f"{BASE}/texts/new",
                      headers={"Authorization": jc_auth(), "Accept": "application/json",
                               "Content-Type": "application/json"},
                      json={"justcall_number": num, "contact_number": to, "body": body},
                      timeout=30)
    ok = r.status_code < 300
    return ok, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


def first_name(full):
    return (full or "").strip().split(" ")[0] or "there"


def eligible_leads(db, limit):
    q = {"form_id": {"$in": list(TEMPLATES)}, "sms_first_sent": {"$exists": False}}
    return list(db.fb_leads.find(q).sort("created_time", 1).limit(limit))


def lead_phone(doc):
    # fb-lead-puller stores field_data under 'fields'; be tolerant of shape
    f = doc.get("fields") or {}
    if isinstance(f, dict):
        return f.get("phone_number") or f.get("phone") or doc.get("phone_number")
    if isinstance(f, list):
        m = {x.get("name"): (x.get("values") or [""])[0] for x in f}
        return m.get("phone_number") or m.get("phone")
    return doc.get("phone_number")


def lead_name(doc):
    f = doc.get("fields") or {}
    if isinstance(f, dict):
        return f.get("full_name") or f.get("name")
    if isinstance(f, list):
        m = {x.get("name"): (x.get("values") or [""])[0] for x in f}
        return m.get("full_name") or m.get("name")
    return doc.get("full_name")


def run(send, limit, test_number):
    load_env()
    from shared.db import get_client
    db = get_client()["system_monitor"]

    if test_number:
        body = TEMPLATES["3039075966262793"].format(first="there")
        print(f"[TEST] -> {test_number}\n  {body}\n")
        if send:
            ok, resp = send_sms(test_number, body)
            print("  sent:", ok, str(resp)[:200])
        return {"processed": 1, "sent": 1 if send else 0, "failed": 0}

    leads = eligible_leads(db, limit)
    print(f"eligible new narrative leads without a first SMS: {len(leads)}")
    sent = failed = 0
    for d in leads:
        phone = lead_phone(d); name = lead_name(d)
        body = TEMPLATES[d["form_id"]].format(first=first_name(name))
        print(f"\n[{d.get('form_name','?')}] {name} {phone}\n  {body}")
        if not send:
            continue
        if not phone:
            print("  SKIP: no phone"); failed += 1; continue
        ok, resp = send_sms(phone, body)
        if ok:
            db.fb_leads.update_one({"_id": d["_id"]}, {"$set": {
                "sms_first_sent": datetime.now(timezone.utc).isoformat(),
                "sms_first_body": body}})
            db.lead_sms_log.insert_one({"lead_id": d.get("lead_id"), "phone": phone,
                "form_id": d["form_id"], "form_name": d.get("form_name"), "body": body,
                "direction": "out", "channel": "sms",
                "created_at": datetime.now(timezone.utc).isoformat()})
            print("  SENT"); sent += 1
        else:
            print("  FAILED:", str(resp)[:200]); failed += 1
    return {"processed": len(leads), "sent": sent, "failed": failed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually send (default: dry-run)")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--test", dest="test_number", help="send one test SMS to this number")
    args = ap.parse_args()

    if not args.send:
        run(False, args.limit, args.test_number)  # dry-run: no heartbeat, no writes
        return

    # live mode self-reports (rule 7) and asserts an outcome (rule 7b)
    from job_status import job_run
    with job_run("lead_sms_responder", cadence_hours=1,
                 title="Lead first-touch SMS (JustCall)") as beat:
        r = run(True, args.limit, args.test_number)
        beat.metrics = r
        beat.detail = f"{r['sent']} sent, {r['failed']} failed, {r['processed']} eligible"
        if r["processed"] > 0 and r["sent"] == 0:
            raise RuntimeError(f"had {r['processed']} eligible leads but sent 0 "
                               f"({r['failed']} failed) — JustCall send path is broken")


if __name__ == "__main__":
    main()

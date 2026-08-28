#!/usr/bin/env python3
"""
reel3_evidence_sms.py — text each /your-home-evidence landing lead their off-market link.

Flow: the Reel3 "Trust Test" click-to-site ad sends viewers to
https://fieldsestate.com.au/your-home-evidence . That page resolves the typed address to
its /off-market/<slug> report (via analyse-your-home-submit), shows an instant home card,
captures name + phone, and POSTs to /api/campaign-lead (system_monitor.campaign_leads) with
source="fb_reel3_evidence" and the minted property_slug. This poller reads those leads and
texts each person the private /off-market/<slug> link via JustCall — then marks + logs it.

Unlike owner_market_sms.py we do NOT re-resolve: the page already minted the slug and stored
it on the lead. When property_slug is null (address couldn't be enriched, or the home is
currently listed) we send an acknowledgement and flag needs_manual so Will finishes it by
hand (per the 2026-08-28 product decision).

The lead consented on the page ("you agree to receive one text… reply STOP"), so this is NOT
cold contact; every message identifies Fields and offers STOP (Spam Act 2003). No $ figure in
the SMS; the linked page carries the methodology + confidence disclaimer (CLAUDE.md Rule 5).

SAFE BY DEFAULT: dry-run (prints what it would send) unless --send.

Usage:
  python3 reel3_evidence_sms.py                   # DRY-RUN (print, no send)
  python3 reel3_evidence_sms.py --send            # live: text each new lead
  python3 reel3_evidence_sms.py --test +61XXXXXXXXX   # one test SMS
"""
import os, sys, re, argparse
from datetime import datetime, timezone

ROOT = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# reuse the proven JustCall sender + name helper from the narrative responder
from lead_sms_responder import send_sms, first_name, load_env  # noqa: E402

SITE = "https://fieldsestate.com.au"
SOURCE = "fb_reel3_evidence"


def e164_au(raw):
    """Normalise a typed AU mobile to E.164 (+61…). Returns None if implausible."""
    if not raw:
        return None
    d = re.sub(r"[^\d+]", "", str(raw))
    if d.startswith("+"):
        return d if len(d) >= 11 else None
    d = re.sub(r"\D", "", d)
    if d.startswith("0"):          # 0412345678 -> +61412345678
        d = d[1:]
    if d.startswith("61"):         # already country-coded without +
        return "+" + d
    if len(d) == 9 and d.startswith("4"):   # 412345678
        return "+61" + d
    if len(d) == 10 and d.startswith("04"):
        return "+61" + d[1:]
    return ("+61" + d) if 8 <= len(d) <= 12 else None


def build_body(name, slug):
    first = first_name(name)
    if slug:
        return (f"Hi {first}, it's Will from Fields. Here's the comparable-sales evidence we "
                f"prepared for your home: {SITE}/off-market/{slug} - the recent sales behind "
                f"its value, where it sits locally, and the signals we're watching. "
                f"Reply STOP to opt out.")
    # no slug -> address couldn't be enriched / currently listed: acknowledge, human finishes
    return (f"Hi {first}, it's Will from Fields - thanks for asking to see the evidence behind "
            f"your home's value. I'm finalising your private link and will text it through "
            f"shortly. Reply STOP to opt out.")


def eligible(db, limit):
    return list(db.campaign_leads.find(
        {"source": SOURCE, "reel3_sms_sent": {"$exists": False}}
    ).sort("created_at", 1).limit(limit))


def process(db, send, limit):
    leads = eligible(db, limit)
    print(f"eligible Reel3-evidence leads without an SMS: {len(leads)}")
    sent = failed = manual = 0
    for d in leads:
        name = d.get("name")
        slug = d.get("property_slug")
        phone = e164_au(d.get("phone"))
        body = build_body(name, slug)
        if not slug:
            manual += 1
        print(f"\n{name} {d.get('phone')} -> {phone}\n  slug: {slug or '(none, manual)'}\n  {body}")
        if not send:
            continue
        if not phone:
            print("  SKIP: no valid phone"); failed += 1; continue
        ok, resp = send_sms(phone, body)
        if ok:
            db.campaign_leads.update_one({"_id": d["_id"]}, {"$set": {
                "reel3_sms_sent": datetime.now(timezone.utc).isoformat(),
                "reel3_sms_link": f"{SITE}/off-market/{slug}" if slug else None,
                "reel3_sms_body": body,
                "reel3_needs_manual_link": not slug}})
            db.lead_sms_log.insert_one({"lead_id": str(d.get("_id")), "phone": phone,
                "source": SOURCE, "name": name, "body": body, "direction": "out",
                "channel": "sms", "reel3_slug": slug,
                "created_at": datetime.now(timezone.utc).isoformat()})
            print("  SENT"); sent += 1
        else:
            print("  FAILED:", str(resp)[:160]); failed += 1
    return {"processed": len(leads), "sent": sent, "failed": failed, "manual": manual}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually send (default dry-run)")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--test", dest="test_number")
    args = ap.parse_args()
    load_env()
    from shared.db import get_client
    db = get_client()["system_monitor"]

    if args.test_number:
        body = build_body("Test User", "10-heidelberg-circuit-robina")
        print(f"[TEST] -> {args.test_number} (normalised {e164_au(args.test_number)})\n  {body}")
        if args.send:
            ok, resp = send_sms(e164_au(args.test_number), body)
            print("  sent:", ok, str(resp)[:200])
        return

    if not args.send:
        print("\nDRY-RUN:", process(db, send=False, limit=args.limit)); return

    # live send is an ongoing process -> self-monitor (Rule 7 / 7b)
    from job_status import job_run
    with job_run("reel3_evidence_sms", cadence_hours=1,
                 title="Reel3 /your-home-evidence lead -> SMS off-market link") as beat:
        res = process(db, send=True, limit=args.limit)
        beat.metrics = res
        beat.detail = f"{res['sent']} texted, {res['manual']} manual, {res['failed']} failed"
        # 7b: leads existed but none went out AND some failed -> pipeline broken, not empty
        if res["processed"] > 0 and res["sent"] == 0 and res["failed"] > 0:
            raise RuntimeError(f"had {res['processed']} leads, sent 0, {res['failed']} failed")


if __name__ == "__main__":
    main()

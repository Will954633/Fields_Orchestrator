#!/usr/bin/env python3
"""
find_landing_sms.py — text each /find landing-page lead the link to THEIR home's analysis.

The Owner-Market Facebook ads now land on the website page /find/<suburb> (FindYourHomePage)
instead of a Meta Instant Form. That page mints the /off-market/<slug> client-side and POSTs
{name, phone, address, property_slug, source:"fb_find_landing", consent:true} to
/api/campaign-lead, which stores it in system_monitor.campaign_leads. This poller reads those
leads and texts each one their private link via JustCall — the same delivery the Instant Form
had (see owner_market_sms.py), just sourced from campaign_leads instead of fb_leads.

The homeowner consented on the page ("we'll text you your link… reply STOP"), so this is NOT
cold contact; every message identifies Fields and offers STOP (Spam Act 2003). No $ figure in
the SMS; the linked page carries the methodology + confidence disclaimer (CLAUDE.md Rule 5).

Link resolution: the page already minted the slug, so we prefer the stored property_slug. If
it's absent (needs_manual) we try to resolve the address once more, and otherwise send an
acknowledgement and flag the lead for a human.

SAFE BY DEFAULT: dry-run (resolve + print, no send) unless --send.

Usage:
  python3 find_landing_sms.py                      # DRY-RUN (resolve + print, no send)
  python3 find_landing_sms.py --send               # live: text each new lead
  python3 find_landing_sms.py --test +61XXXXXXXXX  # one test SMS (sample address)
"""
import os, sys, argparse, requests
from datetime import datetime, timezone

ROOT = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# reuse the proven JustCall sender + name helper + env loader
from lead_sms_responder import send_sms, first_name, load_env  # noqa: E402

SUBMIT_URL = "https://fieldsestate.com.au/api/v1/analyse-your-home-submit"
SITE = "https://fieldsestate.com.au"
SOURCE = "fb_find_landing"

# suburb display name inference from the typed address (best-effort, for copy only)
SUBURB_HINTS = [
    ("varsity", "Varsity Lakes"),
    ("burleigh", "Burleigh Waters"),
    ("robina", "Robina"),
]


def suburb_from_address(address):
    a = (address or "").lower()
    for needle, name in SUBURB_HINTS:
        if needle in a:
            return name
    return "the Gold Coast"


def resolve_link(lead):
    """Return (kind, url, note). Prefer the slug the page already minted; fall back to a
    fresh resolve of the typed address. kind: 'analysis' | 'listed' | 'unresolved'."""
    slug = lead.get("property_slug")
    if slug:
        return "analysis", f"{SITE}/off-market/{slug}", "stored slug"

    address = lead.get("address")
    if not address:
        return "unresolved", None, "no slug and no address"
    try:
        r = requests.post(SUBMIT_URL, headers={"Content-Type": "application/json"}, timeout=30,
                          json={"address": address, "source": SOURCE, "claim": True})
        if r.status_code >= 400:
            return "unresolved", None, f"http {r.status_code}"
        d = r.json()
    except Exception as e:
        return "unresolved", None, str(e)[:80]
    if d.get("is_currently_listed") and d.get("listed_property_id"):
        return "listed", f"{SITE}/property/{d['listed_property_id']}", "currently listed"
    if d.get("slug"):
        return "analysis", f"{SITE}/off-market/{d['slug']}", d.get("state", "")
    return "unresolved", None, "no slug returned"


def build_body(name, address, suburb_name, kind, url):
    first = first_name(name or "")
    if kind == "analysis":
        return (f"Hi {first}, it's Will from Fields. Here's the analysis we prepared for "
                f"{address}: {url} - your home's estimated value over 18 months, where it sits "
                f"in {suburb_name}, and the market signals we're watching. Reply STOP to opt out.")
    if kind == "listed":
        return (f"Hi {first}, it's Will from Fields - thanks for requesting your home's analysis. "
                f"{address} looks to be on the market right now; here's what we have for it: {url}. "
                f"Reply STOP to opt out.")
    return (f"Hi {first}, it's Will from Fields - thanks for requesting the analysis for "
            f"{address}. I'm finalising your link and will text it through shortly. "
            f"Reply STOP to opt out.")


def eligible(db, limit):
    return list(db.campaign_leads.find(
        {"source": SOURCE, "consent": True, "find_sms_sent": {"$exists": False}}
    ).sort("created_at_date", 1).limit(limit))


def process(db, send, limit):
    leads = eligible(db, limit)
    print(f"eligible /find landing leads without an SMS: {len(leads)}")
    sent = failed = unresolved = 0
    for d in leads:
        address = d.get("address") or ""
        phone = d.get("phone")
        name = d.get("name")
        suburb_name = suburb_from_address(address)
        kind, url, note = resolve_link(d)
        if kind == "unresolved":
            unresolved += 1
        body = build_body(name, address, suburb_name, kind, url)
        print(f"\n[{suburb_name}] {name} {phone}\n  addr: {address}\n  -> {kind} ({note}) {url or ''}\n  {body}")
        if not send:
            continue
        if not phone:
            print("  SKIP: no phone"); failed += 1; continue
        try:
            ok, resp = send_sms(phone, body)
        except Exception as e:
            ok, resp = False, str(e)
        if ok:
            db.campaign_leads.update_one({"_id": d["_id"]}, {"$set": {
                "find_sms_sent": datetime.now(timezone.utc).isoformat(),
                "find_sms_kind": kind, "find_sms_link": url, "find_sms_body": body,
                "find_needs_manual_link": kind == "unresolved"}})
            db.lead_sms_log.insert_one({"lead_id": str(d.get("_id")), "phone": phone,
                "source": SOURCE, "body": body, "direction": "out", "channel": "sms",
                "find_kind": kind, "find_link": url,
                "created_at": datetime.now(timezone.utc).isoformat()})
            print("  SENT"); sent += 1
        else:
            print("  FAILED:", str(resp)[:160]); failed += 1
    return {"processed": len(leads), "sent": sent, "failed": failed, "unresolved": unresolved}


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
        sample = {"property_slug": None, "address": "10 Heidelberg Circuit, Robina", "name": "Test User"}
        kind, url, note = resolve_link(sample)
        body = build_body("Test User", sample["address"], "Robina", kind, url)
        print(f"[TEST] resolve={kind} {url}\n-> {args.test_number}\n  {body}")
        if args.send:
            ok, resp = send_sms(args.test_number, body); print("  sent:", ok, str(resp)[:200])
        return

    if not args.send:
        res = process(db, send=False, limit=args.limit)
        print("\nDRY-RUN:", res); return

    # live send is an ongoing process -> self-monitor (Rule 7 / 7b)
    from job_status import job_run
    with job_run("find_landing_sms", cadence_hours=1,
                 title="/find landing lead -> SMS link") as beat:
        res = process(db, send=True, limit=args.limit)
        beat.metrics = res
        beat.detail = f"{res['sent']} texted, {res['unresolved']} unresolved, {res['failed']} failed"
        # 7b: leads existed but none went out AND some failed -> pipeline broken, not empty
        if res["processed"] > 0 and res["sent"] == 0 and res["failed"] > 0:
            raise RuntimeError(f"had {res['processed']} leads, sent 0, {res['failed']} failed")


if __name__ == "__main__":
    main()

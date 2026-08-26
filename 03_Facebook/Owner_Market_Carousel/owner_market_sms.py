#!/usr/bin/env python3
"""
owner_market_sms.py — text each Owner-Market FORM lead the link to THEIR home's analysis.

Flow: fb-lead-puller.py captures Instant-Form leads into system_monitor.fb_leads (existing,
scheduled). This reads the 3 Owner-Market forms' new leads, resolves the submitted address
to its /off-market/<slug> page (same resolver the landing page uses), and texts that link
via JustCall — then marks the lead and logs it.

The lead consented on the form ("we'll text you the link… reply STOP"), so this is NOT cold
contact; every message identifies Fields and offers STOP (Spam Act 2003). No $ figure in the
SMS; the linked page carries the methodology + confidence disclaimer (CLAUDE.md Rule 5).

SAFE BY DEFAULT: dry-run (prints what it would send + resolves links) unless --send.

Usage:
  python3 owner_market_sms.py                    # DRY-RUN (resolve + print, no send)
  python3 owner_market_sms.py --send             # live: resolve + text each new lead
  python3 owner_market_sms.py --test +61XXXXXXXXX  # one test SMS (uses a sample address)
"""
import os, sys, json, argparse, requests
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# reuse the proven JustCall sender + name helper from the narrative responder
from lead_sms_responder import send_sms, first_name, load_env  # noqa: E402

SUBMIT_URL = "https://fieldsestate.com.au/api/v1/analyse-your-home-submit"
SITE = "https://fieldsestate.com.au"

# form_id -> (suburb_key, suburb display, slug). Loaded from forms_ids.json at runtime,
# but pinned here as the source of truth in case the file moves.
def form_map():
    ids = json.load(open(os.path.join(HERE, "forms_ids.json")))
    names = {"robina": ("robina", "Robina"), "varsity": ("varsity_lakes", "Varsity Lakes"),
             "burleigh": ("burleigh_waters", "Burleigh Waters")}
    return {o["form_id"]: names[sub] for sub, o in ids["arms"].items()}

def lead_field(doc, *keys):
    f = doc.get("fields") or {}
    if isinstance(f, dict):
        for k in keys:
            if f.get(k): return f[k]
    elif isinstance(f, list):
        m = {x.get("name"): (x.get("values") or [""])[0] for x in f}
        for k in keys:
            if m.get(k): return m[k]
    return None

def resolve_link(address, suburb_key, suburb_name):
    """Resolve a raw typed address to its analysis link. Returns (kind, url, note).
    kind: 'analysis' | 'listed' | 'unresolved'. Endpoint needs BOTH suburb (display)
    and suburb_key."""
    try:
        r = requests.post(SUBMIT_URL, headers={"Content-Type": "application/json"}, timeout=30,
                          json={"address": address, "suburb": suburb_name, "suburb_key": suburb_key,
                                "source": "fb_form_lead", "claim": True})
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
    first = first_name(name)
    if kind == "analysis":
        return (f"Hi {first}, it's Will from Fields. Here's the analysis we prepared for "
                f"{address}: {url} - your home's estimated value over 18 months, where it sits "
                f"in {suburb_name}, and the signals we're watching. Reply STOP to opt out.")
    if kind == "listed":
        return (f"Hi {first}, it's Will from Fields - thanks for requesting your {suburb_name} "
                f"home's analysis. {address} looks to be on the market right now; here's what "
                f"we have for it: {url}. Reply STOP to opt out.")
    # unresolved fallback — we still acknowledge; a human finishes the link
    return (f"Hi {first}, it's Will from Fields - thanks for requesting the analysis for "
            f"{address}. I'm finalising your link and will text it through shortly. "
            f"Reply STOP to opt out.")

def eligible(db, forms, limit):
    return list(db.fb_leads.find(
        {"form_id": {"$in": list(forms)}, "om_sms_sent": {"$exists": False}}
    ).sort("created_time", 1).limit(limit))

def process(db, forms, send, limit):
    leads = eligible(db, forms, limit)
    print(f"eligible Owner-Market form leads without an SMS: {len(leads)}")
    sent = failed = unresolved = 0
    for d in leads:
        suburb_key, suburb_name = forms[d["form_id"]]
        address = lead_field(d, "home_address", "address", "street_address")
        phone = lead_field(d, "phone_number", "phone")
        name = lead_field(d, "full_name", "name")
        if not address:
            print(f"  SKIP {name}: no address in lead"); failed += 1; continue
        kind, url, note = resolve_link(address, suburb_key, suburb_name)
        if kind == "unresolved": unresolved += 1
        body = build_body(name, address, suburb_name, kind, url)
        print(f"\n[{suburb_name}] {name} {phone}\n  addr: {address}\n  -> {kind} ({note}) {url or ''}\n  {body}")
        if not send:
            continue
        if not phone:
            print("  SKIP: no phone"); failed += 1; continue
        ok, resp = send_sms(phone, body)
        if ok:
            db.fb_leads.update_one({"_id": d["_id"]}, {"$set": {
                "om_sms_sent": datetime.now(timezone.utc).isoformat(),
                "om_sms_kind": kind, "om_sms_link": url, "om_sms_body": body,
                "om_needs_manual_link": kind == "unresolved"}})
            db.lead_sms_log.insert_one({"lead_id": d.get("lead_id"), "phone": phone,
                "form_id": d["form_id"], "form_name": d.get("form_name"), "body": body,
                "direction": "out", "channel": "sms", "om_kind": kind, "om_link": url,
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
    forms = form_map()

    if args.test_number:
        kind, url, note = resolve_link("10 Heidelberg Circuit, Robina", "robina", "Robina")
        body = build_body("Test User", "10 Heidelberg Circuit, Robina", "Robina", kind, url)
        print(f"[TEST] resolve={kind} {url}\n-> {args.test_number}\n  {body}")
        if args.send:
            ok, resp = send_sms(args.test_number, body); print("  sent:", ok, str(resp)[:200])
        return

    if not args.send:
        # dry-run: no heartbeat, just resolve + print
        res = process(db, forms, send=False, limit=args.limit)
        print("\nDRY-RUN:", res); return

    # live send is an ongoing process -> self-monitor (Rule 7 / 7b)
    from job_status import job_run
    with job_run("owner_market_sms", cadence_hours=1,
                 title="Owner-Market form lead -> SMS link") as beat:
        res = process(db, forms, send=True, limit=args.limit)
        beat.metrics = res
        beat.detail = f"{res['sent']} texted, {res['unresolved']} unresolved, {res['failed']} failed"
        # 7b: leads existed but none went out AND some failed -> the pipeline is broken, not empty
        if res["processed"] > 0 and res["sent"] == 0 and res["failed"] > 0:
            raise RuntimeError(f"had {res['processed']} leads, sent 0, {res['failed']} failed")

if __name__ == "__main__":
    main()

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
import os, sys, json, re, argparse, requests
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# reuse the proven JustCall sender + name helper from the narrative responder
from lead_sms_responder import send_sms, first_name, load_env  # noqa: E402

SUBMIT_URL = "https://fieldsestate.com.au/api/v1/analyse-your-home-submit"
# Resolves a typed address -> /your-home/<slug> and EMAILS the link via Gmail, with a
# quality gate (won't email an unresolved / "elsewhere on the GC" address). Same endpoint
# the AYH email forms use. We call it for v2 Owner-Market leads that carry an email so the
# "we'll send your link by text AND email" promise on the v2 form is actually kept.
AYH_FULFIL_URL = "https://fieldsestate.com.au/.netlify/functions/ayh-lead-fulfil"
SITE = "https://fieldsestate.com.au"

# form_id -> (suburb_key, suburb display, slug). Loaded from forms_ids.json at runtime,
# but pinned here as the source of truth in case the file moves. Maps BOTH the live v2
# form_id (name+address+phone+EMAIL) AND the legacy_form_id (name+address+phone, pre-email)
# to the same suburb, so leads on either generation resolve. v2 added 2026-08-28 when the
# Owner-Market campaign switched from the website /find leadpage to autofill Instant Forms.
def form_map():
    ids = json.load(open(os.path.join(HERE, "forms_ids.json")))
    names = {"robina": ("robina", "Robina"), "varsity": ("varsity_lakes", "Varsity Lakes"),
             "burleigh": ("burleigh_waters", "Burleigh Waters")}
    m = {}
    for sub, o in ids["arms"].items():
        m[o["form_id"]] = names[sub]
        if o.get("legacy_form_id"):
            m[o["legacy_form_id"]] = names[sub]
    return m


def email_report(address, suburb_key, suburb_name, email, name):
    """Email the analysis link via the AYH fulfilment endpoint (its own quality gate
    decides whether to actually send). Returns (emailed_bool, note)."""
    try:
        r = requests.post(AYH_FULFIL_URL, headers={"Content-Type": "application/json"},
                          timeout=45, json={"address": address, "suburb": suburb_name,
                          "suburb_key": suburb_key, "email": email, "name": name,
                          "source": "owner_market_form_v2"})
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return bool(d.get("emailed")), (d.get("reason") or d.get("slug") or f"http {r.status_code}")
    except Exception as e:
        return False, str(e)[:80]

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

# Street-type words and locality noise we must NOT mistake for the street NAME.
_STREET_TYPES = {
    "ST", "STREET", "RD", "ROAD", "AVE", "AV", "AVENUE", "CT", "CRT", "COURT",
    "CR", "CRES", "CRESCENT", "DR", "DRV", "DRIVE", "PL", "PLACE", "PDE",
    "PARADE", "LN", "LANE", "WAY", "CCT", "CIRCUIT", "CL", "CLOSE", "TCE",
    "TERRACE", "BVD", "BLVD", "BOULEVARD", "ESP", "ESPLANADE", "GR", "GROVE",
    "RISE", "LOOP", "LINK", "MEWS", "QUAY", "PROMENADE", "HIGHWAY", "HWY",
}
_NOISE = {"QLD", "QUEENSLAND", "AUSTRALIA", "AU"}

def _norm_tokens(text):
    """Uppercase alnum tokens, '/' kept as a separator (unit numbers)."""
    return [t for t in re.sub(r"[^A-Za-z0-9/]+", " ", text or "").upper().split() if t]

def _name_variants(tok):
    """'CAMPELLE' <-> 'CAMPELLES'. Typed street names lose/gain a trailing S constantly."""
    v = {tok}
    if tok.endswith("S"):
        v.add(tok[:-1])
    else:
        v.add(tok + "S")
    return v

def resolve_address_locality(db_client, typed, form_suburb_key, form_suburb_name):
    """Find the REAL suburb of a typed address from Gold_Coast.address_search_index.

    The Owner-Market ads are per-suburb, and the old code passed the AD's suburb to the
    resolver regardless of what the person actually typed. Burleigh Waters ads are seen
    by (and answered by) Burleigh Heads owners, so their address could never resolve —
    the search was scoped to the wrong suburb. Measured 2026-08-30: 3 of 4 paid leads
    came back 'unresolved' and 2 of those 3 were sitting in the index verbatim.

    Returns (suburb_key, suburb_name, canonical_address) — falling back to the form's
    own suburb and the typed string when nothing matches, i.e. the previous behaviour.
    """
    tokens = _norm_tokens(typed)
    if not tokens:
        return form_suburb_key, form_suburb_name, typed
    # Street number: first token containing a digit. '2/9' -> '9' (index stores the
    # street number, unit stripped into address only).
    street_no = None
    for t in tokens:
        if any(ch.isdigit() for ch in t):
            street_no = t.split("/")[-1].lstrip("0") or t.split("/")[-1]
            break
    if not street_no:
        return form_suburb_key, form_suburb_name, typed
    words = [t for t in tokens
             if not any(ch.isdigit() for ch in t) and t not in _NOISE]
    cands = set()
    for w in words:
        if w not in _STREET_TYPES:
            cands |= _name_variants(w)
    if not cands:
        return form_suburb_key, form_suburb_name, typed
    try:
        idx = db_client["Gold_Coast"]["address_search_index"]
        rows = list(idx.find({"street_no": street_no,
                              "street_name": {"$in": sorted(cands)}}).limit(60))
    except Exception:
        return form_suburb_key, form_suburb_name, typed
    if not rows:
        return form_suburb_key, form_suburb_name, typed
    typed_set = set(words)

    def score(r):
        s = 0
        # Suburb the person actually wrote beats the suburb the ad was for.
        if set(_norm_tokens(r.get("suburb") or "")) & typed_set:
            s += 4
        if (r.get("street_type") or "") in typed_set:
            s += 2
        if (r.get("street_name") or "") in typed_set:
            s += 2          # exact spelling beats the plural/singular variant
        if r.get("suburb_key") == form_suburb_key:
            s += 1          # weakest tiebreak, not the deciding factor
        return s

    best = max(rows, key=score)
    return (best.get("suburb_key") or form_suburb_key,
            best.get("suburb") or form_suburb_name,
            best.get("address") or typed)

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

def get_or_create_link_token(db, phone=None, email=None):
    """Find this lead's crm_contact (by email, else phone) and return a stable,
    opaque link_token, minting one if absent. The token — never any PII — is what
    we append to the SMS link so lead-link-visit.mjs can bind their on-site session
    back to this contact. Returns None if no contact exists yet (link still works,
    just no identity join)."""
    import uuid
    contact = None
    if email:
        contact = db.crm_contacts.find_one({"email": email.strip().lower()})
    if not contact and phone:
        contact = db.crm_contacts.find_one({"phone": phone})
        if not contact:
            digits = "".join(c for c in phone if c.isdigit())[-9:]
            if digits:
                for cand in db.crm_contacts.find({"phone": {"$ne": None}}):
                    if "".join(c for c in (cand.get("phone") or "") if c.isdigit())[-9:] == digits:
                        contact = cand
                        break
    if not contact:
        return None
    tok = contact.get("link_token")
    if not tok:
        tok = uuid.uuid4().hex
        db.crm_contacts.update_one({"_id": contact["_id"]}, {"$set": {"link_token": tok}})
    return tok


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
    emailed = 0
    for d in leads:
        suburb_key, suburb_name = forms[d["form_id"]]
        address = lead_field(d, "home_address", "address", "street_address")
        phone = lead_field(d, "phone_number", "phone")
        email = lead_field(d, "email", "email_address")
        name = lead_field(d, "full_name", "name")
        if not address:
            print(f"  SKIP {name}: no address in lead"); failed += 1; continue
        # Trust the address the person TYPED over the suburb the ad happened to be for.
        suburb_key, suburb_name, canonical = resolve_address_locality(
            db.client, address, suburb_key, suburb_name)
        if canonical != address:
            print(f"  locality: {address!r} -> {canonical!r} ({suburb_key})")
        kind, url, note = resolve_link(canonical, suburb_key, suburb_name)
        if kind == "unresolved": unresolved += 1
        # Append the identity-join token to the /off-market analysis link (the page
        # that runs phIdentifyLead). Binds their click-through to this lead. Only
        # when actually sending — dry-run must not mint tokens / write to the CRM.
        if send and kind == "analysis" and url:
            tok = get_or_create_link_token(db, phone=phone, email=email)
            if tok:
                url = f"{url}?lead={tok}"
        body = build_body(name, address, suburb_name, kind, url)
        print(f"\n[{suburb_name}] {name} ph={phone} em={email}\n  addr: {address}\n  -> {kind} ({note}) {url or ''}\n  {body}")
        if not send:
            continue
        # A lead is fulfilled if we reach it on EITHER channel. Text (if phone) + email
        # (if email) — the v2 form promises both. Mark processed if either lands so a
        # phone-less-but-email lead isn't retried forever (and vice versa).
        set_fields = {"om_sms_kind": kind, "om_sms_link": url,
                      "om_needs_manual_link": kind == "unresolved"}
        delivered = False
        if phone:
            ok, resp = send_sms(phone, body)
            if ok:
                set_fields.update({"om_sms_sent": datetime.now(timezone.utc).isoformat(),
                                   "om_sms_body": body})
                db.lead_sms_log.insert_one({"lead_id": d.get("lead_id"), "phone": phone,
                    "form_id": d["form_id"], "form_name": d.get("form_name"), "body": body,
                    "direction": "out", "channel": "sms", "om_kind": kind, "om_link": url,
                    "created_at": datetime.now(timezone.utc).isoformat()})
                print("  SMS SENT"); sent += 1; delivered = True
            else:
                print("  SMS FAILED:", str(resp)[:160]); failed += 1
        else:
            print("  no phone — skipping SMS")
        if email:
            eok, enote = email_report(address, suburb_key, suburb_name, email, name)
            if eok:
                set_fields["om_email_sent"] = datetime.now(timezone.utc).isoformat()
                print(f"  EMAIL SENT ({enote})"); emailed += 1; delivered = True
            else:
                print(f"  email not sent ({enote})")
        else:
            print("  no email — skipping email")
        # Mark processed so the lead leaves the eligible set. Use om_sms_sent as the
        # historical gate field; if only email landed (no phone), stamp it too so the
        # lead is not reprocessed every 3 min.
        if delivered and "om_sms_sent" not in set_fields:
            set_fields["om_sms_sent"] = datetime.now(timezone.utc).isoformat()
            set_fields["om_sms_kind"] = "email_only"
        if delivered:
            db.fb_leads.update_one({"_id": d["_id"]}, {"$set": set_fields})
    return {"processed": len(leads), "sent": sent, "emailed": emailed,
            "failed": failed, "unresolved": unresolved}

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
        beat.detail = (f"{res['sent']} texted, {res.get('emailed', 0)} emailed, "
                       f"{res['unresolved']} unresolved, {res['failed']} failed")
        # 7b: leads existed but nothing went out on EITHER channel AND some failed ->
        # the pipeline is broken, not empty.
        if res["processed"] > 0 and res["sent"] == 0 and res.get("emailed", 0) == 0 and res["failed"] > 0:
            raise RuntimeError(f"had {res['processed']} leads, sent 0 SMS / 0 email, {res['failed']} failed")
        # 7b: sending the "I'm finalising your link" holding SMS counts as sent=1, so a
        # batch where EVERY address failed to resolve used to report success. It is not
        # success — we took the lead, promised a link and produced none. Distinguish
        # "no work to do" (processed=0, fine) from "could not do the work".
        if res["processed"] > 0 and res["unresolved"] == res["processed"]:
            raise RuntimeError(
                f"resolved 0 of {res['processed']} addresses to a link; everyone got only "
                f"the holding SMS. Check the locality resolver / address_search_index.")
        # A promise with no consumer is how leads go cold: nothing reads
        # om_needs_manual_link, so surface the backlog on the health board.
        waiting = db.fb_leads.count_documents({"om_needs_manual_link": True})
        beat.metrics = dict(res, awaiting_manual_link=waiting)
        if waiting:
            beat.detail += f" | {waiting} awaiting a manual link"

if __name__ == "__main__":
    main()

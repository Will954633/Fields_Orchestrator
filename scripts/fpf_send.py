#!/usr/bin/env python3
"""
fpf_send.py — Five Property Friday delivery engine.

On a new buyer-brief lead: pick the welcome variant (Friday vs standard vs
needs-suburb), send it, and — if today is Friday and we know their suburb —
send their 5 the same day. Otherwise the 5 go out in the Friday batch.

Budget: the form doesn't capture it, so we fall back to the suburb house median
(the welcome asks them to reply with a real budget → updated 5 next run).

All sends go through the tracked email path (open/click tracking + monitoring
copy to Will + CRM engagement). Nothing is auto-named — we greet "Hi there"
because FB emails carry no reliable first name.

Usage:
  python3 scripts/fpf_send.py --lead-id <id> [--dry-run]   # handle one lead
  python3 scripts/fpf_send.py --friday-batch [--dry-run]    # send all active subs their 5
"""
import os, sys, re, json, argparse, requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client
import five_property_friday as fpf

SEND_URL = "https://fieldsestate.com.au/.netlify/functions/send-tracked-email"
SECRET = os.environ.get("EMAIL_SEND_SECRET", "")
AEST = ZoneInfo("Australia/Brisbane")
BUYER_BRIEF_FORMS = {"914858877560109", "1562508485581939"}  # v1, v2(+phone)

AREA_TO_SUBURBS = {
    "robina": ["robina"], "burleigh_waters": ["burleigh_waters"], "varsity_lakes": ["varsity_lakes"],
    "open_to_all_three": ["robina", "burleigh_waters", "varsity_lakes"],
}
SUBURB_LABEL = {"robina": "Robina", "burleigh_waters": "Burleigh Waters", "varsity_lakes": "Varsity Lakes"}


def is_friday():
    return datetime.now(AEST).weekday() == 4


def suburb_median(suburb):
    d = get_client()["Gold_Coast"]["suburb_median_prices"].find_one({"suburb": suburb, "property_type": "House"})
    data = sorted((d or {}).get("data", []), key=lambda x: x.get("date", ""))
    return data[-1]["median"] if data else None


def budget_for(suburbs):
    meds = [m for m in (suburb_median(s) for s in suburbs) if m]
    return round(sum(meds) / len(meds)) if meds else None


def target_suburbs(area):
    return AREA_TO_SUBURBS.get((area or "").lower())   # None if elsewhere/unknown


def _int(v):
    m = re.sub(r"\D", "", str(v or ""))
    return int(m) if m else 0


# ---------------- HTML ----------------
def _wrap(inner):
    return (f'<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#2c3e50;'
            f'line-height:1.6;max-width:600px;margin:0 auto;padding:8px 4px">{inner}'
            f'<p style="color:#8a8a8a;font-size:12px;margin-top:28px">Fields Real Estate · Smarter with data · '
            f'fieldsestate.com.au<br>You asked us for a Gold Coast property shortlist. Reply STOP to opt out.</p></div>')


def welcome_html(suburb_label, budget, kind):
    if kind == "needs_suburb":
        body = ("<p>Hi there,</p><p>Thanks for signing up.</p>"
                "<p>Each week we send a short, curated list of the Gold Coast homes worth your attention — with the "
                "comparable-sales data behind each. To make yours genuinely useful, one quick thing: <b>you mentioned "
                "you're open across the Gold Coast, so which suburb or two are you most focused on — and roughly what "
                "budget?</b> Just hit reply; a sentence is plenty.</p><p>No rush at all — once you point us at an area, "
                "we'll start sending you a tailored five.</p><p>— Will, Fields</p>")
    elif kind == "friday":
        body = (f"<p>Hi there,</p><p>Thanks for signing up — and good timing: Friday is when we send our shortlists, "
                f"so <b>yours is coming through today.</b></p><p>Each Friday we go through every home for sale in "
                f"{suburb_label} and send you the five worth your attention — not everything, just the ones genuinely "
                f"worth a look, with the comparable-sales data behind each.</p><p>For today's list we've started from "
                f"the <b>{suburb_label} median (around ${budget:,})</b> as a guide. Reply with your budget range and any "
                f"must-have or deal-breaker, and we'll send you an <b>updated five straight away</b>.</p>"
                f"<p>Your five are in the next email.</p><p>— Will, Fields</p>")
    else:  # standard
        body = (f"<p>Hi there,</p><p>Thanks for signing up. Your first shortlist lands <b>this Friday.</b></p>"
                f"<p>Each Friday we go through every home for sale in {suburb_label} and send you the five worth your "
                f"attention — with the comparable-sales data behind each.</p><p>To make that first one useful, one quick "
                f"thing — <b>what's your budget range, and any must-have or deal-breaker?</b> Just hit reply. If we don't "
                f"hear back, we'll start from the {suburb_label} median and refine once you tell us more.</p>"
                f"<p>— Will, Fields</p>")
    return _wrap(body)


def shortlist_html(suburb_label, picks):
    rows = [f"<p>Hi there,</p><p><b>This week in {suburb_label}:</b> here are the five worth your time.</p>"]
    for i, (role, c) in enumerate(picks, 1):
        slug = c.get("url_slug") or re.sub(r",.*", "", c["address"]).strip().lower().replace(" ", "-")
        url = f"https://fieldsestate.com.au/property/{slug}"
        rows.append(
            f'<div style="margin:0 0 20px;padding-bottom:16px;border-bottom:1px solid #eee">'
            f'<p style="margin:0 0 4px"><b>{i}. {role} — {c["address"]}</b><br>'
            f'<span style="color:#666">{c["beds"]} bed / {c["baths"]} bath · asking {c["price_text"]}</span></p>'
            f'<p style="margin:0 0 6px">{fpf.take_line(role, c)}</p>'
            f'<p style="margin:0"><a href="{url}" style="color:#b87333">See the full analysis →</a></p></div>')
    rows.append("<p>Reply and tell us which to dig into — or send your budget and must-haves and we'll retune Friday's "
                "list.</p><p>— Will, Fields</p>")
    return _wrap("".join(rows))


# ---------------- send ----------------
def tracked_send(to, subject, html, type_, meta, dry):
    if dry:
        print(f"  [DRY] would send to {to} | {type_} | subj: {subject}")
        return {"ok": True, "dry": True}
    r = requests.post(SEND_URL, headers={"x-send-secret": SECRET, "Content-Type": "application/json"},
                      data=json.dumps({"to": to, "subject": subject, "html": html, "type": type_, "meta": meta}), timeout=45)
    return r.json()


def build_picks(suburbs, beds, baths, budget):
    brief = {"suburbs": suburbs, "beds": beds, "baths": baths, "budget": budget}
    cands = fpf.gather(brief)
    if budget:
        cands = [c for c in cands if not (c["ask"] and c["ask"] > budget * 1.25)]
    flagged = [c for c in cands if c["gap"] is not None and abs(c["gap"]) > fpf.SANITY_PCT]
    scoreable = sorted([c for c in cands if c not in flagged], key=lambda c: -fpf.score(c, budget))
    return fpf.assign_roles(scoreable, budget)


def handle_lead(lead, dry=False, force_friday=None):
    sm = get_client()["system_monitor"]
    f = lead.get("fields", {}) or {}
    email = (f.get("email") or "").strip()
    if not email:
        print("  no email — skip"); return
    friday = is_friday() if force_friday is None else force_friday
    subs = target_suburbs(f.get("area"))
    sends = {}

    if not subs:                                   # elsewhere / unknown suburb
        html = welcome_html("", None, "needs_suburb")
        r = tracked_send(email, "Your Gold Coast shortlist — one quick question first", html,
                         "fpf_welcome_needs_suburb", {"lead": lead["_id"]}, dry)
        sends["welcome"] = r.get("send_id")
        status = "welcomed_needs_suburb"
    else:
        label = " / ".join(SUBURB_LABEL.get(s, s) for s in subs)
        budget = budget_for(subs)
        html = welcome_html(label, budget, "friday" if friday else "standard")
        subj = "Your first 5 — coming through today" if friday else "Your first shortlist — one quick thing first"
        r = tracked_send(email, subj, html, "fpf_welcome_friday" if friday else "fpf_welcome", {"lead": lead["_id"]}, dry)
        sends["welcome"] = r.get("send_id")
        status = "welcomed"
        if friday:
            picks = build_picks(subs, _int(f.get("bedrooms")), _int(f.get("bathrooms")), budget)
            if picks:
                r2 = tracked_send(email, f"Your 5 for Friday — {label}", shortlist_html(label, picks),
                                  "fpf_shortlist", {"lead": lead["_id"], "count": len(picks)}, dry)
                sends["shortlist"] = r2.get("send_id")
                status = "welcomed+shortlist_sent"
    if not dry:
        sm["fb_leads"].update_one({"_id": lead["_id"]}, {"$set": {
            "fpf_status": "active", "contact_status": status, "sends": sends,
            "contacted_at": datetime.now(timezone.utc).isoformat()}})
    print(f"  {email}: {status} {sends}")


def friday_batch(dry=False, force=False):
    if not force and not is_friday():
        print("not Friday (AEST) — batch skipped"); return
    sm = get_client()["system_monitor"]
    today = datetime.now(AEST).date().isoformat()
    q = {"form_id": {"$in": list(BUYER_BRIEF_FORMS)}, "fpf_status": "active"}
    n = 0
    for lead in sm["fb_leads"].find(q):
        f = lead.get("fields", {}) or {}
        subs = target_suburbs(f.get("area"))
        if not subs:
            continue                                # no suburb → skip (awaiting reply)
        if str(lead.get("last_shortlist_at", ""))[:10] == today:
            continue                                # already sent today — no double-send
        label = " / ".join(SUBURB_LABEL.get(s, s) for s in subs)
        budget = budget_for(subs)
        picks = build_picks(subs, _int(f.get("bedrooms")), _int(f.get("bathrooms")), budget)
        if not picks:
            continue
        email = f.get("email")
        r = tracked_send(email, f"Your 5 for Friday — {label}", shortlist_html(label, picks),
                         "fpf_shortlist", {"lead": lead["_id"], "count": len(picks)}, dry)
        if not dry:
            sm["fb_leads"].update_one({"_id": lead["_id"]},
                                      {"$set": {"last_shortlist_at": datetime.now(timezone.utc).isoformat(),
                                                "last_shortlist_send": r.get("send_id")}})
        n += 1
        print(f"  batch → {email} ({label})")
    print(f"friday batch: {n} shortlists sent")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lead-id")
    ap.add_argument("--friday-batch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-friday", action="store_true", help="treat today as Friday (testing)")
    args = ap.parse_args()
    if args.friday_batch:
        friday_batch(dry=args.dry_run)
    elif args.lead_id:
        lead = get_client()["system_monitor"]["fb_leads"].find_one({"_id": args.lead_id})
        if not lead:
            sys.exit("lead not found")
        handle_lead(lead, dry=args.dry_run, force_friday=True if args.force_friday else None)
    else:
        sys.exit("use --lead-id <id> or --friday-batch")


if __name__ == "__main__":
    main()

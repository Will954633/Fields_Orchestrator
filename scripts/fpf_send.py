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


WEBSITE_SUBS_COLL = "five_property_friday_subscribers"
_ALL_THREE = ["robina", "burleigh_waters", "varsity_lakes"]
_LABEL_TO_KEY = {v.lower(): k for k, v in SUBURB_LABEL.items()}


def website_sub_suburbs(doc):
    """Resolve suburb keys for a website 5PF subscriber (the /for-sale-v3 ladder
    opt-in, or a legacy signup). Prefers the explicit `suburbs` key list; falls
    back to `suburb_preference` ('all', comma/slash-joined keys, or labels).
    Unknown/empty → all three (a subscriber never gets nothing)."""
    keys = [s for s in (doc.get("suburbs") or []) if s in SUBURB_LABEL]
    if keys:
        return keys
    pref = (doc.get("suburb_preference") or "").strip().lower()
    if not pref or pref == "all":
        return list(_ALL_THREE)
    out = []
    for p in re.split(r"[,/]", pref):
        p = p.strip()
        if p in SUBURB_LABEL and p not in out:
            out.append(p)
        elif p in _LABEL_TO_KEY and _LABEL_TO_KEY[p] not in out:
            out.append(_LABEL_TO_KEY[p])
    return out or list(_ALL_THREE)


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

    fails = []                                     # (kind, error) for any send that returned ok:false
    if not subs:                                   # elsewhere / unknown suburb
        html = welcome_html("", None, "needs_suburb")
        r = tracked_send(email, "Your Gold Coast shortlist — one quick question first", html,
                         "fpf_welcome_needs_suburb", {"lead": lead["_id"]}, dry)
        sends["welcome"] = r.get("send_id")
        if not (dry or r.get("ok")): fails.append(("welcome_needs_suburb", r.get("error")))
        status = "welcomed_needs_suburb"
    else:
        label = " / ".join(SUBURB_LABEL.get(s, s) for s in subs)
        budget = budget_for(subs)
        html = welcome_html(label, budget, "friday" if friday else "standard")
        subj = "Your first 5 — coming through today" if friday else "Your first shortlist — one quick thing first"
        r = tracked_send(email, subj, html, "fpf_welcome_friday" if friday else "fpf_welcome", {"lead": lead["_id"]}, dry)
        sends["welcome"] = r.get("send_id")
        if not (dry or r.get("ok")): fails.append(("welcome", r.get("error")))
        status = "welcomed"
        if friday:
            picks = build_picks(subs, _int(f.get("bedrooms")), _int(f.get("bathrooms")), budget)
            if picks:
                r2 = tracked_send(email, f"Your 5 for Friday — {label}", shortlist_html(label, picks),
                                  "fpf_shortlist", {"lead": lead["_id"], "count": len(picks)}, dry)
                sends["shortlist"] = r2.get("send_id")
                if not (dry or r2.get("ok")): fails.append(("shortlist", r2.get("error")))
                status = "welcomed+shortlist_sent"
    if fails:                                      # never let a new-lead send fail silently
        print(f"  SEND FAILURE for {email}: {fails}")
        try:
            from telegram_notify import send_message
            send_message(f"🚨 *FPF new-lead send failed* — {email}\n"
                         + "\n".join(f"• {k}: {err}" for k, err in fails)
                         + "\n\nLikely Gmail token expiry — re-auth (gmail_send_token_expiry memory).")
        except Exception as e:
            print(f"(telegram alert failed: {e})")
    if not dry:
        sm["fb_leads"].update_one({"_id": lead["_id"]}, {"$set": {
            "fpf_status": "active", "contact_status": status, "sends": sends,
            "contacted_at": datetime.now(timezone.utc).isoformat()}})
    print(f"  {email}: {status} {sends}")


def _aest_date(v):
    """AEST calendar date (YYYY-MM-DD) for a stored UTC-ISO timestamp/datetime.
    The double-send guard compares dates: last_shortlist_at is stored in UTC, so
    at 09:00 AEST it reads as the *previous* UTC day — a naive [:10] slice made
    the guard compare a UTC date to an AEST date and mismatch. Always normalise
    to AEST before comparing."""
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(AEST).date().isoformat()
    except Exception:
        return None


def _report_batch(sent, failed, skipped, dry):
    """Make a batch outcome loud, not silent. Records a self-reported result to
    system_monitor.job_runs (read by main_site_health_check.py -> "Leads & CRM"
    -> "Five Property Friday delivery") and Telegram-alerts on any send failure.
    This is the fix for [FPF-GMAIL-TOKEN] 2026-07-24: a dead Gmail token made
    every send return ok:false while the batch still logged "N shortlists sent"
    and stamped the leads — a full weekly cycle lost with zero signal."""
    if dry:
        return
    status = "error" if failed else "success"
    detail = ("; ".join(f"{e}: {err}" for e, err in failed)[:400] if failed
              else f"{len(sent)} shortlists delivered")
    try:
        from job_status import record_job_result
        # Cron: Fri 09:00 AEST, weekly. stale_hours=192 (8d) so one missed
        # Friday flags rather than waiting the default 10.5d.
        record_job_result("fpf_friday_batch", status, detail=detail,
                          cadence_hours=168, stale_hours=192,
                          title="Five Property Friday — Friday shortlist batch",
                          sent=len(sent), failed=len(failed), skipped=skipped)
    except Exception as e:
        print(f"(job_status record failed: {e})")
    if failed:
        try:
            from telegram_notify import send_message
            lines = "\n".join(f"• {e} — {err}" for e, err in failed)
            send_message(
                "🚨 *Five Property Friday — send failure*\n"
                f"{len(sent)} sent, *{len(failed)} FAILED*, {skipped} already-sent.\n{lines}\n\n"
                "Most likely the Gmail OAuth token expired (7-day testing-mode). "
                "Re-auth per the `gmail_send_token_expiry` memory / fix-history [FPF-GMAIL-TOKEN], "
                "then re-run `python3 scripts/fpf_send.py --friday-batch`.")
        except Exception as e:
            print(f"(telegram alert failed: {e})")


def friday_batch(dry=False, force=False):
    if not force and not is_friday():
        print("not Friday (AEST) — batch skipped"); return
    sm = get_client()["system_monitor"]
    today = datetime.now(AEST).date().isoformat()   # AEST calendar date
    q = {"form_id": {"$in": list(BUYER_BRIEF_FORMS)}, "fpf_status": "active"}
    sent, failed, skipped = [], [], 0
    for lead in sm["fb_leads"].find(q):
        f = lead.get("fields", {}) or {}
        subs = target_suburbs(f.get("area"))
        if not subs:
            continue                                # no suburb → skip (awaiting reply)
        if _aest_date(lead.get("last_shortlist_at")) == today:
            skipped += 1
            continue                                # already sent today — no double-send
        label = " / ".join(SUBURB_LABEL.get(s, s) for s in subs)
        budget = budget_for(subs)
        picks = build_picks(subs, _int(f.get("bedrooms")), _int(f.get("bathrooms")), budget)
        if not picks:
            continue
        email = f.get("email")
        r = tracked_send(email, f"Your 5 for Friday — {label}", shortlist_html(label, picks),
                         "fpf_shortlist", {"lead": lead["_id"], "count": len(picks)}, dry)
        # Only count + stamp a send that ACTUALLY succeeded. tracked_send returns
        # {ok:false, error} on a failed Gmail send — stamping on that is what hid
        # the 2026-07-24 outage.
        if dry or r.get("ok"):
            if not dry:
                sm["fb_leads"].update_one({"_id": lead["_id"]},
                                          {"$set": {"last_shortlist_at": datetime.now(timezone.utc).isoformat(),
                                                    "last_shortlist_send": r.get("send_id")}})
            sent.append(email)
            print(f"  batch → {email} ({label})")
        else:
            failed.append((email, r.get("error", "unknown")))
            print(f"  FAILED → {email} ({label}): {r.get('error')}")

    # Website 5 Property Friday opt-ins (system_monitor.five_property_friday_subscribers).
    # Previously these were stored by the signup endpoint but NEVER emailed — only
    # fb_leads was queried. The /for-sale-v3 ladder opt-in writes here too, so the
    # batch now delivers to them as well. Dedup: skip any email already handled as
    # an active buyer-brief FB lead, so a person on both lists gets one email.
    fb_emails = set()
    for l in sm["fb_leads"].find({"form_id": {"$in": list(BUYER_BRIEF_FORMS)}, "fpf_status": "active"},
                                 {"fields.email": 1}):
        e = ((l.get("fields") or {}).get("email") or "").strip().lower()
        if e:
            fb_emails.add(e)
    for sub in sm[WEBSITE_SUBS_COLL].find({"status": "active"}):
        email = (sub.get("email") or "").strip()
        if not email or email.lower() in fb_emails:
            continue                                # no email, or already sent via fb_leads
        if _aest_date(sub.get("last_shortlist_at")) == today:
            skipped += 1
            continue                                # already sent today — no double-send
        subs = website_sub_suburbs(sub)
        label = " / ".join(SUBURB_LABEL.get(s, s) for s in subs)
        budget = budget_for(subs)
        picks = build_picks(subs, _int(sub.get("bedrooms")), _int(sub.get("bathrooms")), budget)
        if not picks:
            continue
        r = tracked_send(email, f"Your 5 for Friday — {label}", shortlist_html(label, picks),
                         "fpf_shortlist", {"subscriber": str(sub.get("_id")), "count": len(picks), "src": "website"}, dry)
        if dry or r.get("ok"):
            if not dry:
                sm[WEBSITE_SUBS_COLL].update_one({"_id": sub["_id"]},
                                                 {"$set": {"last_shortlist_at": datetime.now(timezone.utc).isoformat(),
                                                           "last_shortlist_send": r.get("send_id")}})
            sent.append(email)
            print(f"  batch(web) → {email} ({label})")
        else:
            failed.append((email, r.get("error", "unknown")))
            print(f"  FAILED(web) → {email} ({label}): {r.get('error')}")

    print(f"friday batch: {len(sent)} sent, {len(failed)} failed, {skipped} already-sent-today")
    _report_batch(sent, failed, skipped, dry)


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

#!/usr/bin/env python3
"""
walkthrough_outreach.py — suburb walkthrough video CRM outreach (Sep 2026).

Drafts a personalised email + SMS per reachable CRM contact pointing at the suburb
walkthrough deep link (/news/<suburb>?play=1), lets Will sample-send per contact via
the live single-contact CRM endpoints (full tracking for free), and reports
opens / clicks / walkthrough viewing engagement.

Modes
  --build                 build/refresh drafts into system_monitor.walkthrough_outreach_drafts
                          (+ writes a human review file next to the targets JSON)
  --preview [--limit N]   print drafts (default 5; 0 = all)
  --send --contact X      send ONE contact's draft. X = contact id, email, or phone.
                          --channel email|sms|both (default: recommended channel)
  --report                engagement report: email opens/clicks, SMS delivery,
                          PostHog walkthrough events bound via ?lead= token

Tracking chain (why no extra work is needed at send time):
  email: crm-contact-send → mailer.mjs instrument() rewrites links through
         email-track.mjs (open pixel + click log) and the click redirect appends
         ?lead=<link_token>, which root.tsx useLeadIdentify binds to PostHog.
  sms:   no rewrite layer exists, so the SMS link carries &lead=<link_token>
         directly (token minted here, same uuid4-hex shape as email-track.mjs).
  video: MarketFlowProto.engine.ts fires walkthrough_start / _progress(25/50/75) /
         _film / _complete / _exit / _unmute / _cta_shown to PostHog (2026-09-11).

Deliberately NOT a cron job — one-shot campaign tool, so no job_run heartbeat.
Sending is always explicit (--send, one contact per invocation). Bulk send is a
conscious follow-up decision, not something this script does unattended.
"""

import argparse
import base64
import hashlib
import hmac
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from shared.env import load_env  # noqa: E402
from shared.db import get_client  # noqa: E402

CAMPAIGN = "walkthrough_sep26"
CAMPAIGN_DIR = ROOT / "22_CRM" / "campaigns" / CAMPAIGN
TARGETS_JSON = CAMPAIGN_DIR / "targets_2026-09-11.json"
REVIEW_MD = CAMPAIGN_DIR / "DRAFTS_REVIEW.md"
SITE = "https://fieldsestate.com.au"

SLUGS = {"Robina": "robina", "Varsity Lakes": "varsity-lakes", "Burleigh Waters": "burleigh-waters"}
DEFAULT_SUBURB = "Robina"


def contact_key(contact_id: str, secret: str) -> str:
    """k = base64url(HMAC-SHA256(REPORT_LINK_SECRET, "crm:"+id))[:16] — mirrors crm-contact-send.mjs."""
    dig = hmac.new(secret.encode(), f"crm:{contact_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(dig).decode().rstrip("=")[:16]


def is_au_mobile(phone_norm: str) -> bool:
    return bool(re.fullmatch(r"\+614\d{8}", phone_norm or ""))


def first_name(name: str) -> str:
    if not name:
        return ""
    tok = name.strip().split()[0]
    return tok.title() if not tok.isupper() or len(tok) <= 3 else tok.title()


def links_for(suburb: str, token: str | None):
    slug = SLUGS[suburb]
    email_link = f"{SITE}/news/{slug}?play=1&utm_source=crm_email&utm_campaign={CAMPAIGN}"
    sms_link = f"{SITE}/news/{slug}?play=1&utm_source=crm_sms&utm_campaign={CAMPAIGN}"
    if token:
        sms_link += f"&lead={token}"
    return email_link, sms_link


def compose(first: str, suburb: str, email_link: str, sms_link: str):
    greet = f"Hi {first}," if first else "Hi,"
    subject = f"A video walkthrough of the {suburb} market"
    email_body = (
        f"{greet}\n\n"
        f"It's Will here from Fields Real Estate. I've just completed a video walkthrough "
        f"of the {suburb} market. In it I speak to one metric that shows how buyer demand "
        f"has changed, and another that's proved to be a leading indicator on where the "
        f"market goes next.\n\n"
        f"Watch it here: {email_link}\n\n"
        f"Kind regards,\nWill Simpson\nFields Real Estate"
    )
    sms_greet = f"Hi {first}, it's" if first else "Hi, it's"
    sms_body = (
        f"{sms_greet} Will from Fields Real Estate. I've just completed a video walkthrough "
        f"of the {suburb} market — one metric shows how buyer demand has changed, another "
        f"has been a leading indicator on where the market goes next. Watch: {sms_link}"
    )
    return subject, email_body, sms_body


def build(db):
    data = json.loads(TARGETS_JSON.read_text())
    col = db["walkthrough_outreach_drafts"]
    crm = db["crm_contacts"]
    built, skipped = [], []

    for c in data["contacts"]:
        if c.get("internal_or_test"):
            skipped.append((c["id"], "internal_or_test"))
            continue
        email = (c.get("email") or "").strip().lower()
        phone = c.get("phone_norm") or ""
        emailable = bool(email) and not c.get("do_not_email")
        smsable = is_au_mobile(phone) and not c.get("do_not_sms")
        if not emailable and not smsable:
            skipped.append((c["id"], "unreachable (no valid email/mobile)"))
            continue

        flags = []
        if c.get("do_not_email") and email:
            flags.append("do_not_email — email suppressed, SMS only")
        if email.endswith("@bigpong.com"):
            flags.append("email domain looks like a typo (bigpong.com) — will bounce")
        if (c.get("phone_norm") or c.get("phone")) and not smsable:
            flags.append(f"phone not an AU mobile ({c.get('phone') or c.get('phone_norm')}) — SMS suppressed")

        suburb = c.get("suburb_assignment")
        basis = c.get("suburb_basis") or ""
        if suburb not in SLUGS:
            area = (c.get("lead_brief_area") or "").lower()
            if area == "open_to_all_three":
                suburb, basis = DEFAULT_SUBURB, "open_to_all_three → defaulted"
            else:
                suburb, basis = DEFAULT_SUBURB, "no suburb signal → defaulted"
                flags.append("no suburb signal — defaulted to Robina, review before sending")

        # Mint/reuse the durable ?lead= token (same shape email-track.mjs mints on click).
        token = None
        if smsable or emailable:
            doc = crm.find_one({"_id": c["id"]}, {"link_token": 1, "messenger": 1, "contact_status": 1})
            if doc is None:
                from bson import ObjectId
                if re.fullmatch(r"[a-f0-9]{24}", c["id"]):
                    doc = crm.find_one({"_id": ObjectId(c["id"])},
                                       {"link_token": 1, "messenger": 1, "contact_status": 1})
            if doc is None:
                skipped.append((c["id"], "crm contact not found"))
                continue
            token = doc.get("link_token")
            if not token:
                token = uuid.uuid4().hex
                crm.update_one({"_id": doc["_id"]}, {"$set": {"link_token": token}})

        # ⭐ CHANNEL PREFERENCE (Will, 2026-09-11): someone who has WRITTEN TO US on
        # Messenger gets the message there — that's where they demonstrably engage
        # (the Sep-4 messenger repliers all ignored their campaign email). Messenger
        # drafts are pasted by Will from the Business inbox (Meta's messaging window
        # bars API sends on old threads), so --send-all lists them instead of sending;
        # log the paste with --mark-messenger-sent. Declined/spam threads never qualify
        # (their contact_status suppresses them at the send stage anyway).
        msgr = (doc or {}).get("messenger") or {}
        messenger_pref = bool(msgr.get("has_inbound")) and \
            (doc or {}).get("contact_status") not in ("do_not_contact", "not_interested", "spam")

        email_link, sms_link = links_for(suburb, token)
        subject, email_body, sms_body = compose(first_name(c.get("name") or ""), suburb, email_link, sms_link)
        msgr_link = sms_link.replace("utm_source=crm_sms", "utm_source=crm_messenger")
        _, _, msgr_body = compose(first_name(c.get("name") or ""), suburb, email_link, msgr_link)

        draft = {
            "_id": c["id"],
            "campaign": CAMPAIGN,
            "name": c.get("name") or "",
            "email": email if emailable else None,
            "phone": phone if smsable else None,
            "suburb": suburb,
            "suburb_basis": basis or c.get("suburb_basis"),
            "link_token": token,
            "email_draft": {"subject": subject, "body": email_body} if emailable else None,
            "sms_draft": {"body": sms_body} if smsable else None,
            "messenger_draft": {"body": msgr_body, "thread_link": msgr.get("thread_link")} if messenger_pref else None,
            "recommended_channel": "messenger" if messenger_pref else ("email" if emailable else "sms"),
            "flags": flags,
            "source": c.get("source"),
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        col.update_one(
            {"_id": draft["_id"]},
            {"$set": draft, "$setOnInsert": {"status": "draft", "sends": []}},
            upsert=True,
        )
        built.append(draft)

    write_review(built, skipped)
    by_suburb = {}
    for d in built:
        by_suburb[d["suburb"]] = by_suburb.get(d["suburb"], 0) + 1
    print(f"built {len(built)} drafts ({by_suburb}), skipped {len(skipped)}")
    for sid, why in skipped:
        print(f"  skipped {sid}: {why}")
    if not built:
        raise RuntimeError("built 0 drafts from a non-empty targets file — something is broken")
    print(f"review file: {REVIEW_MD}")


def write_review(built, skipped):
    lines = [
        "# Walkthrough outreach — drafts for review",
        f"\nGenerated {datetime.now(timezone.utc).isoformat()} · campaign `{CAMPAIGN}` · {len(built)} drafts",
        "\nSend a sample:  `python3 scripts/walkthrough_outreach.py --send --contact <email|phone|id> [--channel email|sms|both]`\n",
    ]
    for suburb in ["Robina", "Varsity Lakes", "Burleigh Waters"]:
        subset = [d for d in built if d["suburb"] == suburb]
        if not subset:
            continue
        lines.append(f"\n## {suburb} — {len(subset)} contacts\n")
        for d in subset:
            who = d["name"] or "(no name)"
            reach = " / ".join(x for x in [d["email"], d["phone"]] if x)
            lines.append(f"### {who} — {reach}  `[{d['recommended_channel']}]`")
            lines.append(f"- suburb basis: {d['suburb_basis']} · source: {d['source']}")
            for f in d["flags"]:
                lines.append(f"- ⚠ {f}")
            if d["email_draft"]:
                lines.append(f"\n**Email — subject:** {d['email_draft']['subject']}\n")
                lines.append("```\n" + d["email_draft"]["body"] + "\n```")
            if d["sms_draft"]:
                lines.append("\n**SMS:**\n")
                lines.append("```\n" + d["sms_draft"]["body"] + "\n```")
            lines.append("")
    if skipped:
        lines.append("\n## Skipped\n")
        for sid, why in skipped:
            lines.append(f"- {sid}: {why}")
    REVIEW_MD.write_text("\n".join(lines))


def find_draft(db, needle: str):
    col = db["walkthrough_outreach_drafts"]
    n = needle.strip()
    d = col.find_one({"_id": n})
    if not d:
        d = col.find_one({"email": n.lower()})
    if not d:
        norm = re.sub(r"[^\d+]", "", n)
        if norm.startswith("0"):
            norm = "+61" + norm[1:]
        d = col.find_one({"phone": norm})
    return d


def send(db, needle: str, channel: str | None):
    import os
    secret = os.environ["REPORT_LINK_SECRET"]
    d = find_draft(db, needle)
    if not d:
        sys.exit(f"no draft matches {needle!r} — run --build first, or check the value")
    channels = [channel] if channel in ("email", "sms") else (
        ["email", "sms"] if channel == "both" else [d["recommended_channel"]]
    )
    k = contact_key(d["_id"], secret)
    col = db["walkthrough_outreach_drafts"]
    for ch in channels:
        draft = d.get(f"{ch}_draft")
        if not draft:
            print(f"  {ch}: no draft for this contact (channel not reachable) — skipped")
            continue
        if ch == "email":
            r = requests.post(f"{SITE}/api/v1/crm-contact-send", timeout=30, json={
                "id": d["_id"], "k": k, "subject": draft["subject"],
                "body": draft["body"], "type": CAMPAIGN,
            })
        else:
            r = requests.post(f"{SITE}/api/v1/crm-contact-sms", timeout=30, json={
                "id": d["_id"], "k": k, "body": draft["body"],
            })
        try:
            res = r.json()
        except Exception:
            res = {"ok": False, "error": f"http {r.status_code}: {r.text[:200]}"}
        stamp = {"channel": ch, "at": datetime.now(timezone.utc).isoformat(), "result": res}
        col.update_one({"_id": d["_id"]}, {
            "$push": {"sends": stamp},
            "$set": {"status": "sent" if res.get("ok") else "send_failed"},
        })
        print(f"  {ch} → {d.get(ch) or d.get('phone')}: {json.dumps(res)}")
        if not res.get("ok"):
            sys.exit(f"{ch} send FAILED for {d['_id']}: {res.get('error')}")


SELF_TEST_ID = "6a96158a78932e9fc290a09e"  # Will's own contact — excluded from bulk


def send_all(db):
    """Bulk send: every draft not yet sent, via its recommended channel (email where
    available, SMS for phone-only) — one message per person. Throttled; aborts after
    5 consecutive failures so a systemic outage doesn't burn the whole list."""
    import os
    import time
    secret = os.environ["REPORT_LINK_SECRET"]
    col = db["walkthrough_outreach_drafts"]
    pending = [d for d in col.find({"campaign": CAMPAIGN})
               if d["_id"] != SELF_TEST_ID and d.get("status") == "draft"]
    print(f"bulk send: {len(pending)} pending drafts")
    sent = failed = consec_fail = 0
    manual = []
    for d in pending:
        ch = d["recommended_channel"]
        if ch == "messenger":
            manual.append(d)
            continue
        draft = d.get(f"{ch}_draft")
        if not draft:
            print(f"  SKIP {d['name'] or d['_id']}: no {ch} draft")
            continue
        k = contact_key(d["_id"], secret)
        try:
            if ch == "email":
                r = requests.post(f"{SITE}/api/v1/crm-contact-send", timeout=30, json={
                    "id": d["_id"], "k": k, "subject": draft["subject"],
                    "body": draft["body"], "type": CAMPAIGN})
            else:
                r = requests.post(f"{SITE}/api/v1/crm-contact-sms", timeout=30, json={
                    "id": d["_id"], "k": k, "body": draft["body"]})
            res = r.json()
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "error": str(e)[:200]}
        col.update_one({"_id": d["_id"]}, {
            "$push": {"sends": {"channel": ch, "at": datetime.now(timezone.utc).isoformat(), "result": res}},
            "$set": {"status": "sent" if res.get("ok") else "send_failed"},
        })
        tag = "OK " if res.get("ok") else "FAIL"
        print(f"  {tag} [{ch}] {d['name'] or '(no name)'} → {d.get(ch) or d.get('phone')}"
              + ("" if res.get("ok") else f"  ({res.get('error')})"))
        if res.get("ok"):
            sent += 1
            consec_fail = 0
        else:
            failed += 1
            consec_fail += 1
            if consec_fail >= 5:
                sys.exit(f"ABORTED after 5 consecutive failures — {sent} sent, {failed} failed, "
                         f"{len(pending) - sent - failed} untouched. Investigate before resuming.")
        time.sleep(1.5)
    print(f"\ndone: {sent} sent, {failed} failed")
    if manual:
        print(f"\n⚠ {len(manual)} MESSENGER-preferred contacts NOT sent (Meta bars API sends on old"
              f" threads) — Will pastes these from the Business inbox, then run"
              f" --mark-messenger-sent --contact <name>:")
        for d in manual:
            print(f"\n  {d['name']} — {d['messenger_draft'].get('thread_link')}\n"
                  f"    {d['messenger_draft']['body']}")
    if sent == 0 and pending and len(manual) < len(pending):
        raise RuntimeError("0 of the sendable drafts sent — endpoint or auth is broken")


def mark_messenger_sent(db, needle: str):
    """Record a manual Messenger paste: draft → sent, plus a communications[] timeline
    entry on the contact (the inbox has no API hook, so honesty is on us here)."""
    from bson import ObjectId
    d = find_draft(db, needle) or db["walkthrough_outreach_drafts"].find_one(
        {"campaign": CAMPAIGN, "name": {"$regex": re.escape(needle.strip()), "$options": "i"}})
    if not d or not d.get("messenger_draft"):
        sys.exit(f"no messenger draft matches {needle!r}")
    now = datetime.now(timezone.utc).isoformat()
    db["walkthrough_outreach_drafts"].update_one({"_id": d["_id"]}, {
        "$push": {"sends": {"channel": "messenger", "at": now, "result": {"ok": True, "manual": True}}},
        "$set": {"status": "sent"},
    })
    crm = db["crm_contacts"]
    q = {"_id": d["_id"]}
    if crm.find_one(q) is None and re.fullmatch(r"[a-f0-9]{24}", d["_id"]):
        q = {"_id": ObjectId(d["_id"])}
    r = crm.update_one(q, {
        "$set": {"last_contact_at": now, "updated_at": now},
        "$push": {"communications": {
            "type": "messenger", "direction": "out", "date": now,
            "body": d["messenger_draft"]["body"], "outcome": "sent",
            "channel": "messenger", "by": "will",
        }},
    })
    if r.matched_count != 1:
        sys.exit(f"draft updated but CRM contact not matched for {d['name']!r} — investigate")
    print(f"marked messenger-sent + timeline entry: {d['name']}")


def report(db):
    from crm_sync import posthog_query  # noqa: WPS433

    drafts = list(db["walkthrough_outreach_drafts"].find({"campaign": CAMPAIGN}))
    by_token = {d["link_token"]: d for d in drafts if d.get("link_token")}
    sent = [d for d in drafts if d.get("status") in ("sent", "send_failed")]
    print(f"campaign {CAMPAIGN}: {len(drafts)} drafts, {len(sent)} with send attempts\n")

    # Email: sends of this campaign type + their open/click events
    sends = list(db["email_sends"].find({"type": CAMPAIGN}))
    ev_by_send = {}
    for e in db["email_events"].find({"send_id": {"$in": [s["send_id"] for s in sends]}}):
        ev_by_send.setdefault(e["send_id"], []).append(e)
    print(f"— EMAIL: {len(sends)} sent")
    for s in sends:
        evs = ev_by_send.get(s["send_id"], [])
        opens = sum(1 for e in evs if e["kind"] == "open")
        clicks = [e for e in evs if e["kind"] == "click"]
        line = f"   {s['to']}: opens={opens} clicks={len(clicks)}"
        if clicks:
            line += f" first_click={clicks[0]['at']}"
        print(line)

    # SMS: campaign link marker in body + delivery status from the JustCall webhook
    sms = list(db["sms_messages"].find({"direction": "out", "body": {"$regex": CAMPAIGN}}))
    print(f"\n— SMS: {len(sms)} sent")
    for m in sms:
        print(f"   {m['phone']}: status={m.get('status')} at={m.get('sent_at')}")

    # Walkthrough engagement, bound via ?lead= token (token becomes the PostHog distinct_id
    # after identify; lead_link_visit confirms the click landed). Scoped to AFTER the first
    # campaign send: link_tokens are reused from earlier tracked emails, so an unscoped query
    # surfaces pre-campaign activity as if it were campaign engagement.
    first_send = None
    for d in drafts:
        for s in d.get("sends", []):
            if s.get("result", {}).get("ok") and (first_send is None or s["at"] < first_send):
                first_send = s["at"]
    if by_token and first_send:
        toks = ",".join(f"'{t}'" for t in by_token)
        since = first_send[:19].replace("T", " ")
        rows = posthog_query(
            "SELECT distinct_id, event, count(), max(toInt(coalesce(properties.video_t, '0'))) "
            "FROM events "
            f"WHERE distinct_id IN ({toks}) AND timestamp >= toDateTime('{since}') "
            "AND event IN ('lead_link_visit','$pageview','walkthrough_start','walkthrough_progress',"
            "'walkthrough_film','walkthrough_complete','walkthrough_exit','walkthrough_unmute',"
            "'walkthrough_cta_shown','walkthrough_fb_follow_click','walkthrough_subscribe_click') "
            "GROUP BY distinct_id, event ORDER BY distinct_id, event LIMIT 500",
            soft=True,
        )
        print(f"\n— WALKTHROUGH ENGAGEMENT (via lead token, since {since} UTC):")
        if not rows:
            print("   no bound sessions yet")
        cur = None
        for did, event, n, max_t in rows:
            d = by_token.get(did)
            if did != cur:
                cur = did
                print(f"   {d['name'] or d['_id']} ({d['suburb']}):")
            extra = f" (max video_t {max_t}s)" if str(event).startswith("walkthrough") and max_t else ""
            print(f"      {event} ×{n}{extra}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--send", action="store_true")
    mode.add_argument("--send-all", action="store_true", help="bulk: every pending draft, recommended channel")
    mode.add_argument("--mark-messenger-sent", action="store_true",
                      help="log a manual Messenger paste (draft→sent + timeline entry)")
    mode.add_argument("--report", action="store_true")
    ap.add_argument("--contact", help="--send target: contact id, email, or phone")
    ap.add_argument("--channel", choices=["email", "sms", "both"])
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    load_env()
    db = get_client()["system_monitor"]

    if args.build:
        build(db)
    elif args.preview:
        q = db["walkthrough_outreach_drafts"].find({"campaign": CAMPAIGN})
        if args.limit:
            q = q.limit(args.limit)
        for d in q:
            print(json.dumps({k: v for k, v in d.items() if k != "built_at"}, indent=2, default=str))
    elif args.send:
        if not args.contact:
            sys.exit("--send requires --contact <id|email|phone>")
        send(db, args.contact, args.channel)
    elif args.send_all:
        send_all(db)
    elif args.mark_messenger_sent:
        if not args.contact:
            sys.exit("--mark-messenger-sent requires --contact <name|id>")
        mark_messenger_sent(db, args.contact)
    elif args.report:
        report(db)


if __name__ == "__main__":
    main()

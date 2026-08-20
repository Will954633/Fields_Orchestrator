#!/usr/bin/env python3
"""
Log a real human touch (call / SMS / email) against a contact in system_monitor.crm_contacts,
and optionally set when they should be followed up.

Everything else in the CRM is written by automation from observed behaviour. This is the one
script for the things only Will knows: that he rang, what was said, what he sent, and when
to come back. Those facts have been living in his phone and nowhere else.

Writes:
  communications[]   append {type, date, channel, subject, body, outcome, logged_by}
                     -- same array engagement_activity_to_sheet.py reads for "already sent",
                        which renders `subject` (or falls back to `type`), so both are set.
  notes[]            append {text, author, timestamp}   (existing shape: text/author/timestamp)
  last_contact_at    ISO timestamp of this touch
  contact_status     free text -- "spoke", "no_answer", "self_serve" ...
  follow_up_at       ISO date (YYYY-MM-DD) the next touch is due  -> drives the Priority tab
  follow_up_reason   one line, shown to Will on the Priority tab
  follow_up_channel  call | sms | email  -- how to make contact, NOT always the phone
  contact_preference optional, sticky: how this person has ASKED to be dealt with

follow_up_at is the whole point: it is the only field that makes a lead resurface. A touch
logged without one is a lead that quietly goes cold.

Usage:
  python3 scripts/log_contact_touch.py --email x@y.com --type call --outcome no_answer \\
      --note "Rang 10:14am, no answer, left voicemail." \\
      --follow-up 2026-08-22 --follow-up-reason "..." --follow-up-channel call
  python3 scripts/log_contact_touch.py --email x@y.com --type sms --body-file msg.txt
  python3 scripts/log_contact_touch.py --email x@y.com --show
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.db import get_client  # noqa: E402

AEST = timezone(timedelta(hours=10))
VALID_TYPES = ("call", "sms", "email", "voicemail", "meeting", "other")
VALID_CHANNELS = ("call", "sms", "email", "none")


def now_aest() -> str:
    return datetime.now(AEST).isoformat(timespec="seconds")


def show(db, email: str) -> None:
    c = db.crm_contacts.find_one({"email": email.lower()})
    if not c:
        print(f"No contact for {email}")
        return
    print(f"{c.get('name') or '(no name)'} <{c['email']}>  phone={c.get('phone') or '-'}")
    print(f"  status={c.get('status')}  contact_status={c.get('contact_status') or '-'}")
    print(f"  last_contact_at={c.get('last_contact_at') or '-'}")
    print(f"  follow_up_at={c.get('follow_up_at') or '-'} "
          f"({c.get('follow_up_channel') or '-'}) {c.get('follow_up_reason') or ''}")
    if c.get("contact_preference"):
        print(f"  contact_preference={c['contact_preference']}")
    for comm in c.get("communications") or []:
        print(f"  - {str(comm.get('date'))[:16]} [{comm.get('type')}] "
              f"{comm.get('subject') or ''} {comm.get('outcome') or ''}")
        if comm.get("body"):
            print(f"      \"{comm['body'][:120]}...\"")
    for n in c.get("notes") or []:
        print(f"  * {str(n.get('timestamp'))[:16]} ({n.get('author')}) {n.get('text')}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--show", action="store_true", help="print the contact and exit")
    p.add_argument("--type", choices=VALID_TYPES)
    p.add_argument("--outcome", default="", help="no_answer | spoke | sent | ...")
    p.add_argument("--subject", default="", help="one-line label for the timeline")
    p.add_argument("--body", default="", help="verbatim message text")
    p.add_argument("--body-file", default="", help="read verbatim message text from a file")
    p.add_argument("--note", default="", help="what happened, in Will's words")
    p.add_argument("--date", default="", help="ISO datetime of the touch (default: now)")
    p.add_argument("--contact-status", default="")
    p.add_argument("--contact-preference", default="")
    p.add_argument("--follow-up", default="", help="YYYY-MM-DD next touch due")
    p.add_argument("--follow-up-reason", default="")
    p.add_argument("--follow-up-channel", default="", choices=("",) + VALID_CHANNELS)
    p.add_argument("--clear-follow-up", action="store_true")
    p.add_argument("--phone", default="", help="set/repair the phone number on the contact")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    db = get_client()["system_monitor"]
    email = a.email.lower().strip()

    if a.show:
        show(db, email)
        return 0

    contact = db.crm_contacts.find_one({"email": email})
    if not contact:
        print(f"ERROR: no crm_contacts document for {email} — refusing to create one blind.")
        return 1
    if not a.type and not a.follow_up and not a.clear_follow_up and not a.phone:
        print("ERROR: nothing to do — pass --type, --follow-up, --clear-follow-up or --phone.")
        return 1

    body = a.body
    if a.body_file:
        with open(a.body_file) as fh:
            body = fh.read().strip()

    when = a.date or now_aest()
    set_fields: dict = {"updated_at": now_aest()}
    push: dict = {}

    if a.type:
        comm = {"type": a.type, "date": when, "channel": a.type,
                "subject": a.subject or f"{a.type} — {a.outcome or 'logged'}",
                "outcome": a.outcome, "logged_by": "will"}
        if body:
            comm["body"] = body
        push["communications"] = comm
        set_fields["last_contact_at"] = when

    if a.note:
        push["notes"] = {"text": a.note, "author": "will", "timestamp": when}

    if a.contact_status:
        set_fields["contact_status"] = a.contact_status
    if a.contact_preference:
        set_fields["contact_preference"] = a.contact_preference
    if a.phone:
        set_fields["phone"] = a.phone

    if a.clear_follow_up:
        set_fields["follow_up_at"] = None
        set_fields["follow_up_reason"] = ""
    elif a.follow_up:
        datetime.strptime(a.follow_up, "%Y-%m-%d")  # validate, raises on junk
        set_fields["follow_up_at"] = a.follow_up
        set_fields["follow_up_reason"] = a.follow_up_reason
        set_fields["follow_up_channel"] = a.follow_up_channel or "call"
        set_fields["follow_up_set_at"] = now_aest()

    update: dict = {"$set": set_fields}
    if push:
        update["$push"] = {k: v for k, v in push.items()}

    if a.dry_run:
        import json
        print(json.dumps(update, indent=1, default=str))
        return 0

    res = db.crm_contacts.update_one({"email": email}, update)
    if res.matched_count != 1:
        print(f"ERROR: matched {res.matched_count} documents for {email}")
        return 1
    print(f"Logged against {email}:")
    show(db, email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

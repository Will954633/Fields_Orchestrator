#!/usr/bin/env python3
"""
source_leads_sync.py — funnel every contactable lead from the scattered source
collections into system_monitor.crm_contacts, so nothing with a phone or email is
invisible to the Priority tab.

WHY
---
crm_sync (PostHog visitors) and crm_lead_sync (FB lead ads + email) between them cover
two channels. But leads also land in a handful of smaller collections written by various
website forms and imports — and those were never funnelled into crm_contacts, so a real
person who gave us an email/phone through one of them never appeared on the tracker.
Found 2026-09-04 alongside the Messenger gap.

Collections swept (keyed by email, else phone):
  leads, campaign_leads, lead_signups, subscribers,
  five_property_friday_subscribers, analyse_leads, launch_leads

Upsert is by contact key: if a crm_contacts doc already carries that email/phone (e.g. the
same person came via FB lead ad) it is enriched, not duplicated. Test/internal addresses
are skipped.

Rule 7 / 7b: self-registered heartbeat; if contactable leads exist but any remain absent
from crm_contacts after the run, it raises rather than reporting a false success.

Usage:
  python3 scripts/source_leads_sync.py --dry-run
  python3 scripts/source_leads_sync.py
"""
from __future__ import annotations
import argparse
import os
import sys
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv                       # noqa: E402
load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client                     # noqa: E402
from job_status import job_run                       # noqa: E402

# collection -> the fields that carry contact identity, in the doc's own vocabulary
SOURCES = {
    "leads": {"email": ["email"], "phone": ["phone"], "name": ["name", "owner"]},
    "campaign_leads": {"email": ["email"], "phone": ["phone"], "name": ["name"]},
    "lead_signups": {"email": ["email"], "phone": ["phone"], "name": ["name"]},
    "subscribers": {"email": ["email"], "phone": ["phone"], "name": ["name"]},
    "five_property_friday_subscribers": {"email": ["email"], "phone": [], "name": ["name"]},
    "analyse_leads": {"email": ["email"], "phone": ["phone"], "name": ["name"]},
    "launch_leads": {"email": ["email"], "phone": ["phone"], "name": ["name"]},
}
TEST_EMAILS = {"will@fieldsestate.com.au", "test@tester.com.au",
               "will.simpson@blueoceans.com.au"}


def is_test(name, email, phone):
    """Drop obvious diagnostic rows (e.g. 'test person' / 000110003) that would
    otherwise manufacture a junk contact."""
    if email in TEST_EMAILS:
        return True
    if name and "test" in str(name).lower():
        return True
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if d and set(d) <= {"0", "1"}:   # 000110003 and the like
        return True
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_email(e):
    e = (e or "").strip().lower()
    return e or None


def norm_phone(p):
    if not p:
        return None
    d = "".join(ch for ch in str(p) if ch.isdigit())
    return d if len(d) >= 8 else None


def phone_tail(p):
    p = norm_phone(p)
    return p[-9:] if p else None


def first(doc, keys):
    for k in keys:
        v = doc.get(k)
        if v:
            return v
    return None


def load_crm_index(db):
    """Sets of contact keys already present, so we count true misses not just upserts."""
    emails, phones = set(), set()
    for d in db.crm_contacts.find({}, {"email": 1, "phone": 1}):
        e = norm_email(d.get("email"))
        p = phone_tail(d.get("phone"))
        if e:
            emails.add(e)
        if p:
            phones.add(p)
    return emails, phones


def run(dry_run: bool) -> dict:
    db = get_client()["system_monitor"]
    emails, phones = load_crm_index(db)

    contactable = 0
    missing_before = 0
    upserted = 0
    per_source: dict[str, int] = {}

    for coll, fmap in SOURCES.items():
        added = 0
        for d in db[coll].find({}):
            email = norm_email(first(d, fmap["email"]))
            phone = first(d, fmap["phone"])
            ptail = phone_tail(phone)
            if not email and not ptail:
                continue
            name = first(d, fmap["name"])
            if is_test(name, email, phone):
                continue
            contactable += 1
            present = (email in emails if email else False) or \
                      (ptail in phones if ptail else False)
            if present:
                continue
            missing_before += 1
            if dry_run:
                print(f"  [{coll}] {name or '(no name)'} <{email or phone}>")
                added += 1
                # reserve the key so two docs for the same person count once
                if email:
                    emails.add(email)
                if ptail:
                    phones.add(ptail)
                continue
            match = {"email": email} if email else {"phone": phone}
            set_fields = {"updated_at": _now(),
                          "qualification_reason": f"Form/source lead — {coll}"}
            if name:
                set_fields["name"] = name
            if phone:
                set_fields["phone"] = phone
            db.crm_contacts.update_one(
                match,
                {"$setOnInsert": {**({"email": email} if email else {}),
                                  "created_at": _now(), "first_seen": _now(),
                                  "status": "lead", "source": coll,
                                  "engagement_score": 20},
                 "$set": set_fields,
                 "$addToSet": {"tags": {"$each": ["source_lead", coll]}}},
                upsert=True)
            added += 1
            upserted += 1
            if email:
                emails.add(email)
            if ptail:
                phones.add(ptail)
        if added:
            per_source[coll] = added

    return {"contactable": contactable, "missing_before": missing_before,
            "upserted": upserted, "per_source": per_source}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.dry_run:
        res = run(True)
        print(res)
        return 0

    with job_run("source_leads_sync", cadence_hours=24,
                 title="Source-collection leads → CRM") as beat:
        res = run(False)
        beat.metrics = res
        # Rule 7b: recount misses after writing. Anything still absent means the upsert
        # did not take — a silent drop, not an empty source.
        emails, phones = load_crm_index(get_client()["system_monitor"])
        still_missing = 0
        db = get_client()["system_monitor"]
        for coll, fmap in SOURCES.items():
            for d in db[coll].find({}):
                email = norm_email(first(d, fmap["email"]))
                phone = first(d, fmap["phone"])
                ptail = phone_tail(phone)
                if (not email and not ptail) or \
                        is_test(first(d, fmap["name"]), email, phone):
                    continue
                if not ((email in emails if email else False) or
                        (ptail in phones if ptail else False)):
                    still_missing += 1
        if still_missing:
            raise RuntimeError(
                f"{still_missing} contactable source leads still absent from "
                f"crm_contacts after sync — upserts are silently failing.")
        beat.detail = (f"{res['upserted']} new source leads into CRM "
                       f"(of {res['contactable']} contactable); {res['per_source']}")
        print(beat.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

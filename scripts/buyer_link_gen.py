#!/usr/bin/env python3
"""
buyer_link_gen.py — mint a personalised buyer link for a CRM contact.

A buyer who reached out to us (FB buyer-brief ad, on-site form) has a structured
`lead_brief` on their `system_monitor.crm_contacts` record. This tool mints (or
reuses) their stable opaque `link_token` and assembles

    https://fieldsestate.com.au/for-sale-v3?lead=<link_token>

which, when clicked, preloads the for-sale-v3 feed to their brief (suburb +
bedrooms), unlocks the gated editorial, and binds their on-site session back to
this contact (lead-link-visit.mjs / buyer-prefs.mjs). The assembled URL is stored
on the contact as `buyer_link` so it shows in the leads sheet and can be resent.
The token — never any PII — is all that rides in the URL.

`link_token` and `buyer_link` are both in crm_sync.py's carry-forward allow-list,
so the hourly full-doc replace does not wipe them.

Usage:
    python3 scripts/buyer_link_gen.py --email chang_jennifer@hotmail.com
    python3 scripts/buyer_link_gen.py --email a@x.com --email b@y.com
    python3 scripts/buyer_link_gen.py --all-buyers          # every buyer-brief lead missing a link
    python3 scripts/buyer_link_gen.py --all-buyers --dry-run
"""
import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.env import load_env
from shared.db import get_client

SITE = "https://fieldsestate.com.au"

# FB buyer-brief lead-form tags (see crm_lead_sync.py / fpf_send.py BUYER_BRIEF_FORMS).
BUYER_TAGS = {"fb_lead"}
BUYER_BRIEF_TAG_HINT = "Buyer Brief"


def build_link(token: str) -> str:
    return f"{SITE}/for-sale-v3?lead={token}"


def ensure_link(db, contact, *, dry_run: bool) -> str:
    """Return the buyer link for a contact, minting a link_token + storing
    buyer_link if absent. Idempotent: an existing token/link is reused."""
    tok = contact.get("link_token")
    link = contact.get("buyer_link")
    if tok and link:
        return link
    if not tok:
        tok = uuid.uuid4().hex
    link = build_link(tok)
    if not dry_run:
        db.crm_contacts.update_one(
            {"_id": contact["_id"]},
            {"$set": {"link_token": tok, "buyer_link": link}},
        )
    return link


def is_buyer(contact) -> bool:
    """A contact with a buyer brief we can preload (has area or bedrooms)."""
    b = contact.get("lead_brief") or {}
    if b.get("area") or b.get("bedrooms"):
        return True
    tags = contact.get("tags") or []
    return any(BUYER_BRIEF_TAG_HINT in str(t) for t in tags)


def main():
    ap = argparse.ArgumentParser(description="Mint personalised buyer links")
    ap.add_argument("--email", action="append", default=[],
                    help="Contact email (repeatable)")
    ap.add_argument("--all-buyers", action="store_true",
                    help="All buyer-brief contacts missing a buyer_link")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be minted; write nothing")
    args = ap.parse_args()

    if not args.email and not args.all_buyers:
        ap.error("pass --email <addr> (repeatable) or --all-buyers")

    load_env()
    client = get_client()
    db = client["system_monitor"]

    contacts = []
    for em in args.email:
        c = db.crm_contacts.find_one({"email": em.strip().lower()})
        if not c:
            print(f"  MISS  {em}: no crm_contact")
            continue
        contacts.append(c)

    if args.all_buyers:
        for c in db.crm_contacts.find({"buyer_link": {"$exists": False}}):
            if is_buyer(c):
                contacts.append(c)

    if not contacts:
        print("No matching contacts.")
        return

    print(f"{'DRY-RUN — ' if args.dry_run else ''}minting links for {len(contacts)} contact(s):\n")
    for c in contacts:
        link = ensure_link(db, c, dry_run=args.dry_run)
        b = c.get("lead_brief") or {}
        brief = ", ".join(f"{k}={v}" for k, v in b.items() if v) or "(no brief)"
        print(f"  {c.get('email')}")
        print(f"    brief: {brief}")
        print(f"    link : {link}\n")


if __name__ == "__main__":
    main()

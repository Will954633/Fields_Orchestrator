#!/usr/bin/env python3
"""
backfill_mailer_opens.py — one-time: pin the mailer opens that happened BEFORE the QR
carried a lead token (the OT.1 / OTN.1 batches) to durable CRM contacts against their
addresses, exactly as lead-link-visit.mjs now does automatically for token-era scans.

For each genuine open (detected by mailer_attribution_report.build — same post-lodgement
QA filter and single-attribution logic):
  • if the scanner's device already maps to a contact (e.g. Noel, bound via an email
    token) → ENRICH that contact with offmarket_home + property_address (no duplicate);
  • else → adopt the address into a stable `_id:"mailer:<slug>"` contact;
  • bind the device into lead_web.posthog_distinct_id / distinct_ids so the nightly
    lead_web_activity.py harvests its full journey;
  • stamp mail_log.opened_* for the piece;
  • tag the PostHog PERSON with home_address / is_mailer_recipient so the recipient's
    behaviour is queryable by address (server-side $identify, mirrors the function).

Idempotent: re-runs reuse the mailer:<slug> _id and $addToSet the device. Safe to run
more than once. Default is a DRY RUN; pass --commit to write.

  python3 scripts/backfill_mailer_opens.py            # dry run
  python3 scripts/backfill_mailer_opens.py --commit
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client                 # noqa: E402
from mailer_attribution_report import build      # noqa: E402 (reuse identical open detection)

PH_CAPTURE_URL = "https://us.i.posthog.com/capture/"
PH_INGEST_KEY = (os.environ.get("POSTHOG_INGEST_KEY")
                 or "phc_RQ68rG9adv6NYtoZS4JzmJVzVyOWUfprV9ceHb0nLEs")


def tag_person(distinct_id: str, address: str, slug: str) -> bool:
    """Mirror lead-link-visit.mjs identifyPerson: tag the PostHog person with the home
    this mailer inferred, so 'all behaviour of mailer recipients' is a person filter."""
    body = json.dumps({
        "api_key": PH_INGEST_KEY, "event": "$identify", "distinct_id": distinct_id,
        "properties": {"$set": {"home_address": address, "home_address_slug": slug,
                                "is_mailer_recipient": True},
                       "$set_once": {"first_lead_link_at": datetime.now(timezone.utc).isoformat()}},
    }).encode()
    try:
        req = urllib.request.Request(PH_CAPTURE_URL, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception as e:                                    # non-fatal, like the function
        print(f"      (posthog tag failed, non-fatal: {e})")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="write (default is a dry run)")
    a = ap.parse_args()
    live = a.commit

    db = get_client()["system_monitor"]
    crm, mail_log = db["crm_contacts"], db["mail_log"]
    now = datetime.now(timezone.utc)

    opens = []
    for order, b in build().items():
        for r in b["rows"]:
            if r.get("opened_ts") and r.get("device"):
                opens.append(r)
    print(f"{'COMMIT' if live else 'DRY RUN'} — {len(opens)} genuine opens to backfill\n")

    created = enriched = 0
    for r in opens:
        slug, addr, dev = r["slug"], r["address"], r["device"]
        existing = crm.find_one({"$or": [{"lead_web.distinct_ids": dev},
                                         {"posthog_ids": dev}]})
        if existing:
            action, cid = "ENRICH", existing["_id"]
        else:
            action, cid = "CREATE", f"mailer:{slug}"
        print(f"  [{action}] {addr:<44} dev={dev[:16]}… -> {cid}")

        if not live:
            continue

        if existing:
            crm.update_one({"_id": cid}, {
                "$set": {"property_address": existing.get("property_address") or addr,
                         "offmarket_home.slug": slug, "offmarket_home.address": addr,
                         "offmarket_home.source": "mailer", "offmarket_home.at": now,
                         "lead_web.posthog_distinct_id":
                             (existing.get("lead_web") or {}).get("posthog_distinct_id") or dev,
                         "updated_at": now},
                "$addToSet": {"tags": "mailer_offmarket", "lead_web.distinct_ids": dev}})
            enriched += 1
        else:
            crm.update_one({"_id": cid}, {
                "$setOnInsert": {
                    "_id": cid, "posthog_ids": [], "name": None, "email": None, "phone": None,
                    "source": "mailer_offmarket", "status": "prospect", "owner": "will",
                    "engagement_score": 0, "property_address": addr,
                    "offmarket_home": {"slug": slug, "address": addr, "source": "mailer", "at": now},
                    "qualification_reason": f"Scanned mailer QR → {addr}",
                    "tags": ["mailer_offmarket", "inferred_owner"],
                    "first_seen": now.date().isoformat(), "created_at": now},
                "$set": {"lead_web.posthog_distinct_id": dev, "updated_at": now},
                "$addToSet": {"lead_web.distinct_ids": dev}},
                upsert=True)
            created += 1

        mail_log.update_many({"_id": r["piece_id"]},
                             {"$set": {"crm_contact_id": cid, "opened_distinct_id": dev,
                                       "opened_at": r["opened_ts"].isoformat(), "updated_at": now.isoformat()}})
        tag_person(dev, addr, slug)

    print(f"\n{'WROTE' if live else 'WOULD WRITE'}: {created} created, {enriched} enriched. "
          f"Nightly lead_web_activity.py will harvest each device's full journey onto the contact.")
    if not live:
        print("Re-run with --commit to apply.")


if __name__ == "__main__":
    main()

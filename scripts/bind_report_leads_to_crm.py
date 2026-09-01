#!/usr/bin/env python3
"""
bind_report_leads_to_crm.py — join the "leadpage" property-report leads to their CRM
contact so their full on-site behaviour is logged and viewable.

THE GAP THIS CLOSES
-------------------
When someone clicks one of the Owner-Market carousel ads (or any Analyse-Your-Home
leadpage ad), they land on `/find/<suburb>`, type their address, and
`analyse-your-home-submit` writes a `property_reports` doc for that address carrying the
REAL on-site device id in `owner.posthog_distinct_id` + full first/last-touch attribution.
That is the device<->address join.

Separately, crm_sync creates a `crm_contacts` doc for that same distinct_id (it qualified
on engagement) — but that contact is ANONYMOUS: `lead_web.posthog_distinct_id` is null and
no address is attached. So the device<->behaviour doc and the device<->address doc exist
independently and nothing joins them:
  - `lead_web_activity.py` only harvests contacts with `lead_web.posthog_distinct_id` set,
    so it skips these -> no behaviour log.
  - the `/api/v1/crm-contact` page renders the `lead_web` block -> shows "no linked session".

This script binds them: for each real `property_reports` lead with an
`owner.posthog_distinct_id`, it stamps that distinct_id into the contact's `lead_web`
(+ the address, source and attribution). After that:
  - `lead_web_activity.py` picks it up automatically and writes `lead_web.activity` +
    `lead_web.summary` (the full pageview stream, joined by the indexed distinct_id query),
  - the crm-contact page renders the address + the on-site behaviour,
  - the Priority tab's `crm_link(_id)` already exposes it one-click from the tracker.

All fields written here are in crm_sync's carry-forward allow-list (`lead_web`,
`property_address`, `source`, and `lead_attribution` — the last added 2026-09-02), so the
hourly `replace_one` in crm_sync does not wipe them. See [[home_recognition_personalization]]
LANDMINE 1/2 and [[parked_lead_token_identity_join]].

Runs nightly in `nightly_lead_chain` AFTER crm_sync and BEFORE lead_web_activity.

Usage:
  python3 scripts/bind_report_leads_to_crm.py --dry-run
  python3 scripts/bind_report_leads_to_crm.py
"""
import os
import sys
import argparse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from shared.env import load_env  # noqa: E402
from shared.db import get_client  # noqa: E402
from src.mongo_client_factory import cosmos_retry  # noqa: E402
from crm_sync import contact_id  # noqa: E402  deterministic _id from distinct_id
from job_status import job_run  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def report_leads(sm):
    """Every REAL property_reports lead that carries an on-site device id — the leadpage
    arm (Owner-Market carousel + any other AYH-leadpage campaign). is_test excluded."""
    q = {"is_test": {"$ne": True}, "owner.posthog_distinct_id": {"$ne": None}}
    return list(sm["property_reports"].find(q))


def build_updates(rep: dict, contact: dict | None):
    """The $set to bind this report's device+address onto its contact. First-touch is
    sticky: address / source / attribution are only written when the contact lacks them,
    so a real identified contact is never clobbered by a report bind."""
    owner = rep.get("owner") or {}
    did = owner["posthog_distinct_id"]
    attr = owner.get("attribution") or {}
    ft = attr.get("first_touch") or {}
    campaign = ft.get("utm_campaign") or "ayh_leadpage"
    address = rep.get("address")
    existing = contact or {}

    upd = {
        # The bind that makes lead_web_activity harvest it + the page render it.
        "lead_web.posthog_distinct_id": did,
        "lead_web.landing": (existing.get("lead_web") or {}).get("landing") or "report",
        "lead_web.report_slug": rep.get("slug"),
        "lead_web.source": campaign,
        "lead_web.bound_from": "property_reports",
        "lead_web.bound_at": _now(),
        "updated_at": _now(),
    }
    # Address — only if the contact has none, and never a different one.
    if address and not existing.get("property_address"):
        upd["property_address"] = address
    # Source — only overwrite the generic posthog_sync default, never a real source.
    if existing.get("source") in (None, "", "posthog_sync"):
        upd["source"] = campaign
    # Attribution — only if absent (don't overwrite a FB-lead's richer attribution).
    if not existing.get("lead_attribution"):
        upd["lead_attribution"] = {
            "campaign_name": ft.get("utm_campaign"),
            "adset_name": ft.get("utm_term"),
            "ad_name": ft.get("utm_content"),
            "channel_type": attr.get("channel_type"),
        }
    return did, upd


def run(dry_run: bool) -> dict:
    sm = get_client()["system_monitor"]
    leads = report_leads(sm)
    bound = created = skipped = 0
    for rep in leads:
        did, upd = build_updates(rep, None)
        contact = sm["crm_contacts"].find_one({"posthog_ids": did})
        if contact is None:
            # No contact yet (visitor hasn't crossed crm_sync's engagement threshold).
            # Seed a minimal one keyed by the SAME deterministic _id crm_sync would use,
            # so crm_sync merges into it (never forks) on its next pass.
            cid = contact_id(did)
            if dry_run:
                print(f"  CREATE  {cid}  {rep.get('address')}  did={did[:12]}")
                created += 1
                continue
            base = {
                "_id": cid, "posthog_ids": [did], "primary_posthog_id": did,
                "name": None, "email": None, "phone": None,
                "status": "lead", "owner": "will",
                "created_at": _now(), "first_seen": _now(),
            }
            cosmos_retry(lambda b=base: sm["crm_contacts"].insert_one(b))
            contact = base
            created += 1
        # Recompute updates now that we know the contact's existing state (sticky fields).
        did, upd = build_updates(rep, contact)
        if dry_run:
            print(f"  BIND    {contact['_id']}  {rep.get('address')}  did={did[:12]}  "
                  f"fields={sorted(upd.keys())}")
            bound += 1
            continue
        cosmos_retry(lambda c=contact, u=upd, d=did: sm["crm_contacts"].update_one(
            {"_id": c["_id"]},
            {"$set": u, "$addToSet": {"lead_web.distinct_ids": d}}))
        # Back-reference so the tracker can emit a crm-contact link straight from the report.
        cosmos_retry(lambda r=rep, c=contact: sm["property_reports"].update_one(
            {"_id": r["_id"]}, {"$set": {"owner.crm_contact_id": str(c["_id"])}}))
        bound += 1
    return {"report_leads": len(leads), "bound": bound, "created": created, "skipped": skipped}


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        res = run(dry_run=True)
        print(res)
        return 0

    with job_run("bind_report_leads_to_crm", cadence_hours=24,
                 title="Bind report leads -> CRM (device+address)") as beat:
        res = run(dry_run=False)
        beat.metrics = res
        beat.detail = (f"{res['bound']} report leads bound to a CRM contact "
                       f"({res['created']} contacts seeded)")
        # Rule 7b — assert an outcome. Report leads with a device id EXIST but NONE bound
        # means the join is broken (wrong field, contact lookup failing), not "idle".
        if res["report_leads"] > 0 and res["bound"] == 0:
            raise RuntimeError(
                f"{res['report_leads']} property_reports carry an owner.posthog_distinct_id "
                f"but 0 were bound to a CRM contact — the device<->address join is broken.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

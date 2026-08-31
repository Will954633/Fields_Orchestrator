#!/usr/bin/env python3
"""
lead_web_activity.py — pull each identity-bound LEAD's on-site journey onto their
crm_contact, so the website activity behind a lead is durable (PostHog retains
events only ~a rolling window; the CRM is forever).

The join key is `crm_contacts.lead_web.posthog_distinct_id`, written by
lead-link-visit.mjs when a lead clicks their tokenised SMS/email link (the parked
"lead-token identity join", now live). This reads that key and queries PostHog for
the visitor's pageviews — a targeted, INDEXED `distinct_id IN (...)` query, which
returns fast, unlike the `person.properties.email` full scan that 504s. Result is
stored as `lead_web.activity` and a one-line `lead_web.summary`.

Runs nightly as a step of nightly_lead_chain.py (after crm_sync). Heartbeat
`lead_web_activity` with a Rule-7b assertion: leads are bound but zero produced
activity => the PostHog query is broken, not the leads idle.

Usage:
  python3 scripts/lead_web_activity.py --dry-run
  python3 scripts/lead_web_activity.py
"""
import os
import sys
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")

from shared.db import get_client                 # noqa: E402
from crm_sync import posthog_query               # noqa: E402 (hardened retry/limit helper)
from job_status import job_run                   # noqa: E402


def _now():
    return datetime.now(timezone.utc).isoformat()


def bound_leads(sm):
    """Contacts that have clicked a tokenised link (have a bound distinct_id)."""
    return list(sm["crm_contacts"].find(
        {"lead_web.posthog_distinct_id": {"$ne": None}}))


def ids_for(contact):
    """Every distinct_id this lead's on-site events could live under: the
    pre-identify anonymous id(s) AND the link_token (post-identify events carry the
    token as distinct_id). Both resolve to one PostHog person."""
    lw = contact.get("lead_web") or {}
    ids = set(lw.get("distinct_ids") or [])
    if lw.get("posthog_distinct_id"):
        ids.add(lw["posthog_distinct_id"])
    if contact.get("link_token"):
        ids.add(contact["link_token"])
    return sorted(i for i in ids if i)


def fetch_activity(all_ids):
    """One indexed query for the whole cohort: pageviews + pages per distinct_id."""
    if not all_ids:
        return {}, {}
    idlist = "','".join(i.replace("'", "") for i in all_ids)
    agg = posthog_query(f"""
        SELECT distinct_id,
               countIf(event = '$pageview') AS pageviews,
               count(DISTINCT toDate(timestamp)) AS visit_days,
               min(timestamp) AS first_seen,
               max(timestamp) AS last_seen
        FROM events
        WHERE distinct_id IN ('{idlist}')
        GROUP BY distinct_id
    """)
    pages = posthog_query(f"""
        SELECT distinct_id, properties.$pathname AS path, count() AS n
        FROM events
        WHERE distinct_id IN ('{idlist}') AND event = '$pageview'
        GROUP BY distinct_id, path
        ORDER BY n DESC
    """)
    by_id = {r[0]: {"pageviews": int(r[1] or 0), "visit_days": int(r[2] or 0),
                    "first_seen": str(r[3]), "last_seen": str(r[4])} for r in agg}
    pages_by_id = {}
    for did, path, n in pages:
        pages_by_id.setdefault(did, []).append({"path": path, "count": int(n or 0)})
    return by_id, pages_by_id


def merge_activity(contact, by_id, pages_by_id):
    """Combine every distinct_id belonging to this lead into one activity doc."""
    ids = ids_for(contact)
    pv = days = 0
    firsts, lasts, page_counts = [], [], {}
    for did in ids:
        a = by_id.get(did)
        if not a:
            continue
        pv += a["pageviews"]
        days = max(days, a["visit_days"])
        if a["first_seen"] and a["first_seen"] != "None":
            firsts.append(a["first_seen"])
        if a["last_seen"] and a["last_seen"] != "None":
            lasts.append(a["last_seen"])
        for p in pages_by_id.get(did, []):
            page_counts[p["path"]] = page_counts.get(p["path"], 0) + p["count"]
    if pv == 0 and not page_counts:
        return None
    top_pages = sorted(({"path": k, "count": v} for k, v in page_counts.items()),
                       key=lambda x: -x["count"])[:20]
    return {
        "total_pageviews": pv,
        "visit_days": days,
        "first_seen": min(firsts) if firsts else None,
        "last_seen": max(lasts) if lasts else None,
        "pages_visited": top_pages,
        "refreshed_at": _now(),
    }


def summarise(act):
    if not act:
        return ""
    top = act["pages_visited"][0]["path"] if act["pages_visited"] else "?"
    last = (act.get("last_seen") or "")[:10]
    return (f"{act['total_pageviews']} pageviews over {act['visit_days']} day(s); "
            f"last {last}; top: {top}")


def run(dry_run=False):
    sm = get_client()["system_monitor"]
    leads = bound_leads(sm)
    all_ids = sorted({i for c in leads for i in ids_for(c)})
    by_id, pages_by_id = fetch_activity(all_ids)

    updated = with_activity = 0
    for c in leads:
        act = merge_activity(c, by_id, pages_by_id)
        if not act:
            continue
        with_activity += 1
        if dry_run:
            print(f"  {c.get('name') or c.get('phone') or c.get('email')}: {summarise(act)}")
            continue
        sm["crm_contacts"].update_one(
            {"_id": c["_id"]},
            {"$set": {"lead_web.activity": act,
                      "lead_web.summary": summarise(act),
                      "updated_at": _now()}})
        updated += 1
    return {"bound_leads": len(leads), "with_activity": with_activity, "updated": updated}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.dry_run:
        print(run(dry_run=True))
        return 0

    with job_run("lead_web_activity", cadence_hours=24,
                 title="Lead on-site activity -> CRM") as beat:
        res = run(dry_run=False)
        beat.metrics = res
        # Rule 7b: leads are bound to a distinct_id but NONE produced any activity =>
        # the PostHog query is broken (or every event vanished), not "leads idle".
        # A genuinely empty cohort (no one has clicked a link yet) is bound_leads==0.
        if res["bound_leads"] > 0 and res["with_activity"] == 0:
            raise RuntimeError(
                f"{res['bound_leads']} leads have a bound distinct_id but 0 produced any "
                f"pageviews — PostHog query returned nothing, investigate before trusting.")
        beat.detail = (f"{res['with_activity']}/{res['bound_leads']} bound leads have "
                       f"on-site activity; {res['updated']} updated")
        print(beat.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

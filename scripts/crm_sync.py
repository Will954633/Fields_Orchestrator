#!/home/fields/venv/bin/python3
"""
CRM Contact Sync — daily PostHog → system_monitor.crm_contacts pipeline.

Queries PostHog for visitors meeting engagement thresholds, builds journey
summaries, scores engagement, and upserts unified contact records.

Usage:
    python3 scripts/crm_sync.py                  # Sync last 30 days
    python3 scripts/crm_sync.py --days 90         # Wider lookback
    python3 scripts/crm_sync.py --dry-run         # Preview without writing
    python3 scripts/crm_sync.py --report          # Print CRM summary
    python3 scripts/crm_sync.py --verbose         # Detailed logging
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Add scripts dir for ceo_agent_lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ceo_agent_lib import get_client, load_env_file, now_aest, to_jsonable

AEST = ZoneInfo("Australia/Brisbane")
ROOT = Path("/home/fields/Fields_Orchestrator")

# PostHog config
POSTHOG_PROJECT_ID = "348370"
POSTHOG_QUERY_URL = f"https://us.i.posthog.com/api/projects/{POSTHOG_PROJECT_ID}/query/"

# Known internal PostHog IDs (Will + test accounts)
INTERNAL_IDS = {
    "019d03c0-df65-73a0-a156-8e0b18ba42a4",  # Will — 872 pageviews, /ops
    "019d102e-5fb2-7818-8e2a-99d81b4b4297",  # Will/wife — Balderstone St
    "019d24b3-da5e-7a72-9e6a-b34f118e64c7",  # Will — 86 pageviews, /ops
}

# Qualification thresholds
MIN_VISIT_DAYS = 2
INTENT_EVENTS = ["address_search", "analyse_home_submit_start", "analyse_lead_submitted",
                 "lead_cta_click", "signup_gate_complete", "feed_email_submit"]

# Suburbs for auto-tagging
SUBURBS = ["robina", "burleigh-waters", "varsity-lakes", "burleigh_waters", "varsity_lakes"]


# ---------------------------------------------------------------------------
# PostHog API
# ---------------------------------------------------------------------------

def posthog_query(query_str: str) -> list[list]:
    """Execute a HogQL query against PostHog and return results."""
    api_key = os.environ.get("POSTHOG_PERSONAL_API_KEY") or os.environ.get("POSTHOG_API_KEY")
    if not api_key:
        raise RuntimeError("POSTHOG_API_KEY not set")

    payload = json.dumps({"query": {"kind": "HogQLQuery", "query": query_str}}).encode()
    req = urllib.request.Request(
        POSTHOG_QUERY_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return data.get("results", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        print(f"  PostHog API error {e.code}: {body}")
        return []


def fetch_visitor_data(cutoff_iso: str) -> dict[str, dict]:
    """Fetch pageview and event data, grouped by distinct_id."""
    visitors: dict[str, dict] = defaultdict(lambda: {
        "pageviews": [],
        "visit_dates": set(),
        "pages": defaultdict(int),
        "referrers": set(),
        "utm_sources": set(),
        "devices": set(),
        "intent_events": [],
        "total_pageviews": 0,
    })

    # Query 1: Pageviews — aggregate per visitor
    print("  Fetching pageviews...")
    rows = posthog_query(f"""
SELECT
    distinct_id,
    count() as pvs,
    count(distinct toDate(timestamp)) as visit_days,
    groupUniqArray(toDate(timestamp)) as dates,
    groupUniqArray(properties.$pathname) as paths,
    groupUniqArray(properties.$referring_domain) as refs,
    groupUniqArray(properties.utm_source) as utms,
    groupUniqArray(properties.$device_type) as devices
FROM events
WHERE event = '$pageview'
  AND timestamp > toDateTime('{cutoff_iso}')
  AND properties.is_internal != true
GROUP BY distinct_id
HAVING visit_days >= {MIN_VISIT_DAYS} OR distinct_id IN (
    SELECT distinct distinct_id FROM events
    WHERE event IN ('{("', '".join(INTENT_EVENTS))}')
      AND timestamp > toDateTime('{cutoff_iso}')
)
""")
    for did, pvs, vdays, dates, paths, refs, utms, devices in rows:
        if did in INTERNAL_IDS:
            continue
        v = visitors[did]
        v["total_pageviews"] = pvs
        for d in (dates or []):
            v["visit_dates"].add(str(d))
        for p in (paths or []):
            if p:
                v["pages"][p] += 1
        for r in (refs or []):
            if r and r != "$direct":
                v["referrers"].add(r)
        for u in (utms or []):
            if u:
                v["utm_sources"].add(u)
        for d in (devices or []):
            if d:
                v["devices"].add(d)

    # Query 2: Intent events
    print("  Fetching intent events...")
    event_list = "', '".join(INTENT_EVENTS)
    rows = posthog_query(f"""
SELECT
    distinct_id,
    event,
    timestamp,
    properties.search_query as search_query,
    properties.address as address,
    properties.$pathname as path
FROM events
WHERE event IN ('{event_list}')
  AND timestamp > toDateTime('{cutoff_iso}')
  AND properties.is_internal != true
ORDER BY timestamp ASC
""")
    for did, event, ts, search_q, address, path in rows:
        if did in INTERNAL_IDS:
            continue
        visitors[did]["intent_events"].append({
            "event": event,
            "timestamp": str(ts),
            "search_query": search_q,
            "address": address,
            "path": path,
        })

    # Query 3: Property views for journey enrichment
    print("  Fetching property views...")
    rows = posthog_query(f"""
SELECT
    distinct_id,
    properties.$pathname as path,
    count() as views
FROM events
WHERE event = '$pageview'
  AND properties.$pathname LIKE '/property/%'
  AND timestamp > toDateTime('{cutoff_iso}')
  AND properties.is_internal != true
GROUP BY distinct_id, path
ORDER BY views DESC
""")
    for did, path, views in rows:
        if did in INTERNAL_IDS:
            continue
        # Store property views as intent signals
        if path:
            visitors[did]["intent_events"].append({
                "event": "property_view",
                "path": path,
                "count": views,
            })

    return dict(visitors)


# ---------------------------------------------------------------------------
# Qualification & Scoring
# ---------------------------------------------------------------------------

def qualifies(v: dict) -> tuple[bool, str]:
    """Check if a visitor meets CRM contact thresholds."""
    visit_days = len(v["visit_dates"])
    has_intent = any(e["event"] in INTENT_EVENTS for e in v["intent_events"])
    property_views = sum(1 for e in v["intent_events"] if e.get("event") == "property_view")

    if has_intent:
        intent_name = next(e["event"] for e in v["intent_events"] if e["event"] in INTENT_EVENTS)
        return True, f"intent_event: {intent_name}"
    if visit_days >= MIN_VISIT_DAYS:
        return True, f"{visit_days} visit days"
    return False, ""


def calculate_engagement_score(v: dict) -> tuple[int, dict]:
    """Calculate 0-100 engagement score with breakdown."""
    visit_days = len(v["visit_dates"])
    total_pv = v["total_pageviews"]
    unique_pages = len(v["pages"])

    # Visit frequency (max 30)
    freq_score = min(visit_days * 6, 30)

    # Depth (max 25)
    depth_score = min(int(total_pv * 1.5), 15) + min(unique_pages * 2, 10)

    # Intent signals (max 30)
    intent_score = 0
    has_address_search = any(e["event"] == "address_search" for e in v["intent_events"])
    has_lead_action = any(e["event"] in ("analyse_home_submit_start", "analyse_lead_submitted",
                                          "lead_cta_click", "signup_gate_complete", "feed_email_submit")
                          for e in v["intent_events"])
    property_view_count = sum(1 for e in v["intent_events"] if e.get("event") == "property_view")

    if has_address_search:
        intent_score += 15
    if has_lead_action:
        intent_score += 10
    intent_score += min(property_view_count * 2, 5)
    intent_score = min(intent_score, 30)

    # Recency (max 15)
    if v["visit_dates"]:
        last_visit = max(v["visit_dates"])
        days_ago = (date.today() - date.fromisoformat(last_visit)).days
        if days_ago <= 1:
            recency_score = 15
        elif days_ago <= 3:
            recency_score = 12
        elif days_ago <= 7:
            recency_score = 9
        elif days_ago <= 14:
            recency_score = 5
        elif days_ago <= 30:
            recency_score = 2
        else:
            recency_score = 0
    else:
        recency_score = 0

    total = min(freq_score + depth_score + intent_score + recency_score, 100)
    breakdown = {
        "visit_frequency": freq_score,
        "depth": depth_score,
        "intent_signals": intent_score,
        "recency": recency_score,
    }
    return total, breakdown


def auto_tags(v: dict) -> list[str]:
    """Generate automatic tags from journey data."""
    tags = []
    visit_days = len(v["visit_dates"])

    if visit_days >= 3:
        tags.append("repeat_visitor")
    if visit_days >= 2:
        tags.append("returning")

    # Suburb interest
    for suburb in SUBURBS:
        slug = suburb.replace("_", "-")
        if any(slug in p.lower() or suburb in p.lower() for p in v["pages"]):
            clean = suburb.replace("-", "_").replace(" ", "_").lower()
            tags.append(f"{clean}_interest")

    # Intent tags
    if any(e["event"] == "address_search" for e in v["intent_events"]):
        tags.append("address_searcher")
    if any(e["event"] in ("analyse_home_submit_start", "analyse_lead_submitted") for e in v["intent_events"]):
        tags.append("analyse_home_user")
    if any(e["event"] == "property_view" for e in v["intent_events"]):
        tags.append("property_viewer")

    score, _ = calculate_engagement_score(v)
    if score >= 70:
        tags.append("high_intent")

    return sorted(set(tags))


# ---------------------------------------------------------------------------
# Contact building & DB
# ---------------------------------------------------------------------------

def build_contact_doc(distinct_id: str, v: dict, existing: dict | None = None) -> dict:
    """Build a CRM contact document from visitor data."""
    score, breakdown = calculate_engagement_score(v)
    tags = auto_tags(v)

    # Top pages (sorted by visit count)
    top_pages = sorted(v["pages"].items(), key=lambda x: -x[1])[:20]

    # Key events (deduplicate address_search keystroke spam — keep longest query per session)
    key_events = []
    seen_searches = set()
    for e in v["intent_events"]:
        if e["event"] == "address_search":
            q = e.get("search_query", "")
            if q and len(q) > 5 and q not in seen_searches:
                seen_searches.add(q)
                key_events.append(e)
        elif e["event"] == "property_view":
            key_events.append({"event": "property_view", "path": e.get("path"), "count": e.get("count", 1)})
        else:
            key_events.append(e)

    visit_dates = sorted(v["visit_dates"])
    first_seen = visit_dates[0] if visit_dates else None
    last_seen = visit_dates[-1] if visit_dates else None

    now = now_aest()

    doc = {
        # Identity — preserve existing name/email/etc if already set
        "name": (existing or {}).get("name"),
        "email": (existing or {}).get("email"),
        "phone": (existing or {}).get("phone"),
        "company": (existing or {}).get("company"),
        "role": (existing or {}).get("role"),
        # PostHog
        "posthog_ids": list(set((existing or {}).get("posthog_ids", []) + [distinct_id])),
        "primary_posthog_id": (existing or {}).get("primary_posthog_id", distinct_id),
        # Discovery
        "source": (existing or {}).get("source", "posthog_sync"),
        "qualification_reason": qualifies(v)[1],
        "first_seen": (existing or {}).get("first_seen", first_seen),
        "last_seen": last_seen,
        # Journey
        "journey": {
            "total_pageviews": v["total_pageviews"],
            "visit_days": len(v["visit_dates"]),
            "visit_dates": visit_dates,
            "pages_visited": [{"path": p, "count": c} for p, c in top_pages],
            "key_events": key_events[:30],
            "entry_referrers": sorted(v["referrers"]),
            "utm_sources": sorted(v["utm_sources"]),
            "devices": sorted(v["devices"]),
        },
        # Scoring
        "engagement_score": score,
        "engagement_breakdown": breakdown,
        # CRM state
        "status": (existing or {}).get("status", "lead"),
        "tags": sorted(set((existing or {}).get("tags", []) + tags)),
        "notes": (existing or {}).get("notes", []),
        # Linked records
        "linked_records": (existing or {}).get("linked_records", {}),
        # Metadata
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    return doc


def link_existing_leads(contact: dict, sm) -> dict:
    """Try to match contact against existing lead collections."""
    linked = contact.get("linked_records", {})
    email = contact.get("email")

    if email:
        # Check analyse_leads
        if not linked.get("analyse_leads_id"):
            lead = sm["analyse_leads"].find_one({"email": email})
            if lead:
                linked["analyse_leads_id"] = str(lead["_id"])
                if not contact.get("name") and lead.get("name"):
                    contact["name"] = lead["name"]
                if not contact.get("phone") and lead.get("phone"):
                    contact["phone"] = lead["phone"]

        # Check leads
        if not linked.get("leads_id"):
            lead = sm["leads"].find_one({"email": email})
            if lead:
                linked["leads_id"] = str(lead["_id"])

        # Check lead_signups
        if not linked.get("lead_signups_id"):
            signup = sm["lead_signups"].find_one({"email": email})
            if signup:
                linked["lead_signups_id"] = str(signup["_id"])
                if not contact.get("name") and signup.get("name"):
                    contact["name"] = signup["name"]

    contact["linked_records"] = linked
    return contact


def contact_id(distinct_id: str) -> str:
    """Deterministic _id from primary PostHog ID."""
    return hashlib.sha256(distinct_id.encode()).hexdigest()[:24]


def ensure_indexes(col):
    """Create indexes on crm_contacts."""
    indexes = [
        ("posthog_ids", {}),
        ("email", {"sparse": True}),
        ("status", {}),
        ("engagement_score", {}),
        ("updated_at", {}),
        ("tags", {}),
    ]
    existing = {idx["name"] for idx in col.list_indexes()}
    for field, opts in indexes:
        name = f"{field}_1"
        if name not in existing:
            try:
                col.create_index(field, name=name, **opts)
                print(f"  Created index: {name}")
            except Exception as e:
                print(f"  Index {name} failed: {e}")


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def sync(days: int = 30, dry_run: bool = False, verbose: bool = False):
    """Main sync: PostHog → crm_contacts."""
    load_env_file()
    cutoff = (datetime.now(AEST) - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    print(f"CRM Sync — lookback {days} days (since {cutoff})")

    # Fetch data from PostHog
    visitors = fetch_visitor_data(cutoff)
    print(f"  {len(visitors)} distinct visitors fetched")

    # Qualify
    qualified = {}
    for did, v in visitors.items():
        ok, reason = qualifies(v)
        if ok:
            qualified[did] = v
    print(f"  {len(qualified)} qualify for CRM contact")

    if dry_run:
        print("\n--- DRY RUN (no DB writes) ---")
        for did, v in sorted(qualified.items(), key=lambda x: -calculate_engagement_score(x[1])[0]):
            score, _ = calculate_engagement_score(v)
            tags = auto_tags(v)
            _, reason = qualifies(v)
            name = "Unknown"
            print(f"  [{score:3d}] {did[:16]}... | {len(v['visit_dates'])} days | "
                  f"{v['total_pageviews']} pvs | {reason} | tags: {tags}")
        return

    # DB setup
    client = get_client()
    sm = client["system_monitor"]
    col = sm["crm_contacts"]
    ensure_indexes(col)

    # Fetch existing PostHog person data for known contacts
    created = 0
    updated = 0

    for did, v in qualified.items():
        # Check for existing contact
        existing = col.find_one({"posthog_ids": did})

        doc = build_contact_doc(did, v, existing)
        doc = link_existing_leads(doc, sm)

        doc_id = contact_id(doc["primary_posthog_id"])

        if verbose:
            score = doc["engagement_score"]
            print(f"  {'UPDATE' if existing else 'CREATE'} [{score:3d}] "
                  f"{doc.get('name') or did[:16] + '...'} | "
                  f"{doc['journey']['visit_days']} days | "
                  f"{doc['journey']['total_pageviews']} pvs | "
                  f"tags: {doc['tags']}")

        try:
            result = col.replace_one({"_id": doc_id}, {**doc, "_id": doc_id}, upsert=True)
            if result.upserted_id:
                created += 1
            else:
                updated += 1
        except Exception as e:
            print(f"  ERROR writing {did[:16]}: {e}")
            time.sleep(1)

        time.sleep(0.1)  # gentle on Cosmos RU

    print(f"\nDone: {created} created, {updated} updated, {created + updated} total")


def report():
    """Print CRM summary."""
    load_env_file()
    client = get_client()
    col = client["system_monitor"]["crm_contacts"]

    total = col.count_documents({})
    print(f"\n=== CRM Contacts: {total} ===\n")

    # By status
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    print("By status:")
    for doc in col.aggregate(pipeline):
        print(f"  {doc['_id']}: {doc['count']}")

    # Top by engagement score
    print("\nTop 15 by engagement score:")
    for doc in col.find().sort("engagement_score", -1).limit(15):
        name = doc.get("name") or doc.get("primary_posthog_id", "?")[:16] + "..."
        score = doc.get("engagement_score", 0)
        days = doc.get("journey", {}).get("visit_days", 0)
        pvs = doc.get("journey", {}).get("total_pageviews", 0)
        tags = doc.get("tags", [])
        print(f"  [{score:3d}] {name:<30} | {days} days | {pvs} pvs | {tags}")

    # By tag
    print("\nTag distribution:")
    tag_pipeline = [
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    for doc in col.aggregate(tag_pipeline):
        print(f"  {doc['_id']}: {doc['count']}")


# ---------------------------------------------------------------------------
# Seed known contacts
# ---------------------------------------------------------------------------

def seed_known_contacts():
    """Seed manually identified contacts (Elle Anderson, etc.)."""
    load_env_file()
    client = get_client()
    col = client["system_monitor"]["crm_contacts"]

    known = [
        {
            "name": "Elle Anderson",
            "company": "WhiteFox",
            "role": "real_estate_agent",
            "posthog_ids": [
                "019d575f-dd21-7e58-ac3f-2254feed1e96",
                "019d575e-e0f1-74cc-bf2f-10ab06cb3a22",
            ],
            "primary_posthog_id": "019d575f-dd21-7e58-ac3f-2254feed1e96",
            "source": "manual",
            "status": "contact",
            "tags": ["real_estate_agent", "address_searcher", "manual_id"],
        },
        {
            "name": "Marissa Hegarty",
            "email": "marissahegarty@gmail.com",
            "posthog_ids": [],  # will be matched during sync if she returns
            "primary_posthog_id": "",
            "source": "form_submission",
            "status": "lead",
            "tags": ["analyse_home_user", "lead_signup"],
            "notes": [{"text": "Submitted analyse-your-home form (44/46 Clover Hill Dr, Mudgeeraba). Also signed up via for-sale gate.", "author": "system", "timestamp": "2026-04-07"}],
        },
    ]

    for contact in known:
        pid = contact.get("primary_posthog_id") or contact.get("email", "unknown")
        doc_id = contact_id(pid)

        existing = col.find_one({"_id": doc_id})
        if existing:
            # Merge — don't overwrite journey data
            for key in ("name", "company", "role", "email", "phone", "source", "status"):
                if contact.get(key):
                    existing[key] = contact[key]
            existing["tags"] = sorted(set(existing.get("tags", []) + contact.get("tags", [])))
            existing["posthog_ids"] = sorted(set(existing.get("posthog_ids", []) + contact.get("posthog_ids", [])))
            if contact.get("notes"):
                existing.setdefault("notes", []).extend(contact["notes"])
            existing["updated_at"] = now_aest()
            col.replace_one({"_id": doc_id}, existing)
            print(f"  Updated: {contact['name']}")
        else:
            now = now_aest()
            doc = {
                "_id": doc_id,
                "name": contact.get("name"),
                "email": contact.get("email"),
                "phone": contact.get("phone"),
                "company": contact.get("company"),
                "role": contact.get("role"),
                "posthog_ids": contact.get("posthog_ids", []),
                "primary_posthog_id": contact.get("primary_posthog_id", ""),
                "source": contact.get("source", "manual"),
                "qualification_reason": "manual",
                "first_seen": None,
                "last_seen": None,
                "journey": {"total_pageviews": 0, "visit_days": 0, "visit_dates": [],
                            "pages_visited": [], "key_events": [], "entry_referrers": [],
                            "utm_sources": [], "devices": []},
                "engagement_score": 0,
                "engagement_breakdown": {"visit_frequency": 0, "depth": 0, "intent_signals": 0, "recency": 0},
                "status": contact.get("status", "lead"),
                "tags": contact.get("tags", []),
                "notes": contact.get("notes", []),
                "linked_records": {},
                "created_at": now,
                "updated_at": now,
            }
            col.insert_one(doc)
            print(f"  Created: {contact['name']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CRM Contact Sync from PostHog")
    parser.add_argument("--days", type=int, default=30, help="Lookback days (default 30)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--report", action="store_true", help="Print CRM summary")
    parser.add_argument("--seed", action="store_true", help="Seed known contacts")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    args = parser.parse_args()

    if args.report:
        report()
    elif args.seed:
        seed_known_contacts()
    else:
        sync(days=args.days, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()

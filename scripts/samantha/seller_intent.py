#!/usr/bin/env python3
"""
seller_intent.py — a CRM enrichment layer "over the top" of lead_worklist.

For each person in the worklist it cross-references two things the base
lead_intelligence pipeline does NOT connect:

  1. Their OWN property's live listing status, and — crucially — HOW LONG it has
     been for sale (the base pipeline's `status_age_days` measures how fresh OUR
     data is, not time-on-market; this computes real days-on-market).
  2. Every OTHER current listing they viewed in their PostHog journey
     (organic_journeys.pages -> /property/, /your-home/, /off-market/, /sold/
     slugs -> resolved to the live listing + its status/price/days-on-market).

It then draws a seller-intent conclusion (Will 2026-07-28):
  - Own home FOR SALE and long on market   -> likely frustrated vendor /
    second-opinion candidate (e.g. 41 Quambone St Worongary: 364 days at
    $5.15-5.65M with Harcourts).
  - Own home NOT listed but viewing live listings -> probable seller weighing a
    move / researching the market -> pre-market approach candidate.

Non-invasive: writes ONLY `lead_worklist.seller_intent`. It never touches the
base pipeline's priority/reason/signals (owned by lead_intelligence.py) or the
human-dismissal fields.

Usage:
  python3 scripts/samantha/seller_intent.py --address quambone --dry-run
  python3 scripts/samantha/seller_intent.py --lead-key "addr:41quambone..."
  python3 scripts/samantha/seller_intent.py --all
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from shared.db import get_client  # noqa: E402

try:
    from src.mongo_client_factory import cosmos_retry  # noqa: E402
except Exception:  # pragma: no cover
    def cosmos_retry(fn):
        return fn()

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None

NOW = datetime.now(timezone.utc)
STALE_DOM_DAYS = 90  # a listing on market longer than this reads as "stale / frustrated vendor"

# Paths that point at a specific property (the slug is the last segment).
LISTING_PATH_RE = re.compile(
    r"^/(?:property|sold|off-market|your-home|analyse-your-home/building)/([a-z0-9][a-z0-9\-]+?)/?$"
)


# ------------------------------------------------------------------ helpers ---
def _dom_from_listing(d: dict):
    """Days the property has been on market. Prefer first_listed_timestamp (accurate
    to today); fall back to the scraped days_on_domain."""
    ts = d.get("first_listed_timestamp")
    if ts:
        try:
            dt = datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")
            return (NOW.replace(tzinfo=None) - dt).days
        except Exception:
            pass
    try:
        return int(d.get("days_on_domain"))
    except Exception:
        return None


def _price_display(d: dict):
    return d.get("price") or d.get("listing_price") or None


def build_suburb_index(gc_db):
    """[(hyphenated-suburb, collection_name)] sorted longest-first, for slug suffix match."""
    skip = ("precomputed", "address_", "system", "fci", "indexed", "_")
    colls = [x for x in gc_db.list_collection_names() if not x.startswith(skip)]
    pairs = [(c.replace("_", "-"), c) for c in colls]
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


def resolve_slug(gc_db, slug: str, suburb_index):
    """Resolve a url_slug to its live Gold_Coast listing doc (any GC suburb)."""
    if not slug:
        return None
    for hy, coll in suburb_index:
        if slug == hy or slug.endswith("-" + hy):
            d = gc_db[coll].find_one({"url_slug": slug})
            if d:
                return d
            break  # suburb matched but slug not found — don't scan every collection
    return None


def listing_brief(d: dict):
    if not d:
        return None
    status = d.get("listing_status")
    return {
        "url_slug": d.get("url_slug"),
        "address": d.get("address"),
        "suburb": d.get("suburb") or d.get("LOCALITY"),
        "listing_status": status,
        "price": _price_display(d),
        "days_on_market": _dom_from_listing(d) if status == "for_sale" else None,
        "bedrooms": d.get("bedrooms") or d.get("BEDROOMS"),
        "agency": d.get("agency"),
    }


def extract_listing_slugs(pages):
    seen, out = set(), []
    for p in pages or []:
        if not isinstance(p, str):
            continue
        m = LISTING_PATH_RE.match(p.split("?")[0])
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def lead_distinct_ids(lead: dict, sm) -> set:
    """Every PostHog distinct_id we can tie to this lead (report owner, extra, offmarket)."""
    ids = set()
    ex = lead.get("extra") or {}
    if ex.get("posthog_distinct_id"):
        ids.add(ex["posthog_distinct_id"])
    for o in lead.get("origins") or []:
        if o.get("collection") == "property_reports" and ObjectId:
            try:
                rep = sm["property_reports"].find_one(
                    {"_id": ObjectId(o["id"])}, {"owner.posthog_distinct_id": 1})
                did = ((rep or {}).get("owner") or {}).get("posthog_distinct_id")
                if did:
                    ids.add(did)
            except Exception:
                pass
    lk = str(lead.get("lead_key", ""))
    if lk.startswith("offmarket_view:"):
        ids.add(lk.split(":", 1)[1])
    return ids


def journeys_for(sm, distinct_ids):
    pages, sessions = [], 0
    if not distinct_ids:
        return pages, sessions
    for j in sm["organic_journeys"].find({"distinct_id": {"$in": list(distinct_ids)}}):
        sessions += 1
        pages.extend(j.get("pages") or [])
    return pages, sessions


def own_property_brief(lead: dict, gc_db, suburb_index):
    """Resolve the lead's OWN home -> (brief, own_slug).

    1st choice: the report_slug they generated (full gc_doc -> real days-on-market).
    Fallback:   the base pipeline's already-resolved `property` sub-doc (gives the
                listing STATUS + price for address-only leads, but no days-on-market).
    """
    slug = (lead.get("extra") or {}).get("report_slug")
    d = resolve_slug(gc_db, slug, suburb_index) if slug else None
    if d:
        return listing_brief(d), slug
    p = lead.get("property") or {}
    if p.get("resolved_property_id"):
        return {
            "url_slug": None,
            "address": lead.get("address"),
            "suburb": p.get("suburb"),
            "listing_status": p.get("listing_status"),
            "price": p.get("price"),
            "days_on_market": None,  # unavailable without the report slug -> full doc
            "bedrooms": p.get("bedrooms"),
            "resolved_via": "base_pipeline",
        }, None
    return None, None


def conclude(own, current_viewed, generated_minisite):
    own_status = (own or {}).get("listing_status")
    dom = (own or {}).get("days_on_market")
    n = len(current_viewed)
    addrs = ", ".join(v["address"] for v in current_viewed if v.get("address"))[:200]

    if own_status == "for_sale":
        if dom is not None and dom >= STALE_DOM_DAYS:
            return ("on_market_stale",
                    f"Own home has been FOR SALE {dom} days ({(own or {}).get('price')}). "
                    "Long on market + actively researching Fields = likely frustrated vendor, "
                    "second-opinion / re-list candidate. Verify listing is fresh before any contact.")
        return ("on_market_active",
                f"Own home is FOR SALE ({dom}d on market, {(own or {}).get('price')}) — active campaign. "
                "Track the listing; not a pre-market seller.")
    if own_status == "withdrawn":
        return ("pre_market_withdrawn",
                "Own home recently WITHDRAWN from market — wait-and-see pre-market seller. High-intent.")

    own_resolved = own is not None  # we actually identified their home
    if own_resolved:
        # Home identified and NOT currently for sale/withdrawn (never-listed, sold, etc.)
        if n >= 1:
            return ("browsing_while_unlisted",
                    f"Own home is NOT currently listed, yet viewed {n} live listing(s) [{addrs}]. "
                    "Strong 'weighing a move / thinking of selling' signal — pre-market approach candidate."
                    + (" Also generated their own valuation mini-site." if generated_minisite else ""))
        return ("no_cross_signal", "Home identified, not listed, no active-listing cross-signal yet.")

    # We could NOT identify their home — a viewed listing is a weaker (home-unknown) signal.
    if n >= 1:
        return ("viewing_listings_home_unknown",
                f"Viewed {n} live listing(s) [{addrs}] but we have not tied a home to this person — "
                "could be a buyer, or a seller we can't yet confirm. Enrich identity before acting.")
    return ("no_cross_signal", "No active-listing cross-signal yet.")


def analyze(lead: dict, sm, gc_db, suburb_index) -> dict:
    dids = lead_distinct_ids(lead, sm)
    pages, sessions = journeys_for(sm, dids)
    own, own_slug = own_property_brief(lead, gc_db, suburb_index)

    viewed = []
    for s in extract_listing_slugs(pages):
        if own_slug and s == own_slug:
            continue
        d = resolve_slug(gc_db, s, suburb_index)
        viewed.append(listing_brief(d) if d else {
            "url_slug": s, "address": s.replace("-", " ").title(),
            "listing_status": "unresolved", "price": None, "days_on_market": None})
    current_viewed = [v for v in viewed if v.get("listing_status") == "for_sale"]
    generated_minisite = any(o.get("collection") == "property_reports"
                             for o in lead.get("origins") or [])
    label, reason = conclude(own, current_viewed, generated_minisite)
    return {
        "label": label,
        "conclusion": reason,
        "own_property": own,
        "listings_viewed": viewed,
        "current_listings_viewed": current_viewed,
        "n_current_listings_viewed": len(current_viewed),
        "journey_sessions": sessions,
        "generated_own_minisite": generated_minisite,
        "computed_at": NOW,
    }


def run(query: dict, dry_run: bool = False, limit: int = 0) -> int:
    c = get_client()
    sm = c["system_monitor"]
    gc_db = c["Gold_Coast"]
    suburb_index = build_suburb_index(gc_db)

    leads = list(sm["lead_worklist"].find(query))
    if limit:
        leads = leads[:limit]

    n = hits = 0
    for lead in leads:
        si = analyze(lead, sm, gc_db, suburb_index)
        n += 1
        if si["label"] != "no_cross_signal":
            hits += 1
        own = si["own_property"] or {}
        line = (f"[{si['label']:>22}] {(lead.get('address') or lead.get('lead_key'))[:44]:<44} "
                f"own={own.get('listing_status')} dom={own.get('days_on_market')} "
                f"| current_viewed={si['n_current_listings_viewed']}")
        print(line)
        if not dry_run:
            cosmos_retry(lambda: sm["lead_worklist"].update_one(
                {"_id": lead["_id"]}, {"$set": {"seller_intent": si}}))
    print(f"\nseller_intent: {n} leads processed, {hits} with a cross-signal, "
          f"{'DRY-RUN (nothing written)' if dry_run else 'written to lead_worklist.seller_intent'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead-key")
    ap.add_argument("--address", help="regex match on lead address")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if args.lead_key:
        q = {"lead_key": args.lead_key}
    elif args.address:
        q = {"address": {"$regex": re.escape(args.address), "$options": "i"}}
    elif args.all:
        q = {}
    else:
        ap.error("pass --lead-key, --address, or --all")
    return run(q, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())

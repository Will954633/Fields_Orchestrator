#!/usr/bin/env python3
"""
offmarket_discovery_nightly.py — demand-driven builder for the off-market
Discovery deck (the cinematic scroll page served at /off-market/<slug>).

Precomputing all ~26k eligible homes is pointless (~17 off-market views/day),
so coverage FOLLOWS DEMAND: we build a Discovery doc only for homes people
actually look up. The demand set is the union of

  1. crm_contacts.offmarket_home          — the PERMANENT google->/off-market
                                             owner-lookup signal (offmarket_home_signal.py)
  2. organic_journeys off-market sessions — recent (rolling ~60d) /off-market
                                             pageviews, so brand-new lookups get
                                             a deck by the next nightly run.

For each demand slug we (a) skip it unless it is loader-eligible (a genuinely
off-market home — not for_sale / under_contract / sold within 12 months, which
the React loader 301s to /property anyway), then (b) build_one() + upsert with
--delta semantics (unchanged source_hash is skipped). The React loader renders
the deck when a doc exists and falls back to the current off-market page when
it does not, so missing coverage never breaks a page — it just means "not yet".

Run once at creation to backfill, then nightly via cron. Wrapped in job_run so
it self-reports on the Systems Health "Process Registry" (CLAUDE.md Rule 7).

  python3 offmarket_discovery_nightly.py                 # full demand set
  python3 offmarket_discovery_nightly.py --limit 25      # staged backfill
  python3 offmarket_discovery_nightly.py --dry-run       # list, don't build
"""
import re
import sys
import time
import argparse
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

import offmarket_discovery_build as ODB
from job_status import job_run

CORE = ["robina", "varsity_lakes", "burleigh_waters"]
SOLD_THRESHOLD_MONTHS = 12  # mirror the React loader (off-market.$slug.tsx)

# Houses only — same policy as the off-market sitemap/index (generate-sitemap.mjs).
# The Discovery engine assumes house features (land, floor, green boundary); units
# would get a degraded deck, so they keep the current off-market page (fallback).
NON_HOUSE_TYPES = {
    "Townhouse", "Apartment", "Apartment / Unit / Flat", "Unit", "Flat",
    "Duplex", "Villa", "Terrace", "Semi-Detached", "Studio",
    "Retirement Living", "New Apartments / Off the Plan",
}
UNIT_ADDR_RE = re.compile(r"\d+\s*/\s*\d+")  # "12/3 …" unit addresses
# Leading "unit-street" double number in the slug ("1-48-glen-eagles-…" = 1/48),
# which Will flagged as not-a-house even when property_type is missing.
UNIT_SLUG_RE = re.compile(r"^\d+-\d+-")


def _months_since(ds):
    if not ds:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(ds).replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return (now.year - d.year) * 12 + (now.month - d.month)
    except Exception:
        return None


def _gc():
    from src.mongo_client_factory import get_mongo_client
    return get_mongo_client()["Gold_Coast"]


def _sm():
    from src.mongo_client_factory import get_mongo_client
    return get_mongo_client()["system_monitor"]


def demand_slugs():
    """Union of permanent owner-lookup signal + recent off-market pageviews."""
    sm = _sm()
    names = set(sm.list_collection_names())
    slugs = set()
    if "crm_contacts" in names:
        for d in sm["crm_contacts"].find(
            {"offmarket_home": {"$exists": True}}, {"offmarket_home": 1}
        ):
            om = d.get("offmarket_home") or {}
            if om.get("slug"):
                slugs.add(om["slug"])
            for s in (om.get("slugs") or []):
                slugs.add(s)
    if "organic_journeys" in names:
        for d in sm["organic_journeys"].find(
            {"is_offmarket": True},
            {"pages": 1, "entry_path": 1, "pattern_address": 1, "timeline": 1},
        ):
            blob = [d.get("entry_path"), d.get("pattern_address")]
            for k in ("pages", "timeline"):
                v = d.get(k)
                if isinstance(v, list):
                    for x in v:
                        blob.append(x if isinstance(x, str)
                                    else (x.get("path") or x.get("url") if isinstance(x, dict) else ""))
            for p in blob:
                m = re.search(r"/off-market/([a-z0-9][a-z0-9-]+)", str(p or ""))
                if m:
                    slugs.add(m.group(1))
    return slugs


def eligible(slug):
    """True when the React off-market loader would render (not 301) this slug."""
    if UNIT_SLUG_RE.match(slug):
        return False
    gc = _gc()
    for c in CORE:
        r = gc[c].find_one(
            {"url_slug": slug},
            {"listing_status": 1, "sold_date": 1, "sale_date": 1,
             "property_type": 1, "building_type": 1, "address": 1},
        )
        if not r:
            continue
        ls = r.get("listing_status")
        if ls in ("for_sale", "under_contract"):
            return False
        if ls == "sold":
            ms = _months_since(r.get("sold_date") or r.get("sale_date"))
            if ms is None or ms < SOLD_THRESHOLD_MONTHS:
                return False
        # houses only (mirror off-market index policy)
        if r.get("property_type") in NON_HOUSE_TYPES or r.get("building_type") in NON_HOUSE_TYPES:
            return False
        if UNIT_ADDR_RE.search(str(r.get("address") or "")):
            return False
        return True
    return False  # not in a core collection -> out of scope for now


def run(limit=None, dry_run=False):
    with job_run("offmarket_discovery_nightly", cadence_hours=24,
                 title="Off-Market Discovery Deck (demand build)") as beat:
        demand = sorted(demand_slugs())
        elig = [s for s in demand if eligible(s)]
        if limit:
            elig = elig[:limit]
        print(f"demand={len(demand)}  eligible={len(elig)}"
              + (f"  (capped to {limit})" if limit else ""), file=sys.stderr)
        if dry_run:
            for s in elig:
                print("  •", s)
            beat.detail = f"dry-run: {len(elig)} eligible of {len(demand)} demand"
            beat.metrics = {"demand": len(demand), "eligible": len(elig)}
            return
        coll = ODB._mongo()
        built = skipped = failed = 0
        t0 = time.time()
        for slug in elig:
            try:
                doc = ODB.build_one(slug, rebuild=True)
            except Exception as e:
                print(f"  ✗ {slug}: {e}", file=sys.stderr)
                failed += 1
                continue
            cur = coll.find_one({"slug": slug}, {"source_hash": 1})
            if cur and cur.get("source_hash") == doc["source_hash"]:
                skipped += 1
                continue
            ODB.upsert(doc)
            built += 1
            print(f"  ✓ {slug:44} lead={doc['lead_angle']}", file=sys.stderr)
        dt = int(time.time() - t0)
        print(f"\nbuilt={built} skipped={skipped} failed={failed} in {dt}s", file=sys.stderr)
        beat.detail = f"built {built}, skipped {skipped}, failed {failed} of {len(elig)} eligible"
        beat.metrics = {"demand": len(demand), "eligible": len(elig),
                        "built": built, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)

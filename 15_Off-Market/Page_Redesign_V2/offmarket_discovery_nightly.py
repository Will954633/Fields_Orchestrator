#!/usr/bin/env python3
"""
offmarket_discovery_nightly.py — full-coverage builder for the off-market
Discovery deck (the cinematic scroll page served at /off-market/<slug>).

COVERAGE = THE INDEXED OFF-MARKET SET. Every off-market URL we submit to Google
must render the new design, so the target is EXACTLY the sitemap's
getOffMarketUrls() criteria (generate-sitemap.mjs) — the sale-history tier:
standalone houses, non-waterfront, not for_sale/under_contract, with a recorded
sale (never-listed cadastral with enriched_data.transactions, OR sold 12+ months
ago with its own sale_price/sold_date). ~14.6k homes across the core suburbs.
Keeping this 1:1 with the sitemap means "indexed → deck" is guaranteed.

INCREMENTAL + RESUMABLE. We load every existing doc's generated_at once, then
build a home only when it has NO doc yet OR the property was re-enriched after
its doc was built (enriched_data.last_enriched > generated_at). So the FIRST run
backfills the whole set (~hours, sequential ~1s/home; each upsert makes that home
live immediately), and every night after only touches new/changed homes (cheap).
Interrupted? Just re-run — already-built fresh docs are skipped.

The React loader (off-market.$slug.tsx) renders the deck when a doc exists and
falls back to the classic off-market page when it does not, so partial coverage
never breaks a page. Wrapped in job_run (CLAUDE.md Rule 7) — heartbeat on the
Systems Health Process Registry.

  python3 offmarket_discovery_nightly.py                 # build missing/stale
  python3 offmarket_discovery_nightly.py --limit 50      # staged
  python3 offmarket_discovery_nightly.py --rebuild-all   # force rebuild every home
  python3 offmarket_discovery_nightly.py --dry-run       # count only
"""
import sys
import time
import argparse
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

import re as _re
import offmarket_discovery_build as ODB
from job_status import job_run

CORE = ["robina", "varsity_lakes", "burleigh_waters"]

# Mirror generate-sitemap.mjs getOffMarketUrls() EXACTLY so deck coverage == index.
NON_HOUSE_TYPES = [
    "Townhouse", "Apartment", "Apartment / Unit / Flat", "Unit", "Flat",
    "Duplex", "Villa", "Terrace", "Semi-Detached", "Studio",
    "Retirement Living", "New Apartments / Off the Plan",
    "Land", "Vacant land", "Industrial", "Development Site",
    "Leisure", "Sport", "Other", "Farm",
]
UNIT_ADDR_RE = _re.compile(r"\d+\s*/\s*\d+")


def _gc():
    from src.mongo_client_factory import get_mongo_client
    return get_mongo_client()["Gold_Coast"]


def indexed_query():
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=int(12 * 30.44))).strftime("%Y-%m-%d")
    return {
        "listing_status": {"$nin": ["for_sale", "under_contract"]},
        "url_slug": {"$exists": True, "$nin": [None, ""]},
        "is_waterfront": {"$ne": True},
        "property_type": {"$nin": NON_HOUSE_TYPES},
        "building_type": {"$nin": NON_HOUSE_TYPES},
        "address": {"$not": UNIT_ADDR_RE},
        "$or": [
            {"listing_status": {"$ne": "sold"}, "enriched_data.transactions.0": {"$exists": True}},
            {"listing_status": "sold", "sale_price": {"$exists": True, "$ne": None},
             "sold_date": {"$lte": cutoff}},
        ],
    }


def indexed_homes():
    """Yield (slug, last_enriched) for every indexed off-market home."""
    gc = _gc()
    q = indexed_query()
    for c in CORE:
        for r in gc[c].find(q, {"url_slug": 1, "enriched_data.last_enriched": 1}):
            slug = r.get("url_slug")
            if not slug:
                continue
            le = (r.get("enriched_data") or {}).get("last_enriched")
            yield slug, le


def existing_generated_at():
    """{slug: generated_at} for docs already built — one pass, cheap."""
    coll = ODB._mongo()
    return {d["slug"]: d.get("generated_at", "")
            for d in coll.find({}, {"slug": 1, "generated_at": 1})}


def _needs_build(slug, last_enriched, have, rebuild_all):
    if rebuild_all:
        return True
    gen = have.get(slug)
    if gen is None:            # no doc yet
        return True
    if last_enriched and str(last_enriched) > str(gen):  # re-enriched since build
        return True
    return False


def _build_loop(todo, tag=""):
    """Build + upsert each home; returns (built, failed, seconds)."""
    built = failed = 0
    t0 = time.time()
    n = len(todo)
    for i, (slug, _le) in enumerate(todo, 1):
        try:
            doc = ODB.build_one(slug, rebuild=True)
            ODB.upsert(doc)
            built += 1
        except Exception as e:
            print(f"  ✗ [{tag}] {slug}: {e}", file=sys.stderr)
            failed += 1
        if i % 200 == 0:
            rate = i / max(1e-6, time.time() - t0)
            eta = int((n - i) / max(1e-6, rate))
            print(f"  … [{tag}] {i}/{n}  built={built} failed={failed}  "
                  f"{rate:.1f}/s  eta={eta // 60}m", file=sys.stderr)
    return built, failed, int(time.time() - t0)


def run(limit=None, rebuild_all=False, dry_run=False, shard=None):
    # shard = (i, N): process only homes whose position ≡ i (mod N). Lets us run
    # N parallel processes (each its own Mongo client — separate processes, no
    # fork) to cut the initial ~14.6k backfill from latency-bound hours to ~1/N.
    # Skip job_run heartbeat for shard workers (a shard isn't "the job"); the
    # unsharded nightly run owns the heartbeat.
    if shard is not None:
        homes = sorted(indexed_homes())
        have = existing_generated_at()
        todo = [(s, le) for (s, le) in homes if _needs_build(s, le, have, rebuild_all)]
        i, N = shard
        todo = [t for k, t in enumerate(todo) if k % N == i]
        _build_loop(todo, tag=f"shard{i}/{N}")
        return
    with job_run("offmarket_discovery_nightly", cadence_hours=24,
                 title="Off-Market Discovery Deck (full indexed coverage)") as beat:
        homes = list(indexed_homes())
        have = existing_generated_at()
        todo = [(s, le) for (s, le) in homes if _needs_build(s, le, have, rebuild_all)]
        if limit:
            todo = todo[:limit]
        total_indexed = len(homes)
        print(f"indexed={total_indexed}  have_docs={len(have)}  to_build={len(todo)}"
              + (f"  (capped {limit})" if limit else ""), file=sys.stderr)
        if dry_run:
            beat.detail = f"dry-run: {len(todo)} to build of {total_indexed} indexed"
            beat.metrics = {"indexed": total_indexed, "have": len(have), "to_build": len(todo)}
            return

        built, failed, dt = _build_loop(todo, tag="main")
        cov = len(existing_generated_at())  # coverage after this run
        print(f"\nbuilt={built} failed={failed} in {dt}s  |  coverage={cov}/{total_indexed}", file=sys.stderr)
        beat.detail = (f"built {built}, failed {failed}; coverage {cov}/{total_indexed} indexed")
        beat.metrics = {"indexed": total_indexed, "built": built, "failed": failed,
                        "coverage": cov, "seconds": dt}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rebuild-all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--shard", default=None, help='"i/N" — build only homes where index%%N==i (parallel workers)')
    args = ap.parse_args()
    shard = None
    if args.shard:
        i, N = args.shard.split("/")
        shard = (int(i), int(N))
    run(limit=args.limit, rebuild_all=args.rebuild_all, dry_run=args.dry_run, shard=shard)

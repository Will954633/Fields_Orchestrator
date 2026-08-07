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

# EXPANSION suburbs are NOT hardcoded here. generate-sitemap.mjs release-gates them
# (`EXPANSION_SUBURBS` ∩ the Gold_Coast.offmarket_sitemap_release config doc: a
# suburb with no limit contributes 0 URLs), so the config doc's keys are a strict
# SUPERSET of what the sitemap can ever emit. Deriving from it here makes
# "builder ⊇ sitemap" hold no matter which side someone edits — the 2026-07-29
# Nerang drift (985 indexed URLs, 0 decks → old page served) came from this list
# being a second, independently-maintained copy. See fix-history [OFFMARKET-DECK-EXPANSION-DRIFT].
#
# We build the WHOLE expansion suburb, not just the released slice. The gate exists
# to meter Google's crawl exposure, not to decide what's built; building ahead means
# a home's deck is ready BEFORE its URL is ever submitted, and we never have to
# replicate the sitemap's `sort({_id:1}).limit(N)` ordering to stay in sync.
#
# FROZEN suburbs (config doc `frozen: [...]`) are the exception, added 2026-08-01 when
# Nerang was pulled back to concentrate on the southern core. A frozen suburb:
#   - is NOT built any further (no new decks, and the release limit never widens), but
#   - KEEPS its already-released slice live and in the sitemap — generate-sitemap.mjs
#     reads `limits` and is deliberately left untouched by freezing, so the URLs Google
#     has already indexed keep resolving to a real deck instead of being orphaned.
# Because the builder no longer covers the whole suburb, "builder ⊇ sitemap" would stop
# holding by construction — so the coverage assertion keeps watching the RELEASED SLICE
# of every frozen suburb (see watched_homes). Freezing must never turn into blindness:
# a frozen suburb losing a deck is the exact 2026-07-29 failure (indexed URL → old
# classic page), and it has to stay loud. To unfreeze, drop the name from `frozen`.
RELEASE_CFG = ("offmarket_sitemap_release", "release")


def _release_cfg(gc=None):
    try:
        coll, _id = RELEASE_CFG
        db = _gc() if gc is None else gc   # pymongo Database has no __bool__ — never `gc or …`
        return db[coll].find_one({"_id": _id}) or {}
    except Exception as e:
        print(f"(release config unreadable, core suburbs only: {e})", file=sys.stderr)
        return {}


def expansion_suburbs(gc=None):
    """Expansion suburbs we still BUILD (released, minus frozen)."""
    cfg = _release_cfg(gc)
    frozen = set(cfg.get("frozen") or [])
    return [s for s in (cfg.get("limits") or {}) if s not in CORE and s not in frozen]


def frozen_suburbs(gc=None):
    """{suburb: released_limit} — built no further, but still watched and still served."""
    cfg = _release_cfg(gc)
    limits = cfg.get("limits") or {}
    return {s: limits.get(s) or 0 for s in (cfg.get("frozen") or []) if s not in CORE}


def target_suburbs(gc=None):
    return CORE + expansion_suburbs(gc)


# A residual coverage gap this large means a whole suburb (or a systemic query
# mismatch) is missing, not the handful of per-home build failures we tolerate.
# Crossing it raises -> status=error on the Systems Health Process Registry.
COVERAGE_GAP_TOLERANCE = 25

# Decks missing `intro_tokens` (no matrix intro — the page opens cold on card 00).
# Steady state is 0 now that tokens are written at build time; a small allowance
# absorbs per-home token failures without turning the whole job red.
INTRO_GAP_TOLERANCE = 50

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
        # Address-identity state, both written by scripts/flag_multilot_offmarket.py.
        # Must stay in lockstep with getOffMarketUrls() in generate-sitemap.mjs and
        # meta() in off-market.$slug.tsx.
        #   offmarket_multilot          — another record IS the published entity
        #                                 (duplicate/redundant; rename to
        #                                 offmarket_entity_duplicate is planned)
        #   offmarket_entity_unresolved — we cannot yet say which entity the
        #                                 address-level content belongs to
        # NOTE: this function answers "what is published NOW", so excluding both is
        # correct here — but it must NEVER be used to discover flag candidates, or
        # the reconciler cancels its own previous run (the 2026-08-07 oscillator).
        # Use candidate_query() in that script instead.
        "offmarket_multilot": {"$ne": True},
        "offmarket_entity_unresolved": {"$ne": True},
        "property_type": {"$nin": NON_HOUSE_TYPES},
        "building_type": {"$nin": NON_HOUSE_TYPES},
        "address": {"$not": UNIT_ADDR_RE},
        "$or": [
            {"listing_status": {"$ne": "sold"}, "enriched_data.transactions.0": {"$exists": True}},
            {"listing_status": "sold", "sale_price": {"$exists": True, "$ne": None},
             "sold_date": {"$lte": cutoff}},
        ],
    }


def reachable_query():
    """Every off-market home a PERSON can reach, indexed or not.

    indexed_query() is deliberately the exact sitemap mirror, and its sale-history
    `$or` is an INDEXING rule: getOffMarketUrls() only submits homes with a
    recorded sale. But the deck builder never reads sale history at all (no
    reference to `transactions` in emit_json.py or fact_bundle.py), so that
    clause was excluding ~8.6k homes the deck renders perfectly well — and
    /off-market/<slug> stays reachable for every one of them via QR, direct mail,
    an ad or a manual lookup. Those visitors were served the pre-V3 classic page
    (found 2026-08-05 on 34 Banksia Broadway, which has an empty transactions
    array while every neighbour has sales).

    Dropping only the `$or` and keeping every other filter means these homes get
    decks WITHOUT entering the sitemap: generate-sitemap.mjs is untouched, so they
    stay noindex exactly as before. Nothing about what Google sees changes.

    Kept separate from indexed_query() on purpose. That function feeds the
    COVERAGE_GAP_TOLERANCE assertion, whose whole meaning is "indexed → deck";
    widening it in place would silently redefine the invariant that caught the
    2026-07-29 Nerang drift. Two queries, two jobs.
    """
    q = indexed_query()
    q.pop("$or", None)
    # STREET-LEVEL RECORDS, not homes. Dropping the sale-history clause also drops
    # the thing that was incidentally excluding them: a cadastral row for a whole
    # street ("cheltenham-drive-robina", "laurel-oak-drive-robina-2") has no
    # transactions, so the `$or` filtered it out for free. 407 of them surface in
    # the reachable set and ZERO in the indexed set — measured, not assumed.
    # A deck for one opens "We found your home." over a street name with no house
    # number, and its intro has no tier-3 grid to close in on. Require a leading
    # house number. Deliberately here and not in indexed_query(), which must stay
    # a byte-for-byte mirror of getOffMarketUrls().
    q["url_slug"] = dict(q.get("url_slug") or {}, **{"$regex": r"^\d"})
    return q


def reachable_homes():
    """Same shape as indexed_homes(), over the wider reachable set."""
    gc = _gc()
    q = reachable_query()
    for c in target_suburbs(gc):
        for r in gc[c].find(q, {"url_slug": 1, "enriched_data.last_enriched": 1,
                               "valuation_data.computed_at": 1}):
            slug = r.get("url_slug")
            if not slug:
                continue
            yield (slug, (r.get("enriched_data") or {}).get("last_enriched"), c,
                   (r.get("valuation_data") or {}).get("computed_at"))


def indexed_homes():
    """Yield (slug, last_enriched, suburb, valuation_computed_at) per indexed home.

    The suburb is carried through to build_one() rather than left to
    fact_bundle's fallback scan (offmarket_intel_poller.TARGET_SUBURBS) — that
    scan is its own hardcoded list and silently returns subject_not_found for a
    collection it doesn't know about. We already know which collection the home
    came from; passing it is both correct and one fewer list to keep in sync.
    """
    gc = _gc()
    q = indexed_query()
    for c in target_suburbs(gc):
        for r in gc[c].find(q, {"url_slug": 1, "enriched_data.last_enriched": 1,
                               "valuation_data.computed_at": 1}):
            slug = r.get("url_slug")
            if not slug:
                continue
            le = (r.get("enriched_data") or {}).get("last_enriched")
            va = (r.get("valuation_data") or {}).get("computed_at")
            yield slug, le, c, va


def frozen_released_slugs(gc=None):
    """Slugs a FROZEN suburb can still emit into the sitemap.

    Mirrors generate-sitemap.mjs exactly: same `indexed_query()` filter, same
    `sort({_id: 1}).limit(N)` release slice. These are not built any more, but they
    must keep their decks — Google already has these URLs, and a missing deck means
    the loader silently falls through to the OLD classic page.
    """
    gc = _gc() if gc is None else gc
    out = set()
    q = indexed_query()
    for sub, limit in frozen_suburbs(gc).items():
        if not limit:
            continue
        for r in gc[sub].find(q, {"url_slug": 1}).sort([("_id", 1)]).limit(int(limit)):
            if r.get("url_slug"):
                out.add(r["url_slug"])
    return out


def existing_generated_at():
    """{slug: generated_at} for docs already built — one pass, cheap."""
    coll = ODB._mongo()
    return {d["slug"]: d.get("generated_at", "")
            for d in coll.find({}, {"slug": 1, "generated_at": 1})}


def _stamp(v):
    """Normalise a freshness marker to a comparable ISO string.

    `last_enriched` is an ISO string, `valuation_data.computed_at` a datetime,
    `generated_at` an isoformat+Z string. Comparing them raw is fragile."""
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _needs_build(slug, last_enriched, have, rebuild_all, valued_at=None):
    """Rebuild when the deck is older than any input that feeds it.

    ⚠ `valued_at` added 2026-08-06. Until then this compared ONLY
    `enriched_data.last_enriched`. Writing `valuation_data` does not touch that
    field, so a home that gained a valuation never triggered a rebuild — and
    `fact_bundle._obvious_comp` reads `valuation_data.recent_sales`, so the
    "that sale up the road isn't your comparison" card could never appear.

    Measured on the live fleet: `comparable` rendered on 22 of 400 decks (5.5%),
    and 0 of 29 cached bundles in a seeded sample carried an `obvious_comp` while
    23 of those 29 documents already held the recent sales it needs.
    """
    if rebuild_all:
        return True
    gen = have.get(slug)
    if gen is None:            # no doc yet
        return True
    gen_s = _stamp(gen)
    newest_input = max(_stamp(last_enriched), _stamp(valued_at))
    return bool(newest_input and newest_input > gen_s)


def _build_loop(todo, tag=""):
    """Build + upsert each home; returns (built, failed, seconds)."""
    built = failed = 0
    t0 = time.time()
    n = len(todo)
    for i, (slug, _le, suburb) in enumerate(todo, 1):
        try:
            doc = ODB.build_one(slug, suburb, rebuild=True)
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


# ⚠ NIGHTLY BUILD CAP (added 2026-08-06).
#
# Deck rebuilds cost ~2.1s each (measured on five real properties). Historically
# `to_build` was 0-2 a night because staleness keyed off `enriched_data.last_enriched`,
# which rarely changes. Two same-day changes altered that: `_needs_build` now also
# triggers on `valuation_data.computed_at`, and `scripts/batch_value_offmarket.py`
# writes a fresh valuation to the whole off-market book. Both are correct, and
# together they make the backlog ~10,000 decks — about 6 hours in one run, holding
# Cosmos RUs through the morning crons on a serverless tier.
#
# So the nightly takes the OLDEST decks first and stops at the cap. Homes not
# reached tonight keep serving their existing deck — exactly what they would have
# done anyway — and the backlog drains over several nights. Self-healing: each run
# takes the next oldest slice. Raise with --limit, disable with --limit 0.
DEFAULT_NIGHTLY_CAP = 3000


def run(limit=None, rebuild_all=False, dry_run=False, shard=None, reachable=False):
    # shard = (i, N): process only homes whose position ≡ i (mod N). Lets us run
    # N parallel processes (each its own Mongo client — separate processes, no
    # fork) to cut the initial ~14.6k backfill from latency-bound hours to ~1/N.
    # Skip job_run heartbeat for shard workers (a shard isn't "the job"); the
    # unsharded nightly run owns the heartbeat.
    if shard is not None:
        # Must honour --reachable exactly as the unsharded path does. It did not
        # until 2026-08-05: this branch called indexed_homes() unconditionally, so
        # `--reachable --shard i/N` would silently rebuild only the 14,255 indexed
        # homes and skip every reachable-only one — the parallel path quietly
        # building a different set from the sequential one, with nothing to catch
        # it (shard workers deliberately skip the coverage assertion).
        homes = sorted(reachable_homes() if reachable else indexed_homes())
        have = existing_generated_at()
        todo = [(s, le, sub) for (s, le, sub, va) in homes
                if _needs_build(s, le, have, rebuild_all, va)]
        i, N = shard
        todo = [t for k, t in enumerate(todo) if k % N == i]
        _build_loop(todo, tag=f"shard{i}/{N}")
        return
    with job_run("offmarket_discovery_nightly", cadence_hours=24,
                 title="Off-Market Discovery Deck (full indexed coverage)") as beat:
        # `homes` stays the INDEXED set — the coverage assertion below is defined
        # on it and must keep meaning "indexed → deck". --reachable only widens
        # what gets BUILT (see reachable_query), never what gets asserted.
        homes = list(indexed_homes())
        build_pool = list(reachable_homes()) if reachable else homes
        have = existing_generated_at()
        todo = [(s, le, sub) for (s, le, sub, va) in build_pool
                if _needs_build(s, le, have, rebuild_all, va)]
        # Oldest deck first, so a capped run drains the backlog deterministically
        # instead of rebuilding whichever homes happen to sort first. Decks with
        # no doc yet (`have` miss) go to the front — they render nothing today.
        todo.sort(key=lambda t: _stamp(have.get(t[0])) or "")
        cap = DEFAULT_NIGHTLY_CAP if limit is None else limit
        backlog = len(todo)
        if cap and backlog > cap:
            todo = todo[:cap]
        total_indexed = len(homes)
        print(f"indexed={total_indexed}  reachable={len(build_pool) if reachable else '-'}  "
              f"have_docs={len(have)}  backlog={backlog}  to_build={len(todo)}"
              + (f"  (capped at {cap}; {backlog - len(todo):,} deferred to later runs)"
                 if backlog > len(todo) else ""), file=sys.stderr)
        if dry_run:
            beat.detail = f"dry-run: {len(todo)} to build of {total_indexed} indexed"
            beat.metrics = {"indexed": total_indexed, "have": len(have),
                            "to_build": len(todo), "backlog": backlog}
            return

        built, failed, dt = _build_loop(todo, tag="main")

        # COVERAGE ASSERTION — the invariant this job exists to hold is
        # "indexed → deck". Compare the actual indexed SLUG SET against the built
        # docs, not just the counts: a doc count can match while a whole suburb is
        # absent and an equal number of stale docs sit in its place. Any indexed
        # slug without a doc is a home Google can send traffic to that renders the
        # OLD classic page.
        after = existing_generated_at()
        cov = len(after)
        # Frozen suburbs are not built, but their released slice is still reachable from
        # the sitemap — so it is still covered by this assertion. Watch ⊇ build.
        # `s for s, *_` not `s, _le, _sub` — indexed_homes() yields 4-tuples
        # (slug, last_enriched, suburb, valuation_computed_at). Unpacking a fixed
        # width here crashed the whole run AFTER all 3000 decks had built.
        indexed_slugs = {s for s, *_ in homes} | frozen_released_slugs()
        missing = sorted(indexed_slugs - set(after))
        sample = ", ".join(missing[:5]) + (" …" if len(missing) > 5 else "")
        gap = f"; GAP {len(missing)} indexed w/o deck ({sample})" if missing else ""
        print(f"\nbuilt={built} failed={failed} in {dt}s  |  coverage={cov}/{total_indexed}{gap}",
              file=sys.stderr)
        beat.detail = (f"built {built}, failed {failed}; "
                       f"{len(indexed_slugs) - len(missing)}/{len(indexed_slugs)} indexed have decks"
                       + (f"; {len(missing)} MISSING ({sample})" if missing else ""))
        # INTRO-TOKENS ASSERTION (2026-08-05) — a deck without `intro_tokens`
        # silently skips the matrix intro and opens cold on card 00. Nothing
        # watched this until a newly-built home shipped intro-less and it was
        # caught by eye, so it gets a number here. Steady state is 0: tokens are
        # now written at creation by ODB._write_intro_tokens(); anything above
        # the tolerance means that producer has broken again rather than a
        # handful of per-home failures.
        no_intro = ODB._mongo().count_documents({"intro_tokens": {"$exists": False}})
        beat.metrics = {"indexed": total_indexed, "built": built, "failed": failed,
                        "coverage": cov, "missing": len(missing), "seconds": dt,
                        "no_intro_tokens": no_intro,
                        "suburbs": target_suburbs(),
                        "frozen": frozen_suburbs()}
        if no_intro:
            beat.detail += f"; {no_intro} deck(s) w/o intro tokens"
        if len(missing) > COVERAGE_GAP_TOLERANCE:
            raise RuntimeError(
                f"off-market deck coverage gap: {len(missing)} indexed homes have no "
                f"discovery doc and are serving the OLD classic page (e.g. {sample}). "
                f"Suburbs built: {', '.join(target_suburbs())}.")
        if no_intro > INTRO_GAP_TOLERANCE:
            raise RuntimeError(
                f"off-market intro-token gap: {no_intro} decks have no intro_tokens and "
                f"open cold on card 00 instead of playing the matrix intro. Repair with "
                f"Page_Redesign_V3/intro/backfill_intro_tokens.py, then find why "
                f"_write_intro_tokens() stopped writing them at build time.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rebuild-all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--shard", default=None, help='"i/N" — build only homes where index%%N==i (parallel workers)')
    ap.add_argument("--reachable", action="store_true",
                    help="build every off-market home a person can reach, not just the "
                         "sitemap-indexed set (adds homes with no recorded sale; they stay "
                         "noindex — see reachable_query)")
    args = ap.parse_args()
    shard = None
    if args.shard:
        i, N = args.shard.split("/")
        shard = (int(i), int(N))
    run(limit=args.limit, rebuild_all=args.rebuild_all, dry_run=args.dry_run, shard=shard,
        reachable=args.reachable)

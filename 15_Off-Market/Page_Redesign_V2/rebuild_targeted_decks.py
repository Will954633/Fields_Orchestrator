#!/usr/bin/env python3
"""rebuild_targeted_decks.py — rebuild only the decks whose gaps we can now close.

WHY THIS IS NEEDED AT ALL
-------------------------
The onthehouse backfill (2026-08-13/14) wrote `bedrooms`, `bathrooms`, `floor_area_sqm`
and `land_size_sqm` to 11,591 property documents. **None of it reached a single public
page**, for two compounding reasons:

1. The deck is GENERATED content. `system_monitor.offmarket_discovery` stores rendered
   cards, not attributes — the numbers are baked in at build time. Writing to
   `Gold_Coast` changes nothing until the deck is rebuilt.

2. ⚠ THE NIGHTLY WILL NEVER REBUILD THEM. `offmarket_discovery_nightly._needs_build()`
   treats a deck as stale only when `enriched_data.last_enriched` or
   `valuation_data.computed_at` is newer than it. The backfill wrote neither field, so
   these decks are permanently "fresh" while serving data we superseded days ago.
   18,032 of 18,204 decks still date from 2026-08-09.

So the data sat one hop short of the surface, invisibly, with every job reporting success.

WHAT THIS BUILDS
----------------
Only decks whose own `build_notes.gaps` names something we now hold — "bedrooms unknown"
where we now have bedrooms, "bathrooms unknown" where we now have bathrooms. 2,414 homes,
against 18,204 total. That keeps the blast radius small and makes the result measurable:
the gap list is the acceptance test, and it is written by the builder, not by me.

⚠ NOT A REPLACEMENT FOR THE NIGHTLY. This closes a specific one-off backlog. The real fix
is for attribute writes to touch a staleness field the nightly already watches; until then
any future bulk attribute write needs a pass like this one.

Reuses `offmarket_discovery_nightly._build_loop` rather than reimplementing build+upsert,
so error handling, progress and the Cosmos retry path stay identical to the nightly.

DRY RUN BY DEFAULT.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for p in (str(HERE), str(ROOT), str(ROOT / "scripts"),
          str(ROOT / "15_Off-Market" / "Units" / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.db import get_client                              # noqa: E402
from scripts.job_status import job_run                        # noqa: E402
from unit_valuation import bedrooms_of                        # noqa: E402
from scripts.onthehouse_backfill import _held                 # noqa: E402
import offmarket_discovery_nightly as NIGHTLY                 # noqa: E402

# gap text in build_notes -> predicate saying "we now hold this"
CLOSABLE = {
    "bedrooms unknown":  lambda d: bool(bedrooms_of(d)),
    "bathrooms unknown": lambda d: _held(d, "bathrooms"),
}

ATTR_PROJ = {"url_slug": 1, "bedrooms": 1, "bathrooms": 1, "floor_area_sqm": 1,
             "onthehouse_data": 1,
             "scraped_data.features.bedrooms": 1, "scraped_data_v2.bedrooms": 1,
             "scraped_data_apr01_recovered.features.bedrooms": 1,
             "property_valuation_data.layout.number_of_bedrooms": 1}


def property_attrs(gc):
    """slug -> (doc, suburb) for every property carrying a url_slug."""
    out = {}
    for coll in gc.list_collection_names():
        if coll == "address_search_index":
            continue
        try:
            cur = gc[coll].find({"url_slug": {"$exists": True}}, ATTR_PROJ)
        except Exception:                                     # noqa: BLE001
            continue
        for d in cur:
            out[d["url_slug"]] = (d, coll)
    return out


def select_targets():
    """(slug, None, suburb) for decks with a gap we can now close, + stats."""
    cl = get_client()
    gc, sm = cl["Gold_Coast"], cl["system_monitor"]
    attrs = property_attrs(gc)
    todo, stats = [], Counter()
    for deck in sm["offmarket_discovery"].find({}, {"slug": 1, "build_notes": 1}):
        slug = deck.get("slug")
        gaps = set((deck.get("build_notes") or {}).get("gaps") or [])
        if not gaps or slug not in attrs:
            continue
        doc, suburb = attrs[slug]
        closes = sorted(g for g in gaps & CLOSABLE.keys() if CLOSABLE[g](doc))
        if not closes:
            continue
        stats["+".join(closes)] += 1
        if doc.get("onthehouse_data"):
            stats["from_onthehouse"] += 1
        todo.append((slug, None, suburb))
    return todo, stats


def measure_gaps(slugs):
    """Current gap counts for a slug set — the before/after acceptance measure."""
    sm = get_client()["system_monitor"]
    c = Counter()
    for d in sm["offmarket_discovery"].find({"slug": {"$in": list(slugs)}},
                                            {"build_notes": 1}):
        g = (d.get("build_notes") or {}).get("gaps") or []
        for x in g:
            c[str(x)] += 1
        if not g:
            c["(no gaps)"] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="build (default: dry run)")
    ap.add_argument("--shard", help='"i/N" — build only every Nth home (parallel workers)')
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    todo, stats = select_targets()
    print(f"  targets: {len(todo):,}", flush=True)
    for k in sorted(stats):
        print(f"    {k:24} {stats[k]:>6,}")

    if args.limit:
        todo = todo[:args.limit]
    tag = "targeted"
    if args.shard:
        i, N = (int(x) for x in args.shard.split("/"))
        todo = [t for k, t in enumerate(todo) if k % N == i]
        tag = f"shard{i}/{N}"
        print(f"  {tag}: {len(todo):,} homes", flush=True)

    if not args.apply:
        before = measure_gaps([t[0] for t in todo])
        print("\n  gaps across the target set TODAY:")
        for k, v in before.most_common():
            print(f"    {v:>6,}  {k}")
        print("\n  DRY RUN — nothing built. Re-run with --apply.")
        return 0

    # A shard is not "the job" — the unsharded run owns the heartbeat, matching the
    # nightly's own convention so two shards don't fight over one status row.
    if args.shard:
        built, failed, secs = NIGHTLY._build_loop(todo, tag=tag)
        print(f"  {tag}: built={built} failed={failed} in {secs}s")
        return 0

    with job_run("offmarket_deck_targeted_rebuild", cadence_hours=None,
                 title="Off-Market decks — targeted gap-closing rebuild") as beat:
        slugs = [t[0] for t in todo]
        before = measure_gaps(slugs)
        built, failed, secs = NIGHTLY._build_loop(todo, tag=tag)
        after = measure_gaps(slugs)
        print(f"\n  built={built:,} failed={failed:,} in {secs // 60}m")
        print("  gap                            before -> after")
        for k in sorted(set(before) | set(after)):
            print(f"    {k:28} {before.get(k, 0):>6,} -> {after.get(k, 0):>6,}")
        beat.metrics = {"targets": len(todo), "built": built, "failed": failed,
                        "beds_gap_before": before.get("bedrooms unknown", 0),
                        "beds_gap_after": after.get("bedrooms unknown", 0),
                        "baths_gap_before": before.get("bathrooms unknown", 0),
                        "baths_gap_after": after.get("bathrooms unknown", 0)}
        beat.detail = (f"{built:,} decks rebuilt; bedrooms-unknown "
                       f"{before.get('bedrooms unknown', 0):,} -> "
                       f"{after.get('bedrooms unknown', 0):,}")

        # ---- Rule 7b: assert the OUTCOME, not merely that nothing threw. ----
        if not todo:
            raise RuntimeError("0 targets selected — the gap text or the attribute "
                               "predicates changed; this job had ~2,414 to do")
        if built == 0:
            raise RuntimeError(f"selected {len(todo):,} decks and built NONE — the "
                               "builder is broken, not the dataset")
        if failed > max(10, 0.10 * len(todo)):
            raise RuntimeError(f"{failed:,} of {len(todo):,} builds failed")
        closed = (before.get("bedrooms unknown", 0) - after.get("bedrooms unknown", 0)
                  + before.get("bathrooms unknown", 0) - after.get("bathrooms unknown", 0))
        if closed <= 0:
            raise RuntimeError(
                "rebuilt every target and closed NO gaps — the builder is not reading "
                "the attributes we wrote, so this whole approach is wrong")
        print(f"  gaps closed: {closed:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

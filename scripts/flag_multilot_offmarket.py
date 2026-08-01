#!/usr/bin/env python3
"""flag_multilot_offmarket.py — mark addresses we cannot uniquely identify a HOUSE at.

Why
---
Off-market address pages are standalone-houses-only. The cadastre, however, stores
one record per TITLED LOT, and a community-titles scheme records every lot under the
same street address with no unit number — e.g. "2 Scottsdale Drive, Robina" is eight
lots on survey plan SP135953. `url_slug` disambiguates them with a 4-hex `_id` suffix
(`...-robina-2a52`), so each lot became its own off-market page: eight near-identical
pages asserting eight standalone houses at one address. Measured 2026-08-01 across the
three core suburbs: 167 colliding slug bases, 393 pages, 226 of them surplus, and 143
of the 167 groups sit on a SINGLE plan (i.e. plainly one strata scheme, not houses).

The `UNIT_ADDR_RE` / NON_HOUSE_TYPES filters can't catch these: the address carries no
unit number and the cadastral `property_type` is a bare "House".

Policy: if more than one eligible lot shares a slug base, we cannot say which physical
home an address page refers to — so NONE of that group is published. Conservative on
purpose; a wrong "this is your standalone house" page is worse than no page.

This writes a flag rather than filtering inline because three independent consumers
must agree on it, and Mongo cannot express "exclude groups of size > 1" in a find():
  - offmarket_discovery_nightly.indexed_query()   (deck builder)
  - generate-sitemap.mjs getOffMarketUrls()        (sitemap)
  - off-market.$slug.tsx meta()                    (robots tag)
Their agreement is load-bearing — see the comment block in meta().

Idempotent: recomputes from scratch each run and CLEARS the flag where a collision no
longer exists, so a cadastral correction heals itself.

Usage:
  python3 scripts/flag_multilot_offmarket.py --dry-run
  python3 scripts/flag_multilot_offmarket.py
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "15_Off-Market", "Page_Redesign_V2"))

from shared.db import get_client
from job_status import job_run

FLAG = "offmarket_multilot"
SUFFIX = re.compile(r"-[0-9a-f]{4}$")


def _nightly():
    """The deck builder owns the eligibility query and the suburb list — reuse both
    rather than keeping a second copy that can drift (the 2026-07-29 Nerang drift was
    exactly that failure mode)."""
    import offmarket_discovery_nightly as N
    return N


def suburbs(N, gc):
    # Frozen suburbs are still SERVED, so they still need correct flags even though
    # they are no longer built.
    return list(dict.fromkeys(N.target_suburbs(gc) + list(N.frozen_suburbs(gc))))


def collisions(gc, N, sub):
    """{base_slug: [_id, ...]} for bases claimed by more than one eligible lot."""
    by = defaultdict(list)
    for r in gc[sub].find(N.indexed_query(), {"url_slug": 1}):
        slug = r.get("url_slug")
        if slug:
            by[SUFFIX.sub("", slug)].append(r["_id"])
    return {b: ids for b, ids in by.items() if len(ids) > 1}


def run(dry_run: bool = False) -> dict:
    N = _nightly()
    gc = N._gc()
    stats = {"suburbs": 0, "groups": 0, "flagged": 0, "cleared": 0, "surplus": 0}
    for sub in suburbs(N, gc):
        groups = collisions(gc, N, sub)
        ids = [i for v in groups.values() for i in v]
        stats["suburbs"] += 1
        stats["groups"] += len(groups)
        stats["surplus"] += len(ids) - len(groups)
        # Anything currently flagged that is no longer colliding gets released.
        stale = [d["_id"] for d in gc[sub].find({FLAG: True, "_id": {"$nin": ids}}, {"_id": 1})]
        print(f"{sub:20s} groups={len(groups):>4} lots={len(ids):>5} "
              f"surplus={len(ids)-len(groups):>4} stale_flags_to_clear={len(stale)}")
        if dry_run:
            continue
        if ids:
            stats["flagged"] += gc[sub].update_many(
                {"_id": {"$in": ids}}, {"$set": {FLAG: True}}).modified_count
        if stale:
            stats["cleared"] += gc[sub].update_many(
                {"_id": {"$in": stale}}, {"$unset": {FLAG: ""}}).modified_count
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        st = run(dry_run=True)
        print(f"\ndry-run: {st['groups']} colliding bases, {st['surplus']} surplus pages")
        return
    with job_run("flag_multilot_offmarket", cadence_hours=24,
                 title="Off-Market Multi-Lot Address Exclusion") as beat:
        st = run()
        beat.detail = (f"{st['groups']} multi-lot address groups across {st['suburbs']} suburb(s); "
                       f"{st['surplus']} surplus pages suppressed; "
                       f"{st['flagged']} flagged, {st['cleared']} released")
        beat.metrics = st
        print("\n" + beat.detail)


if __name__ == "__main__":
    main()

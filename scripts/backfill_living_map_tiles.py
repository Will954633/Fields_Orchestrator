#!/usr/bin/env python3
"""backfill_living_map_tiles.py — repair the missing per-property house/street
tiles on living_map docs.

Context (2026-09-02): the 2026-08-28 living_map build saved ~6,479 burleigh_waters
and ~6,185 varsity_lakes docs with ONLY the shared suburb(z14)+city(z10) tiles —
the per-property house(z20)/street(z17) Static Maps fetch failed for those two
suburbs (env/quota during that chunk). At Home-level zoom the canvas engine then
upscales the z14 suburb tile ~48x → the whole aerial blurs (reported on
14 Treeview Drive, Burleigh Waters). The nightly job filters `living_map:{$exists:
False}` so it NEVER re-touches these — they stay blurry until forced.

This is SURGICAL: it reuses the already-stored `living_map.center` and only
re-fetches the two missing tiles + `$set`s `living_map.tiles.{house,street}`.
It does NOT recompute routes/POIs/comps/catchments (all fine), so a partial
failure here can never regress a good layer.

    python3 scripts/backfill_living_map_tiles.py --suburb burleigh_waters --limit 5
    python3 scripts/backfill_living_map_tiles.py --address "14 Treeview Drive, Burleigh Waters QLD 4220"
    python3 scripts/backfill_living_map_tiles.py            # all suburbs, all missing
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from precompute_living_map import (  # noqa: E402
    ZOOM_HOUSE, ZOOM_STREET, SUBURBS, fetch_static_tile, write_tile_blob,
)

# A doc needs repair if it has a living_map but no usable per-property house tile.
_MISSING = {"$in": [None, ""]}


def _iter_targets(gc, suburb, address, limit):
    q = {"living_map": {"$exists": True}, "living_map.tiles.house": _MISSING}
    if address:
        q = {"address": address, "living_map": {"$exists": True}}
    cur = gc[suburb].find(q, {"_id": 1, "address": 1, "living_map.center": 1,
                              "living_map.tiles.house": 1})
    if limit:
        cur = cur.limit(limit)
    return list(cur)


def backfill_one(gc, suburb, doc, key):
    """Re-fetch house+street for one doc using its stored center. Returns
    (ok: bool, note: str)."""
    center = ((doc.get("living_map") or {}).get("center")) or {}
    lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return False, "no stored center"
    house = write_tile_blob(
        fetch_static_tile(lat, lon, ZOOM_HOUSE, key), f"{suburb}/{doc['_id']}/house.jpg")
    street = write_tile_blob(
        fetch_static_tile(lat, lon, ZOOM_STREET, key), f"{suburb}/{doc['_id']}/street.jpg")
    gc[suburb].update_one(
        {"_id": doc["_id"]},
        {"$set": {"living_map.tiles.house": house,
                  "living_map.tiles.street": street}})
    return True, house


def run(args):
    from shared.db import get_gold_coast_db
    from concurrent.futures import ThreadPoolExecutor
    gc = get_gold_coast_db()
    key = os.getenv("GOOGLE_MAPS_STATIC_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_MAPS_STATIC_API_KEY not set")

    suburbs = [args.suburb] if args.suburb else list(SUBURBS)
    workers = int(os.environ.get("LIVING_MAP_WORKERS", "4"))
    CHUNK = 120
    fixed = failed = eligible = 0

    for suburb in suburbs:
        targets = _iter_targets(gc, suburb, args.address, args.limit)
        eligible += len(targets)
        if not targets:
            print(f"  · {suburb}: nothing to repair")
            continue
        print(f"  · {suburb}: {len(targets)} docs missing house tile")
        for i in range(0, len(targets), CHUNK):
            batch = targets[i:i + CHUNK]
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(backfill_one, gc, suburb, d, key) for d in batch]
                for d, fut in zip(batch, futs):
                    try:
                        ok, note = fut.result()
                    except Exception as e:                  # noqa: BLE001
                        failed += 1
                        print(f"    ✗ {d.get('address', d['_id'])}: {type(e).__name__}: {e}")
                        continue
                    if ok:
                        fixed += 1
                    else:
                        failed += 1
                        print(f"    ✗ {d.get('address', d['_id'])}: {note}")
            print(f"    … {suburb}: {fixed} fixed / {len(targets)} ({failed} failed)")

    return eligible, fixed, failed


def main():
    from shared.env import load_env
    load_env()
    ap = argparse.ArgumentParser(description="Backfill missing living_map house/street tiles")
    ap.add_argument("--suburb", choices=list(SUBURBS))
    ap.add_argument("--address")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-heartbeat", action="store_true",
                    help="skip job_run wrapper (for tiny ad-hoc repairs)")
    args = ap.parse_args()

    if args.no_heartbeat or args.address or (args.limit and args.limit <= 20):
        eligible, fixed, failed = run(args)
        print(f"\n  eligible {eligible} · fixed {fixed} · failed {failed}")
        return 0

    from job_status import job_run
    with job_run("backfill_living_map_tiles", cadence_hours=None,
                 title="Living Map tile backfill (one-off repair)") as beat:
        eligible, fixed, failed = run(args)
        beat.metrics = {"eligible": eligible, "fixed": fixed, "failed": failed}
        # Rule 7b: input present but nothing fixed = upstream broken, not empty.
        if eligible and fixed == 0:
            raise RuntimeError(
                f"{eligible} docs missing house tile but 0 fixed ({failed} failed) "
                f"— Static Maps key / blob store is broken")
        beat.detail = f"{fixed} tiles repaired ({failed} failed)"
    print(f"\n  eligible {eligible} · fixed {fixed} · failed {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

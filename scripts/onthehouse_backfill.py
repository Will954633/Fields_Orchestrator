#!/usr/bin/env python3
"""onthehouse_backfill.py — attributes from onthehouse for ANY dwelling that has none.

WHY THIS EXISTS BEYOND THE UNITS SCRIPT
---------------------------------------
`15_Off-Market/Units/scripts/onthehouse_attributes.py` backfills ATTACHED dwellings only.
The same hole exists for houses: across the three suburbs, 3,473 non-attached dwellings
(1,407 classified `house`, 2,005 `unknown`, 61 `non_dwelling`) have no bedroom count in any
path `bedrooms_of()` reads. They are overwhelmingly cadastral records for homes that have
never been listed, so Domain has nothing — which is exactly why it was assumed the data did
not exist. onthehouse publishes it for free, and 1,818 of them match a sitemap URL.

This script is the general case: pick a dwelling scope, fill what is missing, never
overwrite, record provenance on every field.

WHAT MAKES IT SAFE
------------------
1. THE PAGE IS THE AUTHORITY, NOT THE SITEMAP.  `subject_of()` reads the page's own
   `propertyDetail.property` block and returns the address it belongs to. We then require
   that address to equal the one we asked for. A wrong URL therefore produces NO WRITE
   instead of a wrong write — which is what lets the index be generous about genuinely
   ambiguous slugs (`2-4-riverwalk-ave` is either unit 2 at number 4, or 2-4).
   A page carries a dozen neighbours' `shortAddress` blocks; on `4-dexter-cl-robina` the
   subject is the FOURTEENTH. Reading the first is reading a different house.

2. FILL-ONLY. Every field is written only where we hold nothing. Cadastral land area and
   scraped floor area are ours and better sourced; onthehouse never overwrites them.

3. PROVENANCE PER FIELD. `<field>_source = {path, url, matched, fetched_at, script}` so any
   row can be audited or reverted with a single query.

⚠ A wrong bedroom count is worse than no bedroom count — bedrooms feed valuations, the
statutory comparable set and the bedroom-matched price index. Run
`test_onthehouse_match.py` and `--validate` before ever passing `--apply`.

⚠ ONE CRAWLER AT A TIME. Politeness is per-site, not per-process. Do not run this beside
the units script; `--wait-for` exists to chain them.

DRY RUN BY DEFAULT.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(HERE), str(ROOT / "15_Off-Market" / "Units" / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from curl_cffi import requests                                  # noqa: E402
from pymongo import UpdateOne                                   # noqa: E402
from shared.db import get_client                                # noqa: E402
from shared.dwelling_type import classify_dwelling               # noqa: E402
from scripts.job_status import job_run                           # noqa: E402
from scripts.onthehouse_match import build_index, key_of, subject_of   # noqa: E402
from unit_valuation import bedrooms_of                           # noqa: E402

SUBURB_SITEMAP = {"robina": "ROBINA_4226",
                  "varsity_lakes": "VARSITY_LAKES_4227",
                  "burleigh_waters": "BURLEIGH_WATERS_4220"}
SITEMAP = "https://www.onthehouse.com.au/sitemap/QLD/{}/Property_0.xml"

# robots.txt asks bingbot for Crawl-delay: 1. We are not bingbot, but a public dataset we
# read for free deserves at least the courtesy they asked of a search engine.
DELAY_S = 1.4

PROJ = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
        "property_type": 1, "classified_property_type": 1,
        "bedrooms": 1, "bathrooms": 1, "car_spaces": 1, "floor_area_sqm": 1,
        "land_size_sqm": 1, "lot_size_sqm": 1, "land_area": 1, "year_built": 1,
        "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
        "scraped_data.features.bedrooms": 1, "scraped_data_v2.bedrooms": 1,
        "scraped_data_apr01_recovered.features.bedrooms": 1,
        "property_valuation_data.layout.number_of_bedrooms": 1}

# Canonical target field -> the paths that already count as "we have this".
# ⚠ Land is fragmented across three top-level names in this schema (verified with
# db_fields.py, not guessed). Writing `land_size_sqm` while `lot_size_sqm` holds a
# cadastral figure would create a second, conflicting land area.
HELD_BY = {
    "bathrooms":      ("bathrooms",),
    "car_spaces":     ("car_spaces",),
    "floor_area_sqm": ("floor_area_sqm",),
    "land_size_sqm":  ("land_size_sqm", "lot_size_sqm", "land_area"),
    "year_built":     ("year_built",),
}


def _held(doc, field) -> bool:
    return any(doc.get(p) not in (None, "", 0) for p in HELD_BY[field])


def eff_address(d) -> str:
    return d.get("address") or d.get("complete_address") or d.get("street_address") or ""


def load_index(suburb):
    xml = requests.get(SITEMAP.format(SUBURB_SITEMAP[suburb]),
                       impersonate="chrome120", timeout=180).text
    return build_index(xml, suburb)


def wants(d, need):
    """Is anything we could fill actually missing on this document?

    ⚠ DO NOT GATE THE WHOLE RECORD ON BEDROOMS. A first cut selected on — and wrote only
    for — a missing bedroom count, and discarded the page whenever onthehouse published
    none. Measured on 40 random never-listed Burleigh Waters houses that cost 92% of the
    yield: only 3 of 40 had a bedroom count, but many carried a floor area we lack on 37%
    of houses (and 90% of units). We were throwing away the field we are shortest of in
    order to insist on the one they publish least.
    """
    if need == "bedrooms":
        return not bedrooms_of(d)
    return (not bedrooms_of(d)) or (not _held(d, "floor_area_sqm")) \
        or (not _held(d, "land_size_sqm"))


def select(gc, suburb, idx, scope, need):
    """(doc, key, url) for every in-scope dwelling missing something we can fill."""
    todo, stats = [], Counter()
    for d in gc[suburb].find({}, PROJ):
        eff = eff_address(d)
        cls = classify_dwelling({**d, "street_address": eff})
        if scope == "non-attached" and cls == "attached":
            continue
        if scope == "attached" and cls != "attached":
            continue
        if not wants(d, need):
            continue
        stats["in_scope"] += 1
        stats[f"cls_{cls}"] += 1
        k = key_of(eff, suburb)
        if not k:
            stats["no_key"] += 1          # our address has no street number at all
            continue
        url = idx.get(k)
        if not url:
            stats["unmatched"] += 1
            continue
        todo.append((d, k, url))
    return todo, stats


def fetch_subject(url, want_key, suburb):
    """(result, reason). result is None unless the page IS the home we asked for."""
    try:
        r = requests.get(url, impersonate="chrome120", timeout=45)
    except Exception:                                            # noqa: BLE001
        return None, "fetch_error"
    if r.status_code != 200:
        return None, "http_error"
    got = subject_of(r.text, suburb)
    if not got:
        return None, "no_subject_block"
    if got["key"] != want_key:
        # The index guessed wrong — an ambiguous slug, or their address differs from ours.
        # This is the safety net doing its job, not an error.
        return None, "address_mismatch"
    return got, "ok"


def run(args):
    gc = get_client()["Gold_Coast"]
    targets = [args.suburb] if args.suburb else list(SUBURB_SITEMAP)
    stats = Counter()
    samples = []

    for suburb in targets:
        idx, ixs = load_index(suburb)
        todo, sel = select(gc, suburb, idx, args.scope, args.need)
        stats.update(sel)
        print(f"  {suburb}: sitemap locs={ixs['locs']:,} keys={len(idx):,} "
              f"| in scope {sel['in_scope']:,} "
              f"| matched {len(todo):,} | unmatched {sel['unmatched']:,}", flush=True)

        if args.validate:
            # Held-out check: dwellings whose bedrooms we ALREADY hold. A matcher that
            # returns the building instead of the unit looks correct until compared with
            # something known.
            known = []
            for d in gc[suburb].find({}, PROJ):
                eff = eff_address(d)
                cls = classify_dwelling({**d, "street_address": eff})
                if args.scope == "non-attached" and cls == "attached":
                    continue
                truth = bedrooms_of(d)
                if not truth:
                    continue
                k = key_of(eff, suburb)
                if k and k in idx:
                    known.append((eff, truth, k, idx[k]))
            random.seed(11)
            random.shuffle(known)
            print(f"    validating against {min(args.n, len(known))} of "
                  f"{len(known):,} known-bedroom dwellings", flush=True)
            for eff, truth, k, url in known[:args.n]:
                got, why = fetch_subject(url, k, suburb)
                time.sleep(DELAY_S)
                if not got:
                    stats[f"v_{why}"] += 1
                    continue
                if got["bedrooms"] is None:
                    stats["v_no_beds"] += 1
                elif got["bedrooms"] == truth:
                    stats["v_agree"] += 1
                else:
                    stats["v_disagree"] += 1
                    samples.append(f"ours={truth} oth={got['bedrooms']}  {eff[:44]}"
                                   f"  -> {got['formatted_address']}")
            continue

        # ⚠ Cursor order front-loads the oldest cadastral stubs, which are exactly the
        # records onthehouse publishes least about. A --limit run over that order measures
        # the worst slice and reads as a total failure: the first --limit 3 returned 3/3
        # empty and tripped the "resolved NOTHING" guard, while a random 40 yielded 8%.
        random.seed(17)
        random.shuffle(todo)
        if args.limit:
            todo = todo[:args.limit]
        ops = []
        for d, k, url in todo:
            got, why = fetch_subject(url, k, suburb)
            time.sleep(DELAY_S)
            if not got:
                stats[why] += 1
                continue
            prov = {"path": "onthehouse", "url": url,
                    "matched": got["formatted_address"],
                    "fetched_at": dt.datetime.utcnow().isoformat(),
                    "script": "onthehouse_backfill"}
            # Everything onthehouse gave us, kept whole and separate so no existing
            # structure is disturbed. Coordinates live ONLY here: promoting them into
            # georeference_data is a separate job, because a dotted $set into a null
            # sub-doc silently fails.
            setter = {"onthehouse_data": {**got, "url": url,
                                          "fetched_at": prov["fetched_at"]}}
            filled = []
            if got["bedrooms"] is not None and not bedrooms_of(d):
                setter["bedrooms"] = got["bedrooms"]
                setter["bedrooms_source"] = prov
                filled.append("bedrooms")
            for field in ("bathrooms", "car_spaces", "floor_area_sqm",
                          "land_size_sqm", "year_built"):
                if got.get(field) and not _held(d, field):
                    setter[field] = got[field]
                    setter[f"{field}_source"] = prov
                    filled.append(field)
            for f in filled:
                stats[f"filled_{f}"] += 1
            if not filled:
                # The page had nothing we lack. Still a successful fetch, not an error.
                stats["nothing_to_fill"] += 1
                continue
            stats["resolved"] += 1
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": setter}))
            if len(ops) >= 200 and args.apply:
                gc[suburb].bulk_write(ops, ordered=False)
                ops = []
        if ops and args.apply:
            gc[suburb].bulk_write(ops, ordered=False)

    return stats, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--validate", action="store_true",
                    help="held-out accuracy check against known bedrooms; writes nothing")
    ap.add_argument("--scope", choices=["non-attached", "attached", "all"],
                    default="non-attached",
                    help="non-attached (default) avoids colliding with the units script")
    ap.add_argument("--need", choices=["any", "bedrooms"], default="any",
                    help="'any' (default) targets dwellings missing bedrooms OR floor "
                         "area OR land size; 'bedrooms' is the narrow legacy scope")
    ap.add_argument("--suburb")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--n", type=int, default=40, help="--validate sample size")
    ap.add_argument("--wait-for", help="path to a flag file to wait for before starting "
                                       "(keeps ONE crawler on the site at a time)")
    args = ap.parse_args()

    if args.wait_for:
        waited = 0
        while not os.path.exists(args.wait_for):
            time.sleep(30)
            waited += 30
            if waited % 600 == 0:
                print(f"  waiting for {args.wait_for} ({waited // 60} min)", flush=True)
        print(f"  {args.wait_for} present — starting", flush=True)

    if args.validate:                      # a measurement, not an ongoing process
        stats, samples = run(args)
        print(f"\n  VALIDATION (scope={args.scope})")
        for k in sorted(stats):
            if k.startswith("v_"):
                print(f"    {k[2:]:22} {stats[k]:>6,}")
        a, dis = stats["v_agree"], stats["v_disagree"]
        for s in samples[:10]:
            print(f"      MISMATCH {s}")
        if a + dis == 0:
            print("\n  ⚠ NOT A PASS — nothing was actually compared.")
            return 1
        print(f"\n    bedroom accuracy: {a / (a + dis) * 100:.1f}%  ({a}/{a + dis})")
        return 0 if dis == 0 else 1

    with job_run("onthehouse_backfill", cadence_hours=168,
                 title="onthehouse — attributes for dwellings with none") as beat:
        stats, _ = run(args)
        print()
        for k in sorted(stats):
            print(f"  {k:26} {stats[k]:>7,}")
        if not args.apply:
            print("\n  DRY RUN — nothing written. Re-run with --apply.")
        beat.metrics = dict(stats)
        beat.detail = f"{stats['resolved']:,} dwellings resolved from onthehouse"

        # ---- Rule 7b: assert an OUTCOME, not merely that nothing threw. ----
        if stats["in_scope"] == 0:
            raise RuntimeError(
                "0 dwellings in scope are missing anything — classify_dwelling, "
                "bedrooms_of or _held has broken; this job had ~6,200 to do")
        attempted = (stats["resolved"] + stats["nothing_to_fill"]
                     + stats["address_mismatch"] + stats["no_subject_block"]
                     + stats["fetch_error"] + stats["http_error"])
        if attempted and stats["resolved"] == 0:
            raise RuntimeError(
                f"attempted {attempted:,} fetches and resolved NOTHING — the page shape or "
                "the matcher changed. That is a defect, not an empty dataset")
        errs = stats["fetch_error"] + stats["http_error"]
        if errs > max(5, 0.25 * max(1, attempted)):
            raise RuntimeError(
                f"{errs:,} of {attempted:,} fetches failed — we are blocked or throttled; "
                "stop rather than hammer them")
        if stats["no_subject_block"] > max(5, 0.10 * max(1, attempted)):
            raise RuntimeError(
                f"{stats['no_subject_block']:,} pages had no propertyDetail block — their "
                "page shape has changed and the extractor needs revisiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())

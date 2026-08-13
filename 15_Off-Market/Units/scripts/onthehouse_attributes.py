#!/usr/bin/env python3
"""onthehouse_attributes.py — bedrooms, bathrooms and floor area for units that have none.

WHY
---
4,590 attached dwellings in the three suburbs have NO bedroom count in any of the five
paths `bedrooms_of()` coalesces. That single missing field is the largest constraint on
the whole unit product: a subject WITH a bedroom count gets a valuation range 90% of the
time and one WITHOUT gets one 22% of the time. It also blocks the bedroom-mix claim, the
statutory comparable set (same-bedroom is required) and the bedroom-matched price index.

`backfill_beds_baths.py` cannot help: it MOVES a value between fields we already hold, and
`bedrooms_of()` already reads all of them. If it returns None there is nothing to move.
68% of these dwellings have never been scraped at all — they are cadastral records for
homes that have never been listed, so Domain has nothing either.

onthehouse does. Verified on 1/1 Acacia Court, Robina — a home with no bedroom count of
ours — `beds: 2, baths: 2, floorSize: 138`. Their sitemap publishes every property URL with
the address and id embedded, and `/property/` is not disallowed in robots.txt (only
`/sold-history/`, `/rental-history/` and friends are).

⚠ THE MATCHER IS THE WHOLE RISK, AND A LOOSE ONE ALREADY BURNED US.
A first throwaway sampler matched on substring containment and produced confident, wrong
answers: the record for `61 Investigator Dr` matched INSIDE the slug
`4608-61-investigator-drive`, so unit 4608 would have been assigned the building's
bedrooms. Three of twelve inspected rows were the building rather than the unit. Writing
that would corrupt bedrooms, which then feed valuations, comparables AND the price index —
strictly worse than having no data.

So matching here is exact on a normalised (unit, street-number, street-name, suburb) tuple.
A record without a unit number NEVER matches a subject with one. There is no fuzzy fallback.

⚠ `beds: 0` IS A MISSING VALUE, NOT A STUDIO. onthehouse returns 0 for unknown; two of the
25 sampled did. Zero is rejected.

Every write records provenance so it is auditable and reversible:
    bedrooms_source = {"path": "onthehouse", "url": ..., "fetched_at": ..., "script": ...}

DRY RUN BY DEFAULT.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from curl_cffi import requests                        # noqa: E402
from pymongo import UpdateOne                          # noqa: E402
from shared.db import get_client                       # noqa: E402
from shared.dwelling_type import classify_dwelling      # noqa: E402
from scripts.job_status import job_run                  # noqa: E402
from unit_valuation import bedrooms_of                  # noqa: E402

SUBURB_SITEMAP = {"robina": "ROBINA_4226",
                  "varsity_lakes": "VARSITY_LAKES_4227",
                  "burleigh_waters": "BURLEIGH_WATERS_4220"}
SITEMAP = "https://www.onthehouse.com.au/sitemap/QLD/{}/Property_0.xml"

# robots.txt gives bingbot Crawl-delay: 1. We are not bingbot, but a public dataset we are
# reading for free deserves at least the courtesy they asked of a search engine.
DELAY_S = 1.3
MAX_BEDS, MAX_BATHS = 9, 9
MIN_FLOOR, MAX_FLOOR = 20, 500

ABBR = [(r"\b(court|crt)\b", "ct"), (r"\bdrive\b", "dr"), (r"\bstreet\b", "st"),
        (r"\bavenue\b", "ave"), (r"\bcircuit\b", "cct"), (r"\bplace\b", "pl"),
        (r"\bcrescent\b", "cr"), (r"\bparade\b", "pde"), (r"\broad\b", "rd"),
        (r"\blane\b", "ln"), (r"\bclose\b", "cl"), (r"\bterrace\b", "tce"),
        (r"\bboulevard\b", "bvd"), (r"\bcircle\b", "cir"), (r"\besplanade\b", "esp")]


def norm_street(s: str) -> str:
    s = (s or "").lower().replace(",", " ")
    s = re.sub(r"\bqld\b|\b\d{4}\b", "", s)
    for pat, rep in ABBR:
        s = re.sub(pat, rep, s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def parse_address(a: str):
    """(unit, street_number, rest) from a free-text address. unit is None when absent.

    ⚠ THE UNIT NUMBER IS THE ENTIRE POINT. `4608/61 Investigator Dr` and
    `61 Investigator Dr` normalise to different tuples here, which is what stops a
    building's record standing in for one of its apartments.
    """
    a = (a or "").strip()
    # ⚠ THE STREET NUMBER MAY BE A RANGE. `112/2-4 Riverwalk Ave` is one address, not a
    # unit at number 2 on a street called "4 Riverwalk Ave". Without the optional range
    # the pattern failed outright (returned None) and the slug form parsed as
    # ('112','2','4-riverwalk-ave') — two different wrong answers for one home.
    NUM = r"\d+[a-zA-Z]?(?:\s*-\s*\d+[a-zA-Z]?)?"
    m = re.match(rf"^\s*(\d+[a-zA-Z]?)\s*[/\\]\s*({NUM})\s+(.*)$", a)
    if m:
        return (m.group(1).lower(), re.sub(r"\s*", "", m.group(2).lower()),
                norm_street(m.group(3)))
    m = re.match(rf"^\s*({NUM})\s+(.*)$", a)
    if m:
        return None, re.sub(r"\s*", "", m.group(1).lower()), norm_street(m.group(2))
    return None, None, norm_street(a)


def key_of(address: str, suburb_key: str):
    unit, num, street = parse_address(address)
    if not num or not street:
        return None
    street = re.sub(rf"-{re.escape(suburb_key.replace('_', '-'))}$", "", street)
    return (unit or "", num, street, suburb_key)


def sitemap_index(suburb_key: str):
    """slug-tail -> url, for every property onthehouse publishes in this suburb."""
    url = SITEMAP.format(SUBURB_SITEMAP[suburb_key])
    r = requests.get(url, impersonate="chrome120", timeout=120)
    r.raise_for_status()
    out = {}
    for loc in re.findall(r"<loc>([^<]+)</loc>", r.text):
        tail = loc.rsplit("/", 1)[-1]
        m = re.match(r"(.+?)-qld-\d{4}-(\d+)$", tail)
        if not m:
            continue
        k = key_of(_slug_to_address(m.group(1)), suburb_key)
        if k:
            out[k] = loc
    return out


def _slug_to_address(slug: str) -> str:
    """`1-1-acacia-ct-robina` -> `1/1 acacia ct robina`.

    Only the FIRST two leading numbers can be a unit/street pair; everything after is the
    street name, which may itself contain digits (`2-4 Riverwalk Ave`). Guessing wrong here
    is how a building matches an apartment, so the split is deliberate and narrow.
    """
    parts = slug.split("-")
    num = lambda x: bool(re.fullmatch(r"\d+[a-z]?", x))                    # noqa: E731
    # Three leading numbers means a RANGED street number: 112/2-4 Riverwalk Ave.
    if len(parts) >= 4 and num(parts[0]) and num(parts[1]) and num(parts[2]):
        return f"{parts[0]}/{parts[1]}-{parts[2]} " + " ".join(parts[3:])
    if len(parts) >= 3 and num(parts[0]) and num(parts[1]):
        return f"{parts[0]}/{parts[1]} " + " ".join(parts[2:])
    # A ranged number with no unit: 2-4 Riverwalk Ave.
    if len(parts) >= 3 and num(parts[0]) and num(parts[1]) and not num(parts[2]):
        return f"{parts[0]}-{parts[1]} " + " ".join(parts[2:])
    return " ".join(parts)


def extract(html: str, want_key, suburb_key):
    """Attributes for the SUBJECT only, matched on the exact (unit, number, street) tuple."""
    best = None
    for m in re.finditer(r'"shortAddress":"([^"]+)"', html):
        k = key_of(m.group(1), suburb_key)
        if k != want_key:
            continue
        seg = html[m.start():m.start() + 400]
        beds = re.search(r'"beds":\s*(\d+)', seg)
        baths = re.search(r'"baths":\s*(\d+)', seg)
        floor = re.search(r'"floorSize":\s*(\d+)', seg)
        cars = re.search(r'"carSpaces":\s*(\d+)', seg)
        b = int(beds.group(1)) if beds else 0
        if not (0 < b <= MAX_BEDS):        # 0 is onthehouse's "unknown", not a studio
            continue
        ba = int(baths.group(1)) if baths else 0
        fl = int(floor.group(1)) if floor else 0
        best = {"bedrooms": b,
                "bathrooms": ba if 0 < ba <= MAX_BATHS else None,
                "floor_area_sqm": fl if MIN_FLOOR <= fl <= MAX_FLOOR else None,
                "car_spaces": int(cars.group(1)) if cars else None,
                "matched_address": m.group(1)}
        break
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--suburb")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    targets = [args.suburb] if args.suburb else list(SUBURB_SITEMAP)

    with job_run("units_onthehouse_attributes", cadence_hours=168,
                 title="Units — bedrooms/floor area from onthehouse") as beat:
        gc = get_client()["Gold_Coast"]
        stats = Counter()
        PROJ = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
                "property_type": 1, "classified_property_type": 1, "bedrooms": 1,
                "scraped_data.features.property_type": 1,
                "scraped_data_v2.property_type": 1,
                "scraped_data.features.bedrooms": 1, "scraped_data_v2.bedrooms": 1,
                "scraped_data_apr01_recovered.features.bedrooms": 1,
                "property_valuation_data.layout.number_of_bedrooms": 1}

        for suburb in targets:
            idx = sitemap_index(suburb)
            print(f"  {suburb}: {len(idx):,} onthehouse properties indexed")
            todo = []
            for d in gc[suburb].find({}, PROJ):
                eff = (d.get("address") or d.get("complete_address")
                       or d.get("street_address") or "")
                if classify_dwelling({**d, "street_address": eff}) != "attached":
                    continue
                if bedrooms_of(d):
                    continue
                stats["missing"] += 1
                k = key_of(eff, suburb)
                url = idx.get(k) if k else None
                if not url:
                    stats["unmatched"] += 1
                    continue
                todo.append((d, k, url))
            print(f"    matched to a URL: {len(todo):,}")
            if args.limit:
                todo = todo[:args.limit]

            ops = []
            for d, k, url in todo:
                try:
                    r = requests.get(url, impersonate="chrome120", timeout=45)
                except Exception:                       # noqa: BLE001
                    stats["fetch_error"] += 1
                    time.sleep(DELAY_S)
                    continue
                if r.status_code != 200:
                    stats["http_error"] += 1
                    time.sleep(DELAY_S)
                    continue
                got = extract(r.text, k, suburb)
                time.sleep(DELAY_S)
                if not got:
                    stats["no_attributes"] += 1
                    continue
                stats["resolved"] += 1
                stats["with_floor"] += bool(got["floor_area_sqm"])
                prov = {"path": "onthehouse", "url": url,
                        "matched": got["matched_address"],
                        "fetched_at": dt.datetime.utcnow().isoformat(),
                        "script": "onthehouse_attributes"}
                setter = {"bedrooms": got["bedrooms"], "bedrooms_source": prov}
                if got["bathrooms"]:
                    setter["bathrooms"] = got["bathrooms"]
                    setter["bathrooms_source"] = prov
                if got["floor_area_sqm"]:
                    setter["floor_area_sqm"] = got["floor_area_sqm"]
                    setter["floor_area_source"] = prov
                ops.append(UpdateOne({"_id": d["_id"]}, {"$set": setter}))
                if len(ops) >= 200 and args.apply:
                    gc[suburb].bulk_write(ops, ordered=False)
                    ops = []
            if ops and args.apply:
                gc[suburb].bulk_write(ops, ordered=False)

        print(f"\n  missing bedrooms  : {stats['missing']:,}")
        print(f"  unmatched         : {stats['unmatched']:,}")
        print(f"  RESOLVED          : {stats['resolved']:,}  "
              f"(with floor area: {stats['with_floor']:,})")
        print(f"  no attributes     : {stats['no_attributes']:,}")
        print(f"  fetch/http errors : {stats['fetch_error']:,}/{stats['http_error']:,}")
        if not args.apply:
            print("\n  DRY RUN — nothing written. Re-run with --apply.")

        beat.metrics = dict(stats)
        beat.detail = f"{stats['resolved']:,} dwellings resolved from onthehouse"

        # Rule 7b — the zero-output paths.
        if stats["missing"] == 0:
            raise RuntimeError("0 attached dwellings missing bedrooms — the classifier or "
                               "bedrooms_of broke; this job had 4,590 to do")
        attempted = stats["resolved"] + stats["no_attributes"] + stats["fetch_error"] + stats["http_error"]
        if attempted and stats["resolved"] == 0:
            raise RuntimeError(
                f"attempted {attempted:,} fetches and resolved NOTHING — the page shape or "
                "the matcher changed, which is a defect not an empty dataset")
        if stats["fetch_error"] + stats["http_error"] > max(5, 0.25 * max(1, attempted)):
            raise RuntimeError(
                f"{stats['fetch_error'] + stats['http_error']:,} of {attempted:,} fetches "
                "failed — we are being blocked or throttled; stop rather than hammer them")
    return 0


if __name__ == "__main__":
    sys.exit(main())

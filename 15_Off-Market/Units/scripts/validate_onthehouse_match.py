#!/usr/bin/env python3
"""validate_onthehouse_match.py — held-out check that the matcher is actually right.

Resolves dwellings whose bedroom count we ALREADY hold and compares. A matcher that
returns the building's record instead of the apartment's looks identical to a correct one
until you check it against something you know — which is exactly how a first throwaway
sampler produced three confident wrong rows out of twelve.

Nothing is written. Run this before `onthehouse_attributes.py --apply`, and again whenever
the page shape or the matcher changes.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
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

from curl_cffi import requests                         # noqa: E402
from shared.db import get_client                       # noqa: E402
from shared.dwelling_type import classify_dwelling      # noqa: E402
from unit_valuation import bedrooms_of, _num            # noqa: E402
from onthehouse_attributes import sitemap_index, key_of, extract, DELAY_S   # noqa: E402

PROJ = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
        "property_type": 1, "classified_property_type": 1, "bedrooms": 1,
        "bathrooms": 1, "floor_area_sqm": 1,
        "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
        "scraped_data.features.bedrooms": 1, "scraped_data_v2.bedrooms": 1,
        "scraped_data_apr01_recovered.features.bedrooms": 1,
        "property_valuation_data.layout.number_of_bedrooms": 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default="robina")
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()

    gc = get_client()["Gold_Coast"]
    idx = sitemap_index(args.suburb)
    print(f"  sitemap: {len(idx):,} properties", flush=True)

    cands = []
    for d in gc[args.suburb].find({}, PROJ):
        eff = (d.get("address") or d.get("complete_address")
               or d.get("street_address") or "")
        if classify_dwelling({**d, "street_address": eff}) != "attached":
            continue
        truth = bedrooms_of(d)
        if not truth:
            continue                                   # need ground truth
        k = key_of(eff, args.suburb)
        if k and k in idx:
            cands.append((eff, truth, _num(d.get("floor_area_sqm")), k, idx[k]))
    print(f"  candidates with KNOWN bedrooms and a matched URL: {len(cands):,}", flush=True)
    if not cands:
        print("  nothing to validate — the matcher resolves none of the known homes, "
              "which is itself the finding")
        return 1

    random.seed(11)
    random.shuffle(cands)
    agree = dis = none = 0
    rows, floors = [], []
    for eff, truth, ourfloor, k, url in cands[:args.n]:
        try:
            r = requests.get(url, impersonate="chrome120", timeout=45)
            got = extract(r.text, k, args.suburb) if r.status_code == 200 else None
        except Exception:                              # noqa: BLE001
            got = None
        time.sleep(DELAY_S)
        if not got:
            none += 1
            continue
        if got["bedrooms"] == truth:
            agree += 1
        else:
            dis += 1
            rows.append((eff, truth, got["bedrooms"], got["matched_address"]))
        if ourfloor and got.get("floor_area_sqm"):
            floors.append((ourfloor, got["floor_area_sqm"]))

    n = agree + dis + none
    print(f"\n  VALIDATION on {n} fetched")
    print(f"    agree with our known bedrooms : {agree}")
    print(f"    DISAGREE                      : {dis}")
    print(f"    no attributes returned        : {none}")
    if agree + dis:
        print(f"    bedroom accuracy            : {agree / (agree + dis) * 100:.1f}%")
    for e, t, g, ma in rows[:10]:
        print(f"      MISMATCH ours={t} oth={g}  {e[:42]}  matched -> {ma}")
    if floors:
        d = [abs(a - b) / a * 100 for a, b in floors]
        print(f"    floor area: {len(floors)} comparable, median diff "
              f"{sorted(d)[len(d) // 2]:.1f}%")

    # A validator that validates nothing must not read as a pass.
    if agree + dis == 0:
        print("\n  ⚠ NOT A PASS — every fetch returned nothing, so the matcher was "
              "never actually tested.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

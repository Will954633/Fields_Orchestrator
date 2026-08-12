#!/usr/bin/env python3
"""build_unit_content.py — Part 02 for an attached dwelling. (Plan G1/G2/G5)

WHAT THIS REPLACES, AND WHY IT IS NOT A PORT
--------------------------------------------
The house engine's Part 02 answers "what makes this home uncommon among today's
listings" using land, block, aspect and a suburb-wide active-listing pool. Applied to a
unit it produced the two defects this project started with: a rarity claim counted
against the DETACHED HOUSE market ("it shares its core profile with 107 of 233 nearby
homes"), and a buyer persona promising "the space and backyard".

For a unit the honest comparison set is not the suburb. It is the scheme. The closest
substitute for a 2-bedroom home in a 53-home building is another 2-bedroom home in that
building — which is the same premise the valuation rests on, and it should be the same
premise the content rests on, or the page argues with itself.

So every figure here is scoped to the scheme and to the bedroom count:
  * how many homes of this size the building holds,
  * how often they change hands,
  * where this home sits in the building's own price range.

⚠ NO GREEN-SPACE OR BOUNDARY CLAIMS (plan G3). The house engine classifies "backs onto"
from a single geocode. For a 40-unit complex that point is the building centroid, so the
claim is about the scheme, not the dwelling, and can be flatly false for a home facing
the other way. It is omitted rather than softened.

⚠ EVERY NUMBER IS COUNTED FROM OUR OWN RECORDS AND SAYS SO. Where a count would be
misleading because our coverage of the scheme is thin, the claim is suppressed rather
than qualified — a reader cannot audit a footnote.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics as st
import sys
from collections import Counter, defaultdict
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

from pymongo import UpdateOne                           # noqa: E402
from shared.db import get_client                        # noqa: E402
from shared.dwelling_type import classify_dwelling       # noqa: E402
from scripts.job_status import job_run                   # noqa: E402
from unit_valuation import bedrooms_of, sale_price, plausible_for_scheme   # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
MIN_SCHEME_FOR_MIX = 6      # below this a bedroom-mix claim is noise, not a profile
MIN_SALES_FOR_TURNOVER = 4  # below this "how often homes here sell" is not a rate
RECENT_YEARS = 3

PROJ = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
        "property_type": 1, "classified_property_type": 1, "bedrooms": 1, "bathrooms": 1,
        "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
        "scraped_data.features.bedrooms": 1, "scraped_data_v2.bedrooms": 1,
        "scraped_data_apr01_recovered.features.bedrooms": 1,
        "property_valuation_data.layout.number_of_bedrooms": 1,
        "complex_plan": 1, "complex_cms": 1, "listing_status": 1,
        "sale_price": 1, "sold_date": 1,
        "scraped_data.property_timeline": 1, "enriched_data.transactions": 1}


def year(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def sales_of(doc):
    out = []
    for t in ((doc.get("enriched_data") or {}).get("transactions") or []):
        if isinstance(t, dict):
            p = sale_price(t.get("price"))
            if p:
                out.append((str(t.get("date") or "")[:10], p))
    for ev in ((doc.get("scraped_data") or {}).get("property_timeline") or []):
        if isinstance(ev, dict) and ev.get("is_sold"):
            p = sale_price(ev.get("price"))
            if p:
                out.append((str(ev.get("date") or "")[:10], p))
    if doc.get("listing_status") == "sold":
        p = sale_price(doc.get("sale_price"))
        if p:
            out.append((str(doc.get("sold_date") or "")[:10], p))
    return sorted(set(out))


def build_for_suburb(gc, suburb, this_year):
    """Group every attached dwelling by scheme, then describe each scheme once."""
    members = defaultdict(list)
    docs = []
    for d in gc[suburb].find({}, PROJ):
        eff = (d.get("address") or d.get("complete_address")
               or d.get("street_address") or "")
        if classify_dwelling({**d, "street_address": eff}) != "attached":
            continue
        key = d.get("complex_cms") or d.get("complex_plan")
        if not key:
            continue
        rec = {"slug": d.get("url_slug"), "beds": bedrooms_of(d),
               "sales": sales_of(d), "addr": eff}
        members[key].append(rec)
        docs.append((key, rec))

    # ---- one profile per scheme, computed once and shared by its members
    profiles = {}
    for key, rows in members.items():
        n = len(rows)
        bed_mix = Counter(r["beds"] for r in rows if r["beds"])
        all_sales = [(dte, p) for r in rows for dte, p in r["sales"]]
        # Scheme-relative plausibility again: a car-space title inside the building
        # would otherwise set the bottom of "what homes here sell for".
        if len(all_sales) >= 4:
            med = st.median([p for _d, p in all_sales])
            all_sales = [(d_, p) for d_, p in all_sales if plausible_for_scheme(p, med)]
        recent = [(d_, p) for d_, p in all_sales
                  if year(d_) and this_year - year(d_) <= RECENT_YEARS]
        prices = sorted(p for _d, p in recent)
        profiles[key] = {
            "homes": n,
            "bed_mix": {str(k): v for k, v in sorted(bed_mix.items())},
            "sales_recent": len(recent),
            "recent_low": prices[0] if prices else None,
            "recent_high": prices[-1] if prices else None,
            "recent_median": int(st.median(prices)) if prices else None,
            "last_sale_year": max((year(d_) for d_, _p in all_sales
                                   if year(d_)), default=None),
        }
    return docs, profiles


def content_for(rec, prof, this_year):
    """The claims for ONE home. Each is suppressed independently when its own evidence
    is thin — a page with two true statements beats one with five hedged ones."""
    out = {"scheme_homes": prof["homes"]}
    beds = rec["beds"]

    # 1. How many homes of this size the building holds. This is the rarity claim the
    #    house engine gets wrong by counting the detached-house market instead.
    if beds and prof["homes"] >= MIN_SCHEME_FOR_MIX:
        same = prof["bed_mix"].get(str(beds))
        if same:
            out["same_size_in_scheme"] = same
            out["bed_mix"] = prof["bed_mix"]

    # 2. How often homes here change hands. A turnover RATE needs enough sales to be a
    #    rate rather than an anecdote.
    if prof["sales_recent"] >= MIN_SALES_FOR_TURNOVER:
        out["sales_recent"] = prof["sales_recent"]
        out["sales_window_years"] = RECENT_YEARS
        out["recent_low"] = prof["recent_low"]
        out["recent_high"] = prof["recent_high"]
        # Homes changing hands per year as a share of the building.
        rate = prof["sales_recent"] / RECENT_YEARS / max(1, prof["homes"])
        out["turnover_pct_per_year"] = round(rate * 100, 1)

    # 3. When the building last traded at all — useful precisely when 2 is suppressed.
    if prof["last_sale_year"]:
        out["last_sale_year"] = prof["last_sale_year"]
        out["years_since_scheme_sale"] = this_year - prof["last_sale_year"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    targets = [args.suburb] if args.suburb else SUBURBS
    this_year = dt.date.today().year

    with job_run("units_content_build", cadence_hours=168,
                 title="Units — scheme-scoped page content") as beat:
        gc = get_client()["Gold_Coast"]
        col = gc["unit_content"]
        total = written = with_mix = with_turnover = 0

        for suburb in targets:
            docs, profiles = build_for_suburb(gc, suburb, this_year)
            ops = []
            for key, rec in docs:
                if not rec["slug"]:
                    continue
                total += 1
                c = content_for(rec, profiles[key], this_year)
                if c.get("same_size_in_scheme"):
                    with_mix += 1
                if c.get("sales_recent"):
                    with_turnover += 1
                ops.append(UpdateOne({"_id": rec["slug"]}, {"$set": {
                    "_id": rec["slug"], "suburb_key": suburb, "scheme_key": key,
                    "bedrooms": rec["beds"], **c,
                    "generated_at": dt.datetime.utcnow(),
                    "engine": "unit_content_v1",
                }}, upsert=True))
                if len(ops) >= 250 and not args.dry_run:
                    col.bulk_write(ops, ordered=False)
                    written += len(ops)
                    ops = []
            if ops and not args.dry_run:
                col.bulk_write(ops, ordered=False)
                written += len(ops)
            print(f"  {suburb:17s} {len(docs):6,} attached in {len(profiles):5,} schemes")

        beat.metrics = {"dwellings": total, "with_bed_mix": with_mix,
                        "with_turnover": with_turnover}
        beat.detail = (f"{total:,} dwellings · {with_mix:,} with a size claim · "
                       f"{with_turnover:,} with a turnover claim")

        # Rule 7b — a run that describes nothing is broken, not a quiet market.
        if total == 0:
            raise RuntimeError("0 attached dwellings grouped into schemes — the "
                               "classifier or the complex link broke")
        if with_mix == 0 and with_turnover == 0:
            raise RuntimeError(f"{total:,} dwellings but not one carries a single claim — "
                               "every threshold suppressed, which is a defect not a result")
    return 0


if __name__ == "__main__":
    sys.exit(main())

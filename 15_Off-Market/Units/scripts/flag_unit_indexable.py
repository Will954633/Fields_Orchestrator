#!/usr/bin/env python3
"""flag_unit_indexable.py — the ONE definition of "this unit page may be indexed". (Plan H1)

⚠ WHY A PERSISTED FLAG RATHER THAN A RULE EACH SIDE EVALUATES.
The sitemap (Node) and the route's `meta()` (TypeScript) must agree exactly, or the site
advertises URLs it then tells Google not to index. That has already happened once:
`[OFFMARKET-UNIT-SITEMAP-MISMATCH]` on 2026-08-08, where **4,559 URLs (25.7%)** were in
the sitemap while serving `noindex`, because the same policy was expressed twice in two
languages and the two chains drifted. Re-implementing "has a complex and scheme content"
on both sides would be the identical mistake with a new rule.

So the rule lives here, in Python, once. It writes `unit_indexable` (bool) and
`unit_indexable_reason` (string) onto the document, and both consumers read the field.
Disagreement becomes impossible rather than merely unlikely.

THE BAR — "complex + scheme content" (Will, 2026-08-13), 4,967 URLs:
  1. attached dwelling (shared classifier, on the effective address)
  2. clears the existing off-market tier the sitemap already requires — has a sale
     history, not currently listed, not waterfront, not multilot/unresolved
  3. linked to a scheme (`complex_plan`)
  4. carries at least one scheme-scoped claim in `unit_content` (a bedroom mix or a
     turnover figure) **OR** a publishable valuation. Widened 2026-08-13: requiring the
     claim alone excluded 943 dwellings that hold a tested figure but sit in a scheme too
     small for a mix claim or too quiet for a turnover rate.

Deliberately NOT required: a valuation range. A page whose method honestly refuses still
carries complex identity, scheme context, unit-scoped market data and sale history — and
for someone searching that exact address it is the page they want. The refusal is a
credibility asset, not a hole. It is also why Burleigh Waters (588) is included despite
never displaying a figure.

⚠ THIS DOES NOT WIDEN THE HOUSE RULE. `offmarket_discovery_nightly.indexed_query()` stays
the house-only mirror of the sitemap's house branch, so its COVERAGE_GAP_TOLERANCE
assertion keeps meaning "indexed house → deck". Units are a parallel branch with their own
content path (`unit_content`), so they need their own coverage check — see the Rule 7b
assertions below.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
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

from pymongo import UpdateOne                          # noqa: E402
from shared.db import get_client                       # noqa: E402
from shared.dwelling_type import classify_dwelling      # noqa: E402
from scripts.job_status import job_run                  # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
SOLD_MONTHS = 12

PROJ = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
        "property_type": 1, "classified_property_type": 1, "listing_status": 1,
        "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
        "enriched_data.transactions": 1, "sale_price": 1, "sold_date": 1,
        "is_waterfront": 1, "offmarket_multilot": 1, "offmarket_entity_unresolved": 1,
        "complex_plan": 1, "unit_indexable": 1}


def decide(doc, content, cutoff, publishable=False):
    """Returns (indexable: bool, reason: str). The reason is stored so a page that is
    NOT indexed can say why without anyone re-deriving the rule."""
    eff = (doc.get("address") or doc.get("complete_address")
           or doc.get("street_address") or "")
    if classify_dwelling({**doc, "street_address": eff}) != "attached":
        return False, "not_attached"
    if doc.get("listing_status") in ("for_sale", "under_contract"):
        return False, "currently_listed"
    if doc.get("is_waterfront") is True:
        return False, "waterfront_out_of_scope"
    if doc.get("offmarket_multilot") is True or doc.get("offmarket_entity_unresolved") is True:
        return False, "entity_unresolved"
    if not doc.get("url_slug"):
        return False, "no_slug"

    # The sale-history tier the sitemap already requires of houses.
    has_tx = bool(((doc.get("enriched_data") or {}).get("transactions")))
    sold_ok = (doc.get("listing_status") == "sold" and doc.get("sale_price")
               and str(doc.get("sold_date") or "") <= cutoff)
    if not (has_tx or sold_ok):
        return False, "no_sale_history"

    if not doc.get("complex_plan"):
        return False, "no_scheme"
    # ⚠ SCHEME CLAIM **OR** A PUBLISHABLE FIGURE (Will, 2026-08-13). Originally the bar
    # required a scheme claim, full stop. Measured against what those pages would
    # actually carry, that excluded 943 dwellings holding a TESTED VALUATION — an
    # address, an aerial, market context and a figure we stand behind — purely because
    # their scheme was too small for a bedroom-mix claim (MIN_SCHEME_FOR_MIX=6) or too
    # quiet for a turnover rate (MIN_SALES_FOR_TURNOVER=4). Thresholds that protect a
    # CLAIM from being noise should not also suppress a figure that was never noisy.
    # Still excluded: dwellings with neither, which are genuinely thin.
    if not (content.get("same_size_in_scheme") or content.get("sales_recent")
            or publishable):
        return False, "no_scheme_content"
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=int(SOLD_MONTHS * 30.44))
              ).strftime("%Y-%m-%d")

    with job_run("units_indexable_flag", cadence_hours=24,
                 title="Units — indexability flag (sitemap ↔ robots)") as beat:
        gc = get_client()["Gold_Coast"]
        content = {d["_id"]: d for d in gc["unit_content"].find(
            {}, {"same_size_in_scheme": 1, "sales_recent": 1})}
        # The second half of the bar — a figure we stand behind is content in its own
        # right. `publishable` already encodes the suburb accuracy gate, so a Burleigh
        # Waters dwelling (within-10% 46.5%, below the 55% bar) never qualifies here.
        publishable = {d["_id"] for d in gc["unit_valuations"].find(
            {"publishable": True}, {"_id": 1})}
        reasons, indexable, seen = Counter(), 0, 0

        for suburb in SUBURBS:
            ops = []
            for d in gc[suburb].find({}, PROJ):
                eff = (d.get("address") or d.get("complete_address")
                       or d.get("street_address") or "")
                if classify_dwelling({**d, "street_address": eff}) != "attached":
                    # Clear a stale flag if a document was reclassified — e.g. the
                    # 88 non-dwellings that left the attached bucket on 2026-08-13.
                    if d.get("unit_indexable"):
                        ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {
                            "unit_indexable": False,
                            "unit_indexable_reason": "not_attached"}}))
                    continue
                seen += 1
                ok, why = decide(d, content.get(d.get("url_slug")) or {}, cutoff,
                                 d.get("url_slug") in publishable)
                reasons[why] += 1
                indexable += ok
                # Write only on an actual change. The `or True` that used to be here
                # defeated this test and rewrote all ~11,500 attached docs every night —
                # needless RU on a serverless Cosmos tier. Compare the reason too, not
                # just the boolean: `ok` can stay the same while `why` changes, and the
                # reason is what explains a decision after the fact.
                if (bool(d.get("unit_indexable")) != ok
                        or d.get("unit_indexable_reason") != why):
                    ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {
                        "unit_indexable": ok,
                        "unit_indexable_reason": why,
                        "unit_indexable_at": dt.datetime.utcnow()}}))
                if len(ops) >= 250 and not args.dry_run:
                    gc[suburb].bulk_write(ops, ordered=False)
                    ops = []
            if ops and not args.dry_run:
                gc[suburb].bulk_write(ops, ordered=False)

        print(f"  attached dwellings evaluated: {seen:,}")
        print(f"  INDEXABLE: {indexable:,}\n")
        for k, v in reasons.most_common():
            print(f"    {k:24s} {v:6,}")

        beat.metrics = {"attached": seen, "indexable": indexable,
                        **{f"reason_{k}": v for k, v in reasons.items()}}
        beat.detail = f"{indexable:,} of {seen:,} attached dwellings indexable"

        # Rule 7b — the zero-output paths. Attached stock, schemes and scheme content all
        # exist; a run that flags nothing means an input regressed, not that the bar bit.
        if seen == 0:
            raise RuntimeError("0 attached dwellings seen — classifier or projection broke")
        if indexable == 0:
            raise RuntimeError(f"{seen:,} attached dwellings and 0 indexable — the bar is "
                               "rejecting everything, which is a defect not a result")
        # The bar was measured at ~43% of attached stock when it was chosen. A large
        # move means unit_content or the complex link regressed, and the sitemap would
        # silently shrink or balloon on the next build.
        rate = indexable / seen
        if not 0.25 <= rate <= 0.75:
            raise RuntimeError(
                f"indexable rate {rate*100:.1f}% is outside the 25-75% band this bar was "
                f"measured at (~43%) — refusing to let the sitemap move this far unchecked")
    return 0


if __name__ == "__main__":
    sys.exit(main())

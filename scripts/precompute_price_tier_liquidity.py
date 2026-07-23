#!/usr/bin/env python3
"""
Precompute per-suburb, per-property-type price-tercile days-on-market stats
-> Gold_Coast.precomputed_price_tier_liquidity.

Backs the off-market positioning card's "value_liquidity_play" frame
(scripts/property_reports/positioning_object.py): the honest question of
whether an AFFORDABLE price point for its suburb genuinely sells faster than
the mid/upper end, verified per-suburb from real sold data — NOT assumed to
be universal. Found 2026-07-23 (see fix-history): the pattern is real and
strong in Robina and Burleigh Waters houses (lower tercile sells ~1.4-2x
faster) but flat in Varsity Lakes houses over the same window — so this must
be data-gated per suburb, never a blanket "affordable = fast" rule.

Source: each suburb's `listing_status: sold` House docs, `sale_price` +
`days_on_market`, over the trailing WINDOW_DAYS. Terciles split the sold
sample into lower/mid/upper by price. `qualifies` is only True when both
tiers have enough sample size AND the lower tier's median DOM is genuinely,
meaningfully faster (not noise) than the upper tier's.

Usage:
  python3 scripts/precompute_price_tier_liquidity.py
  python3 scripts/precompute_price_tier_liquidity.py --suburb robina
  python3 scripts/precompute_price_tier_liquidity.py --dry-run
"""
import argparse
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
PROPERTY_TYPE = "House"
WINDOW_DAYS = 730
MIN_PER_TIER = 15
# Lower tercile must sell in at most this fraction of the upper tercile's
# median DOM to count as a genuine, citable "affordable sells faster" story —
# a small gap could just be noise.
FASTER_THRESHOLD = 0.75


def _parse_price(s):
    if not s or not isinstance(s, str):
        return None
    nums = re.findall(r"\$?([\d,]{6,})", s)
    vals = []
    for n in nums:
        try:
            v = float(n.replace(",", ""))
            if 50000 <= v <= 20_000_000:
                vals.append(v)
        except ValueError:
            pass
    return sum(vals) / len(vals) if vals else None


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def compute_for_suburb(gc, suburb, property_type=PROPERTY_TYPE, window_days=WINDOW_DAYS):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    docs = gc[suburb].find(
        {
            "listing_status": "sold",
            "property_type": property_type,
            "sold_date": {"$gte": cutoff},
            "days_on_market": {"$exists": True, "$ne": None},
        },
        {"sale_price": 1, "days_on_market": 1},
    )
    rows = []
    for d in docs:
        p = _parse_price(d.get("sale_price"))
        dom = d.get("days_on_market")
        if p and isinstance(dom, (int, float)) and dom >= 0:
            rows.append((p, dom))

    n_total = len(rows)
    if n_total < MIN_PER_TIER * 3:
        return {
            "suburb": suburb, "property_type": property_type, "window_days": window_days,
            "n_total": n_total, "qualifies": False, "skip_reason": "insufficient_sample",
        }

    rows.sort()
    prices = [p for p, _ in rows]
    p33 = prices[n_total // 3]
    p66 = prices[2 * n_total // 3]

    tiers = {"lower": [], "mid": [], "upper": []}
    for p, dom in rows:
        if p <= p33:
            tiers["lower"].append(dom)
        elif p <= p66:
            tiers["mid"].append(dom)
        else:
            tiers["upper"].append(dom)

    out_tiers = {}
    for name, doms in tiers.items():
        out_tiers[name] = {
            "n": len(doms),
            "median_dom": _median(doms),
            "avg_dom": round(sum(doms) / len(doms), 1) if doms else None,
        }
    out_tiers["lower"]["max_price"] = p33
    out_tiers["upper"]["min_price"] = p66

    lower_n = out_tiers["lower"]["n"]
    upper_n = out_tiers["upper"]["n"]
    lower_dom = out_tiers["lower"]["median_dom"]
    upper_dom = out_tiers["upper"]["median_dom"]

    qualifies = (
        lower_n >= MIN_PER_TIER and upper_n >= MIN_PER_TIER
        and lower_dom is not None and upper_dom is not None and upper_dom > 0
        and lower_dom <= FASTER_THRESHOLD * upper_dom
    )
    gap_pct = round((1 - lower_dom / upper_dom) * 100, 1) if (qualifies and upper_dom) else None

    return {
        "suburb": suburb,
        "property_type": property_type,
        "window_days": window_days,
        "n_total": n_total,
        "tiers": out_tiers,
        "qualifies": qualifies,
        "gap_pct": gap_pct,  # "affordable homes sell {gap_pct}% faster" — only meaningful when qualifies
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", help="single suburb only")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = get_client()
    gc = client["Gold_Coast"]
    coll = client["Gold_Coast"]["precomputed_price_tier_liquidity"]

    suburbs = [args.suburb] if args.suburb else SUBURBS
    for suburb in suburbs:
        result = compute_for_suburb(gc, suburb)
        result["computed_at"] = datetime.now(timezone.utc).isoformat()
        doc_id = f"{suburb}_{PROPERTY_TYPE}"
        print(f"{suburb}: qualifies={result.get('qualifies')} n_total={result.get('n_total')} "
              f"gap_pct={result.get('gap_pct')}")
        if result.get("tiers"):
            for name, t in result["tiers"].items():
                print(f"  {name}: n={t['n']} median_dom={t['median_dom']}")
        if not args.dry_run:
            coll.update_one({"_id": doc_id}, {"$set": {**result, "_id": doc_id}}, upsert=True)

    if not args.dry_run:
        print(f"\nWrote {len(suburbs)} docs to Gold_Coast.precomputed_price_tier_liquidity")


if __name__ == "__main__":
    main()

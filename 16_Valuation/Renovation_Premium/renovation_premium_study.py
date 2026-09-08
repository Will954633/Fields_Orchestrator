#!/usr/bin/env python3
"""
Renovation Premium Study — does full renovation add price, per suburb?

Reproduces (with proper controls) the 'Before You List' Chapter 5 claim:
  "In Robina and Varsity Lakes, fully renovated properties showed LOWER price
   per square metre than original-condition properties. In Burleigh Waters,
   renovation appeared to add approximately 14% to the price per square metre."
The book itself flagged a floor-area confounder and said "further analysis is
underway" — this script IS that analysis (see 12_Marketing/
House_Improvements_Before_Listing/README.md, Open Questions).

Design (agreed with Will, 2026-09-09) — three legs that must agree:
  Leg 1  Stratified medians   beds x floor-area terciles; time-adjusted $/sqm,
                              renovated vs not, n printed in every cell.
  Leg 2  Hedonic regression   log(price) ~ reno tier + log(floor) + log(land)
                              + beds + baths + water class + quarter FE.
                              PRIMARY estimate; HC3 robust SEs.
  Leg 3  Matched pairs        each fully_renovated sale vs its unrenovated
                              near-twins (same beds & water class, floor +-20%,
                              land +-25%, sale within +-6 months); median gap.
  Secondary                   per-item effects (kitchen / bathrooms / flooring
                              booleans + modern_features_score).

Treatment: vision-model tier property_valuation_data.renovation.
  fully_renovated  vs  {original, tired, cosmetically_updated}.
  partially_renovated reported on the ladder but excluded from the binary
  contrast; new_build excluded entirely (different product).

Key choices and why:
  * Outcome is log(price), NOT $/sqm — dividing by floor area assumes price
    scales 1:1 with it and re-imports the confounder the book flagged.
  * Time drift removed by quarter fixed effects (Leg 2) — subtracting the
    suburb median deflates by an index contaminated by composition. Legs 1/3
    use a quarterly median deflator built on houses, waterfront excluded.
  * `waterfront` class (canal/river/ocean frontage) EXCLUDED — specialist
    market, out of scope platform-wide (shared/waterfront.py).
  * We measure PRICE PREMIUM, not ROI — renovation cost is never observed.

Usage:
  python3 renovation_premium_study.py                 # 24-month window
  python3 renovation_premium_study.py --months 12     # sensitivity cut
  python3 renovation_premium_study.py --months 0      # all available sales
Outputs (next to this script): extract CSV, results JSON, REPORT markdown.
"""

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_gold_coast_db          # noqa: E402
from shared.waterfront import classify_water_relationship, WATERFRONT  # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
OUT_DIR = Path(__file__).resolve().parent

RENO_TIERS = ["original", "tired", "cosmetically_updated",
              "partially_renovated", "fully_renovated", "new_build"]
CONTROL_TIERS = {"original", "tired", "cosmetically_updated"}
TREATED_TIER = "fully_renovated"

# Sanity bounds — outside these, the record is a data error, not a house sale.
PRICE_MIN, PRICE_MAX = 400_000, 8_000_000
FLOOR_MIN, FLOOR_MAX = 50, 900
LAND_MIN, LAND_MAX = 100, 6_000

_price_rx = re.compile(r"[\d,]+")


def parse_price(raw):
    """'$1,520,000' / 'SOLD - $1,520,000' / 1520000 -> float, else None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = _price_rx.findall(str(raw))
    if not m:
        return None
    vals = [float(x.replace(",", "")) for x in m if len(x.replace(",", "")) >= 6]
    if not vals:
        return None
    if len(vals) > 1 and max(vals) / min(vals) > 1.05:
        return None  # a range, not a price
    return vals[0]


def parse_date(doc):
    """Coalesce sale_date / sold_date (newer sold docs only carry sold_date)."""
    for f in ("sale_date", "sold_date"):
        v = doc.get(f)
        if not v:
            continue
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(str(v)[:10])
        except ValueError:
            continue
    return None


def extract(months):
    db = get_gold_coast_db()
    rows, drops = [], defaultdict(int)
    for suburb in SUBURBS:
        cur = db[suburb].find(
            {"listing_status": "sold",
             "property_type": {"$regex": "^house$", "$options": "i"},
             "property_valuation_data.renovation.overall_renovation_level":
                 {"$exists": True, "$ne": None}})
        for doc in cur:
            reno = doc["property_valuation_data"]["renovation"]
            tier = reno.get("overall_renovation_level")
            if tier not in RENO_TIERS:
                drops["unknown_tier"] += 1
                continue
            if tier == "new_build":
                drops["new_build"] += 1
                continue
            price = parse_price(doc.get("sale_price"))
            if price is None or not PRICE_MIN <= price <= PRICE_MAX:
                drops["price"] += 1
                continue
            date = parse_date(doc)
            if date is None:
                drops["date"] += 1
                continue
            floor = doc.get("floor_area_sqm")
            if not floor or not FLOOR_MIN <= float(floor) <= FLOOR_MAX:
                drops["floor"] += 1
                continue
            land = doc.get("land_size_sqm") or doc.get("lot_size_sqm")
            if not land or not LAND_MIN <= float(land) <= LAND_MAX:
                drops["land"] += 1
                continue
            beds, baths = doc.get("bedrooms"), doc.get("bathrooms")
            if not beds or not baths:
                drops["beds_baths"] += 1
                continue
            # classify_water_relationship returns (class, reason) — keep the class only
            water = classify_water_relationship(doc)[0]
            if water == WATERFRONT:
                drops["waterfront_excluded"] += 1
                continue
            rows.append({
                "suburb": suburb,
                "address": doc.get("address") or doc.get("full_address") or "",
                "sale_date": date,
                "quarter": f"{date.year}Q{(date.month - 1) // 3 + 1}",
                "price": price,
                "floor": float(floor),
                "land": float(land),
                "beds": int(beds),
                "baths": int(baths),
                "water": water,
                "tier": tier,
                "kitchen": reno.get("kitchen_renovated"),
                "bathrooms_reno": reno.get("bathrooms_renovated"),
                "flooring": reno.get("flooring_updated"),
                "modern_score": reno.get("modern_features_score"),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("extract produced 0 rows — field names or filters are wrong (Rule 8)")
    df = df.drop_duplicates(subset=["address", "sale_date"])
    latest = df["sale_date"].max()
    if months:
        cutoff = latest - timedelta(days=months * 30.44)
        df = df[df["sale_date"] >= cutoff].copy()
    df["ppsqm"] = df["price"] / df["floor"]
    df["treated"] = df["tier"] == TREATED_TIER
    df["control"] = df["tier"].isin(CONTROL_TIERS)
    return df, dict(drops), latest


def add_deflator(df):
    """Quarterly median-price deflator per suburb (all non-waterfront houses).

    Used only in Legs 1 & 3; Leg 2 uses quarter fixed effects instead.
    price_adj = price / (quarter median / suburb median).
    """
    df = df.copy()
    df["deflator"] = 1.0
    for suburb, g in df.groupby("suburb"):
        overall = g["price"].median()
        qmed = g.groupby("quarter")["price"].median()
        for q, m in qmed.items():
            mask = (df["suburb"] == suburb) & (df["quarter"] == q)
            df.loc[mask, "deflator"] = m / overall
    df["price_adj"] = df["price"] / df["deflator"]
    df["ppsqm_adj"] = df["price_adj"] / df["floor"]
    return df


def leg1_strata(df):
    """beds (3/4/5+) x floor terciles; median time-adjusted $/sqm, treated vs control."""
    out = {}
    for suburb, g in df.groupby("suburb"):
        g = g[g["treated"] | g["control"]].copy()
        g["beds_band"] = g["beds"].clip(upper=5).map({3: "3bed", 4: "4bed", 5: "5+bed"})
        g = g.dropna(subset=["beds_band"])
        try:
            g["floor_band"] = pd.qcut(g["floor"], 3, labels=["small", "medium", "large"])
        except ValueError:
            g["floor_band"] = "all"
        cells = []
        for (bb, fb), cell in g.groupby(["beds_band", "floor_band"], observed=True):
            t, c = cell[cell["treated"]], cell[cell["control"]]
            cells.append({
                "beds": bb, "floor_band": str(fb),
                "floor_range": f"{cell['floor'].min():.0f}-{cell['floor'].max():.0f}sqm",
                "n_reno": len(t), "n_unreno": len(c),
                "med_ppsqm_reno": round(t["ppsqm_adj"].median()) if len(t) else None,
                "med_ppsqm_unreno": round(c["ppsqm_adj"].median()) if len(c) else None,
                "gap_pct": round((t["ppsqm_adj"].median() / c["ppsqm_adj"].median() - 1) * 100, 1)
                           if len(t) >= 3 and len(c) >= 3 else None,
                "thin": len(t) < 5 or len(c) < 5,
            })
        out[suburb] = cells
    return out


def leg2_hedonic(df):
    """log(price) ~ tier ladder + log(floor)+log(land)+beds+baths+water+quarter FE."""
    import statsmodels.formula.api as smf
    results = {}
    ladder = [t for t in RENO_TIERS if t != "new_build"]
    for scope, g in list(df.groupby("suburb")) + [("POOLED", df)]:
        g = g.copy()
        g["log_price"] = np.log(g["price"])
        g["log_floor"] = np.log(g["floor"])
        g["log_land"] = np.log(g["land"])
        # baseline = original+tired merged (thin cells), then the ladder upward
        g["tier_c"] = g["tier"].replace({"tired": "original"})
        cats = [t for t in ladder if t in set(g["tier_c"]) and t != "tired"]
        g["tier_c"] = pd.Categorical(g["tier_c"], categories=cats)
        formula = ("log_price ~ tier_c + log_floor + log_land + beds + baths"
                   " + C(water) + C(quarter)")
        if scope == "POOLED":
            formula += " + C(suburb)"
        m = smf.ols(formula, data=g).fit(cov_type="HC1")
        tiers = {}
        for t in cats[1:]:
            k = f"tier_c[T.{t}]"
            if k in m.params:
                pct = (math.exp(m.params[k]) - 1) * 100
                lo, hi = m.conf_int().loc[k]
                tiers[t] = {"premium_pct": round(pct, 1),
                            "ci_pct": [round((math.exp(lo) - 1) * 100, 1),
                                       round((math.exp(hi) - 1) * 100, 1)],
                            "p": round(float(m.pvalues[k]), 4)}
        results[scope] = {"n": int(m.nobs), "r2": round(m.rsquared, 3),
                          "tiers_vs_original": tiers}
    # Does the fully_renovated premium DIFFER between suburbs? (the book's claim)
    g = df.copy()
    g["log_price"] = np.log(g["price"])
    g["log_floor"] = np.log(g["floor"])
    g["log_land"] = np.log(g["land"])
    g = g[g["treated"] | g["control"]]
    m = smf.ols("log_price ~ treated * C(suburb) + log_floor + log_land + beds"
                " + baths + C(water) + C(quarter)", data=g).fit(cov_type="HC1")
    inter = {k: {"coef_pct": round((math.exp(v) - 1) * 100, 1),
                 "p": round(float(m.pvalues[k]), 4)}
             for k, v in m.params.items() if "treated" in k}
    results["suburb_interaction"] = inter
    return results


def leg3_matched(df):
    """Each fully_renovated sale vs unrenovated near-twins; median % gap."""
    out = {}
    for suburb, g in df.groupby("suburb"):
        treated = g[g["treated"]]
        pool = g[g["control"]]
        gaps, unmatched = [], 0
        for _, t in treated.iterrows():
            c = pool[(pool["beds"] == t["beds"]) &
                     (pool["water"] == t["water"]) &
                     (pool["floor"].between(t["floor"] * 0.8, t["floor"] * 1.2)) &
                     (pool["land"].between(t["land"] * 0.75, t["land"] * 1.25)) &
                     ((pool["sale_date"] - t["sale_date"]).abs()
                      <= timedelta(days=183))]
            if len(c) < 2:
                unmatched += 1
                continue
            gaps.append({"gap_pct": (t["price_adj"] / c["price_adj"].median() - 1) * 100,
                         "n_comps": len(c)})
        gp = [x["gap_pct"] for x in gaps]
        boot = None
        if len(gp) >= 8:
            rng = np.random.default_rng(20260909)
            meds = [np.median(rng.choice(gp, len(gp), replace=True)) for _ in range(2000)]
            boot = [round(float(np.percentile(meds, 2.5)), 1),
                    round(float(np.percentile(meds, 97.5)), 1)]
        out[suburb] = {
            "n_treated": len(treated), "n_matched": len(gaps), "n_unmatched": unmatched,
            "median_gap_pct": round(float(np.median(gp)), 1) if gp else None,
            "mean_gap_pct": round(float(np.mean(gp)), 1) if gp else None,
            "boot_ci_pct": boot,
            "median_comps_per_match": int(np.median([x["n_comps"] for x in gaps])) if gaps else None,
        }
    return out


def secondary_items(df):
    """Which items carry the premium: kitchen / bathrooms / flooring / modern score."""
    import statsmodels.formula.api as smf
    results = {}
    for suburb, g in df.groupby("suburb"):
        g = g.copy().dropna(subset=["kitchen", "bathrooms_reno", "flooring", "modern_score"])
        if len(g) < 60:
            results[suburb] = {"n": len(g), "note": "too few rows with item flags"}
            continue
        g["log_price"] = np.log(g["price"])
        g["log_floor"] = np.log(g["floor"])
        g["log_land"] = np.log(g["land"])
        for col in ("kitchen", "bathrooms_reno", "flooring"):
            g[col] = g[col].astype(bool).astype(int)
        m = smf.ols("log_price ~ kitchen + bathrooms_reno + flooring + modern_score"
                    " + log_floor + log_land + beds + baths + C(water) + C(quarter)",
                    data=g).fit(cov_type="HC1")
        items = {}
        for k in ("kitchen", "bathrooms_reno", "flooring", "modern_score"):
            items[k] = {"premium_pct": round((math.exp(m.params[k]) - 1) * 100, 1),
                        "p": round(float(m.pvalues[k]), 4)}
        results[suburb] = {"n": int(m.nobs), "items": items}
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24,
                    help="window back from latest sale (0 = all)")
    args = ap.parse_args()

    df, drops, latest = extract(args.months)
    df = add_deflator(df)

    tier_counts = {s: g["tier"].value_counts().to_dict() for s, g in df.groupby("suburb")}
    results = {
        "generated": "run via renovation_premium_study.py",
        "window_months": args.months,
        "latest_sale": str(latest.date()),
        "n_total": len(df),
        "n_by_suburb": df.groupby("suburb").size().to_dict(),
        "drops": drops,
        "tier_counts": tier_counts,
        "leg1_strata": leg1_strata(df),
        "leg2_hedonic": leg2_hedonic(df),
        "leg3_matched": leg3_matched(df),
        "secondary_items": secondary_items(df),
    }

    tag = f"{args.months}m" if args.months else "all"
    csv_path = OUT_DIR / f"extract_{tag}.csv"
    json_path = OUT_DIR / f"results_{tag}.json"
    df.drop(columns=["address"]).to_csv(csv_path, index=False)  # no addresses in shared artifacts
    json_path.write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps(results, indent=1, default=str))
    print(f"\nwrote {csv_path}\nwrote {json_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

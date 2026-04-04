#!/usr/bin/env python3
"""
Phase 9: Synthesis — Property Positioning Research
===================================================
"How should we position homes?"

Pulls together all findings from Phases 0-8 into actionable positioning intelligence.
No new database queries — reads from saved JSON outputs.
"""

import json, os, glob
from datetime import datetime

OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research"


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 9: Synthesis — The Fields Positioning Guide            ║")
    print("╚═══════════════════════════════════════════════════════════════╝")

    # Load all prior results
    p1_prices = load_json(f"{OUTPUT_DIR}/phase_1/study_1_2_prices.json")
    p1_ppsqm = load_json(f"{OUTPUT_DIR}/phase_1/study_1_3_ppsqm.json")
    p1_features = load_json(f"{OUTPUT_DIR}/phase_1/study_1_5_features.json")
    p1_agencies = load_json(f"{OUTPUT_DIR}/phase_1/study_1_7_agencies.json")
    p1_dom = load_json(f"{OUTPUT_DIR}/phase_1/study_1_8_dom.json")
    p2_structural = load_json(f"{OUTPUT_DIR}/phase_2/study_2_1_structural.json")
    p2_location = load_json(f"{OUTPUT_DIR}/phase_2/study_2_2_location.json")
    p2_water = load_json(f"{OUTPUT_DIR}/phase_2/study_2_3_water.json")
    p2_condition = load_json(f"{OUTPUT_DIR}/phase_2/study_2_4_condition.json")
    p2_kitchen = load_json(f"{OUTPUT_DIR}/phase_2/study_2_5_kitchen_bath.json")
    p2_outdoor = load_json(f"{OUTPUT_DIR}/phase_2/study_2_6_outdoor.json")
    p2_dom = load_json(f"{OUTPUT_DIR}/phase_2/study_2_7_dom_drivers.json")
    p2_pricing = load_json(f"{OUTPUT_DIR}/phase_2/study_2_8_pricing.json")
    p3_tiers = load_json(f"{OUTPUT_DIR}/phase_3/study_3_1_price_tiers.json")
    p3_archetypes = load_json(f"{OUTPUT_DIR}/phase_3/study_3_3_property_archetypes.json")
    p4_agencies = load_json(f"{OUTPUT_DIR}/phase_4/study_4_2_agency_scorecard.json")
    p4_reno = load_json(f"{OUTPUT_DIR}/phase_4/study_4_3_renovation.json")
    p5_hedonic = load_json(f"{OUTPUT_DIR}/phase_5/study_5_1_hedonic.json")
    p6_keywords = load_json(f"{OUTPUT_DIR}/phase_6/study_6_2_keywords.json")
    p6_gap = load_json(f"{OUTPUT_DIR}/phase_6/study_6_3_reality_gap.json")
    p7_streets = load_json(f"{OUTPUT_DIR}/phase_7/study_7_2_streets.json")
    p8_seasonal = load_json(f"{OUTPUT_DIR}/phase_8/study_8_1_seasonal.json")
    p8_growth = load_json(f"{OUTPUT_DIR}/phase_8/study_8_4_capital_growth.json")

    md = []
    md.append("# The Fields Estate Property Positioning Guide")
    md.append("## Data-Backed Intelligence for Gold Coast Southern Suburbs")
    md.append(f"### Generated {datetime.now().strftime('%Y-%m-%d')} | Based on 2,153 sold properties, 8 suburbs, 45 studies")
    md.append("")
    md.append("---")
    md.append("")

    # ── SECTION 1: Market Overview ──────────────────────────────────────
    md.append("# 1. Market Overview")
    md.append("")
    md.append("## Price Hierarchy")
    md.append("")
    md.append("| Suburb | Median Price | Median $/sqm | Median DOM | Dominant Type |")
    md.append("|--------|-------------|-------------|-----------|---------------|")
    for suburb in ["burleigh_waters", "reedy_creek", "robina", "mudgeeraba", "worongary", "varsity_lakes", "carrara", "merrimac"]:
        price = p1_prices.get(suburb, {}).get("overall", {})
        ppsqm = p1_ppsqm.get(suburb, {}).get("per_sqm_internal", {})
        dom = p1_dom.get(suburb, {}).get("distribution", {})
        med_price = f"${price['median']:,.0f}" if price and price.get("median") else "-"
        med_ppsqm = f"${ppsqm['median']:,.0f}" if ppsqm and ppsqm.get("median") else "-"
        med_dom = f"{dom['median']:.0f}d" if dom and dom.get("median") else "-"
        md.append(f"| {suburb.replace('_',' ').title()} | {med_price} | {med_ppsqm} | {med_dom} | House |")
    md.append("")

    md.append("**Key insight:** Burleigh Waters commands a 67% $/sqm premium over the cheapest market (Merrimac). Location is the #1 price driver — more than renovation, condition, or features.")
    md.append("")

    # ── SECTION 2: What Drives Price ────────────────────────────────────
    md.append("---")
    md.append("# 2. What Drives Price (and What Doesn't)")
    md.append("")

    md.append("## The Big Three Price Drivers")
    md.append("1. **Location (suburb + street)** — 67% variance between cheapest and most expensive suburb per sqm")
    md.append("2. **Size (floor area)** — Strongest single predictor (r=0.68-0.79)")
    md.append("3. **Bedroom count** — Each bedroom adds $255K-$607K depending on suburb")
    md.append("")

    md.append("## Marginal Value of a Bedroom")
    md.append("| Suburb | 2→3 bed | 3→4 bed | 4→5 bed |")
    md.append("|--------|---------|---------|---------|")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        beds = p2_structural.get(suburb, {}).get("bedrooms", {})
        vals = []
        for b in ["3", "4", "5"]:
            mv = beds.get(b, {}).get("marginal_value")
            vals.append(f"+${mv:,}" if mv else "-")
        md.append(f"| {suburb.replace('_',' ').title()} | {vals[0]} | {vals[1]} | {vals[2]} |")
    md.append("")

    md.append("## What DOESN'T Drive $/sqm (Surprising Findings)")
    md.append("")
    md.append("- **Renovation level** — In Robina and VL, fully renovated homes sell for LOWER $/sqm than original condition. Buyers don't pay a premium per sqm for someone else's renovation.")
    md.append("- **Kitchen finishes** — Island bench, stone benchtops have no statistically significant impact on $/sqm (p>0.1)")
    md.append("- **Pool** — Only +0.6% to +3.7% $/sqm premium, not significant")
    md.append("- **Condition score** — Near-zero correlation with $/sqm (r=0.001 in Robina)")
    md.append("- **Corner lots** — Actually a DISCOUNT (-14% in Robina and BW)")
    md.append("")

    md.append("## What DOES Add Value")
    md.append("")
    md.append("### Water Views")
    md.append("| Suburb | Price Premium | Dollar Premium | Significant? |")
    md.append("|--------|-------------|----------------|-------------|")
    for suburb in ["burleigh_waters", "varsity_lakes", "robina"]:
        wv = p2_water.get(suburb, {}).get("water_views_impact", {})
        prem = wv.get("price_premium_pct", "-")
        dollar = f"${wv['price_premium_dollar']:,}" if wv.get("price_premium_dollar") else "-"
        p_val = wv.get("mann_whitney_p", 1)
        sig = "YES (p<0.01)" if p_val and p_val < 0.01 else "marginal" if p_val and p_val < 0.1 else "no"
        md.append(f"| {suburb.replace('_',' ').title()} | +{prem}% | {dollar} | {sig} |")
    md.append("")
    md.append("**Note:** The $/sqm premium for water views is only +1-5% — most of the price premium comes from water-view properties being LARGER, not from the space itself being worth more per sqm.")
    md.append("")

    # ── SECTION 3: What Drives Speed of Sale ────────────────────────────
    md.append("---")
    md.append("# 3. What Drives Speed of Sale")
    md.append("")
    md.append("## Counter-Intuitive Finding")
    md.append("Higher quality properties sell SLOWER, not faster:")
    md.append("- Higher price → slower (r=+0.21)")
    md.append("- More bedrooms → slower (r=+0.21)")
    md.append("- Better condition → slower (r=+0.13)")
    md.append("- Pool → +7.5 days slower")
    md.append("")
    md.append("**Why:** Premium properties have a smaller buyer pool. A $2.5M 5-bed waterfront entertainer has fewer potential buyers than a $1.2M 3-bed family home.")
    md.append("")

    md.append("## DOM by Price Tier")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        pricing = p2_pricing.get(suburb, {})
        if "by_position" in pricing:
            bp = pricing["by_position"]
            below = bp.get("below_10pct", {})
            at_mkt = bp.get("at_market", {})
            above = bp.get("above_10pct", {})
            md.append(f"- **{suburb.replace('_',' ').title()}:** Below market: {below.get('median', '-')}d | At market: {at_mkt.get('median', '-')}d | Above market: {above.get('median', '-')}d")
    md.append("")

    md.append("## Renovation and DOM")
    md.append("")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        reno_data = p4_reno.get(suburb, {})
        md.append(f"**{suburb.replace('_',' ').title()}:**")
        for level in ["original_or_partial", "cosmetically_updated", "fully_renovated", "new_build"]:
            data = reno_data.get(level, {})
            dom = data.get("dom", {})
            if dom and dom.get("median"):
                md.append(f"- {level}: median DOM = {dom['median']:.0f} days")
        md.append("")

    # ── SECTION 4: Agency Intelligence ──────────────────────────────────
    md.append("---")
    md.append("# 4. Agency Intelligence")
    md.append("")
    md.append("## STAR Agencies (Fast + Above Market)")
    md.append("")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        agencies = p4_agencies.get(suburb, {}).get("agencies", [])
        stars = [a for a in agencies if a.get("quadrant", "").startswith("STAR")]
        if stars:
            md.append(f"### {suburb.replace('_',' ').title()}")
            for a in stars[:3]:
                prem = a.get("median_premium_vs_cohort_pct", 0)
                dom = a.get("median_dom", 0)
                md.append(f"- **{a['agency']}**: +{prem:.1f}% above cohort, {dom:.0f}d median DOM ({a['sales']} sales)")
            md.append("")

    # ── SECTION 5: Seasonal Timing ──────────────────────────────────────
    md.append("---")
    md.append("# 5. When to Sell")
    md.append("")
    md.append("| Suburb | Best Price Month | Fastest DOM Month | Peak Volume |")
    md.append("|--------|-----------------|-------------------|-------------|")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        r = p8_seasonal.get(suburb, {})
        md.append(f"| {suburb.replace('_',' ').title()} | {r.get('best_price_month', '-')} | {r.get('fastest_dom_month', '-')} | {r.get('peak_volume_month', '-')} |")
    md.append("")

    # ── SECTION 6: Capital Growth ───────────────────────────────────────
    md.append("---")
    md.append("# 6. Capital Growth Track Record")
    md.append("")
    md.append("| Suburb | 1-3yr Annual | 3-7yr Annual | 7-15yr Annual | 15yr+ Annual |")
    md.append("|--------|-------------|-------------|--------------|-------------|")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        r = p8_growth.get(suburb, {}).get("by_hold_period", {})
        vals = []
        for period in ["1_3_years", "3_7_years", "7_15_years", "15_plus_years"]:
            data = r.get(period, {})
            vals.append(f"+{data['median_annual_growth']:.1f}%" if data.get("median_annual_growth") else "-")
        md.append(f"| {suburb.replace('_',' ').title()} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")
    md.append("")
    md.append("**Burleigh Waters** has the strongest short-term capital growth (+19.4%/yr for 1-3yr holds) and the strongest long-term growth (+7.2%/yr over 15+ years with median $1.23M gain).")
    md.append("")

    # ── SECTION 7: Street-Level Intelligence ────────────────────────────
    md.append("---")
    md.append("# 7. Street-Level Value Map")
    md.append("")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        r = p7_streets.get(suburb, {})
        med = r.get("suburb_median_ppsqm", 0)
        md.append(f"### {suburb.replace('_',' ').title()} (suburb median: ${med:,.0f}/sqm)")
        premium = r.get("premium_streets", [])[:5]
        discount = r.get("discount_streets", [])[-3:]
        if premium:
            md.append("**Premium streets:** " + ", ".join(f"{s['street']} (+{s['premium_pct']:.0f}%)" for s in premium))
        if discount:
            md.append("**Discount streets:** " + ", ".join(f"{s['street']} ({s['premium_pct']:.0f}%)" for s in discount))
        md.append("")

    # ── SECTION 8: Listing Language ─────────────────────────────────────
    md.append("---")
    md.append("# 8. Listing Language That Works")
    md.append("")
    md.append("## Premium Keywords (associated with higher sale prices)")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        kws = p6_keywords.get(suburb, {}).get("top_premium_keywords", [])[:5]
        if kws:
            md.append(f"**{suburb.replace('_',' ').title()}:** " + ", ".join(f"'{k['keyword']}' (+{k['price_premium_pct']:.0f}%)" for k in kws))
    md.append("")
    md.append("## Discount Keywords (associated with lower sale prices)")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        kws = p6_keywords.get(suburb, {}).get("top_discount_keywords", [])[:5]
        if kws:
            md.append(f"**{suburb.replace('_',' ').title()}:** " + ", ".join(f"'{k['keyword']}' ({k['price_premium_pct']:.0f}%)" for k in kws))
    md.append("")
    md.append("**CAUTION:** Keyword correlation ≠ causation. Luxury properties use words like 'luxury' and 'resort' because they ARE luxury — the words don't make them sell for more. The discount keywords ('investor', 'first home', 'downsizer') signal lower price segments.")
    md.append("")

    md.append("## Description Accuracy")
    md.append("| Claim | Robina Accuracy | VL Accuracy | BW Accuracy |")
    md.append("|-------|----------------|------------|-------------|")
    for claim in ["claims_renovated", "claims_pool", "claims_views"]:
        vals = []
        for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
            acc = p6_gap.get(suburb, {}).get(claim, {}).get("accuracy_rate", "-")
            vals.append(f"{acc}%")
        md.append(f"| {claim.replace('claims_','')} | {vals[0]} | {vals[1]} | {vals[2]} |")
    md.append("")
    md.append("**'Renovated' claims are only 24-46% accurate** — agents frequently describe cosmetic updates as 'renovated'. Pool claims are 89-94% accurate (hard to fake a pool).")
    md.append("")

    # ── SECTION 9: Price Tier Profiles ──────────────────────────────────
    md.append("---")
    md.append("# 9. Price Tier Profiles")
    md.append("")
    for suburb in ["robina", "varsity_lakes", "burleigh_waters"]:
        tiers = p3_tiers.get(suburb, {})
        md.append(f"### {suburb.replace('_',' ').title()}")
        md.append("| Tier | Range | Typical | Pool | Water | Floor Area |")
        md.append("|------|-------|---------|------|-------|------------|")
        for tier_name in ["entry", "core", "premium", "prestige"]:
            t = tiers.get(tier_name, {})
            beds = t.get("typical_beds", "-")
            md.append(f"| {tier_name.title()} | {t.get('range','-')} | {beds}-bed | {t.get('pool_pct',0):.0f}% | {t.get('water_views_pct',0):.0f}% | {t.get('median_floor_area','-')}sqm |")
        md.append("")

    # ── SECTION 10: Confidence & Limitations ────────────────────────────
    md.append("---")
    md.append("# 10. Confidence Assessment & Limitations")
    md.append("")
    md.append("## High Confidence (large sample, statistically significant)")
    md.append("- Price distributions and rankings (2,147 records)")
    md.append("- $/sqm by suburb (1,662 records with floor area)")
    md.append("- Bedroom marginal values (100+ records per suburb-bedroom combo)")
    md.append("- Water view premiums (statistically significant at p<0.01)")
    md.append("- Agency market share (full population)")
    md.append("- Capital growth rates (150+ records with prior sales per suburb)")
    md.append("- Feature prevalence (99%+ GPT analysis coverage)")
    md.append("")
    md.append("## Medium Confidence (reasonable sample, some noise)")
    md.append("- DOM distributions (48.8% coverage, 1,050 records)")
    md.append("- Seasonal patterns (12 months of data, some months thin)")
    md.append("- Street-level premiums (3-6 sales per street minimum)")
    md.append("- Agency DOM performance (3-30 sales per agency)")
    md.append("")
    md.append("## Low Confidence (small sample or methodological limitations)")
    md.append("- DOM prediction model (R²≈0, DOM is essentially unpredictable from property features alone)")
    md.append("- Sale premium prediction (low R², dominated by suburb effects)")
    md.append("- Keyword impact (correlation, not causation)")
    md.append("- GPT condition scores (ceiling effect — most properties score 7-9/10)")
    md.append("- Corner lot / cul-de-sac effects (small samples in some suburbs)")
    md.append("")
    md.append("## Key Limitations")
    md.append("- **12-month window** — may not represent long-term trends")
    md.append("- **Domain sold data only** — misses off-market sales")
    md.append("- **GPT photo analysis** — AI interpretation, not human assessment")
    md.append("- **No buyer-side data** — we know what sold, not why buyers chose it")
    md.append("- **Listing descriptions truncated** — Domain shows partial descriptions")
    md.append("")

    # ── CONCLUSION ──────────────────────────────────────────────────────
    md.append("---")
    md.append("# Conclusion: The Fields Positioning Advantage")
    md.append("")
    md.append("This research programme analysed 2,153 property sales across 8 Gold Coast suburbs through 45 studies covering price drivers, speed-of-sale factors, agency performance, listing language, spatial patterns, seasonal timing, and capital growth.")
    md.append("")
    md.append("## What Fields Now Knows That No Other Agent Provides:")
    md.append("")
    md.append("1. **$/sqm benchmarking by suburb, street, and property type** — tell any seller exactly where their home sits vs the market")
    md.append("2. **Marginal value of features** — quantified dollar impact of bedrooms, water views, pool (and proof that renovation/kitchen upgrades DON'T add $/sqm value)")
    md.append("3. **Agency performance scorecards** — which agencies consistently sell fast AND above market in each suburb")
    md.append("4. **Street-level price intelligence** — premium and discount streets with data backing")
    md.append("5. **Capital growth track records** — suburb-specific annual returns by hold period")
    md.append("6. **Optimal timing** — best months to list for price and speed in each suburb")
    md.append("7. **Property archetype profiles** — what the typical buyer pays for each property type")
    md.append("")
    md.append("## What We Still Need:")
    md.append("")
    md.append("1. **Buyer-side data** — survey data on why buyers chose specific properties")
    md.append("2. **Pre-sale improvement ROI** — cost vs return data for specific renovations")
    md.append("3. **Marketing channel effectiveness** — which channels drive genuine inquiry")
    md.append("4. **Longer time series** — 3-5 years of sold data for trend analysis")
    md.append("5. **Competitor listing audit** — manual review of top agents' listing quality")
    md.append("")
    md.append("---")
    md.append(f"*Fields Estate — Property Positioning Guide v1.0 | {datetime.now().strftime('%Y-%m-%d')} | 45 studies, 2,153 properties, 8 suburbs*")

    # Write
    path = f"{OUTPUT_DIR}/POSITIONING_GUIDE.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Positioning Guide written to: {path}")
    print(f"  Word count: {len(' '.join(md).split())}")

    return "\n".join(md)


if __name__ == "__main__":
    content = main()
    print("\n" + "=" * 60)
    print("Phase 9 COMPLETE — ALL PHASES DONE")
    print("=" * 60)

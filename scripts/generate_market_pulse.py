#!/usr/bin/env python3
"""
generate_market_pulse.py — Monthly AI-generated market summaries per category per suburb.

Fetches real market data from MongoDB, sends it to Claude Sonnet with category-specific
prompts, and stores the resulting summaries in system_monitor.market_pulse.

Usage:
    python3 scripts/generate_market_pulse.py                  # all suburbs, monthly guard
    python3 scripts/generate_market_pulse.py --force           # skip monthly guard
    python3 scripts/generate_market_pulse.py --suburb robina   # single suburb
    python3 scripts/generate_market_pulse.py --dry-run         # print prompts, don't call API
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pymongo import MongoClient
import anthropic

# ─── Config ───────────────────────────────────────────────────────────────────

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
DISPLAY_NAMES = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}
MODEL = "claude-sonnet-4-6"
MONTHLY_GUARD_DAYS = 25  # won't re-run within 25 days unless --force

CATEGORIES = [
    {
        "id": "sell-now",
        "title": "Should I Sell Now?",
        "charts": ["median_price", "dom", "sales_volume", "price_adjustments", "vendor_discount", "absorption_rate"],
    },
    {
        "id": "buy",
        "title": "Is Now a Good Time to Buy?",
        "charts": ["median_price", "yoy_growth", "qoq_growth", "active_listings", "new_listings", "asking_prices", "absorption_rate"],
    },
    {
        "id": "crash-risk",
        "title": "Crash Risk",
        "charts": ["market_signals", "yoy_growth", "vendor_discount", "absorption_rate", "capital_gain"],
    },
    {
        "id": "overview",
        "title": "Market Overview",
        "charts": ["median_price", "sales_volume", "turnover_rate", "active_listings", "new_listings", "yoy_growth", "dom"],
    },
    {
        "id": "houses-vs-units",
        "title": "Houses vs Units",
        "charts": ["house_type_race", "asking_prices", "median_price", "capital_gain"],
    },
    {
        "id": "direction",
        "title": "Market Direction",
        "charts": ["forecast", "market_signals", "qoq_growth", "yoy_growth", "suburb_dna"],
    },
    {
        "id": "suburb-compare",
        "title": "Suburb Comparison",
        "charts": ["capital_gain", "suburb_motion", "suburb_dna", "turnover_rate"],
    },
]


# ─── Data Fetching ────────────────────────────────────────────────────────────

def fetch_all_data(gc_db, sm_db, suburb):
    """Fetch all available market data for a suburb, return as a structured dict."""
    data = {}
    display = DISPLAY_NAMES.get(suburb, suburb.replace("_", " ").title())

    # 1. Indexed prices (quarterly medians)
    idx = gc_db["precomputed_indexed_prices"].find_one({"_id": suburb})
    if idx:
        series = idx.get("indexed_series", [])
        recent = series[-8:] if len(series) >= 8 else series
        data["median_price_history"] = [
            {
                "period": q.get("period", ""),
                "median_price": q.get("median_price"),
                "index_value": q.get("index_value"),
                "transaction_count": q.get("transaction_count"),
            }
            for q in recent
        ]
        if len(series) >= 5:
            latest = series[-1].get("median_price", 0)
            year_ago = series[-5].get("median_price", 0) if len(series) >= 5 else 0
            if year_ago and latest:
                data["yoy_growth_pct"] = round((latest - year_ago) / year_ago * 100, 1)
            if len(series) >= 2:
                prev = series[-2].get("median_price", 0)
                if prev:
                    data["qoq_growth_pct"] = round((latest - prev) / prev * 100, 1)
            data["current_median_price"] = latest
        # 10-year journey
        if len(series) >= 40:
            ten_yr_start = series[-40].get("median_price", 0)
            ten_yr_end = series[-1].get("median_price", 0)
            if ten_yr_start and ten_yr_end:
                data["ten_year_growth_pct"] = round((ten_yr_end - ten_yr_start) / ten_yr_start * 100, 1)
                data["ten_year_start_price"] = ten_yr_start
                data["ten_year_end_price"] = ten_yr_end

    # 2. Days on Market
    dom_doc = gc_db["precomputed_market_charts"].find_one({"_id": f"{suburb}_days_on_market"})
    if dom_doc:
        timeline = dom_doc.get("dom_timeline", dom_doc.get("timeline", []))
        if timeline:
            latest_dom = timeline[-1]
            data["dom_median"] = latest_dom.get("median_days_on_market")
            data["dom_avg"] = latest_dom.get("avg_days_on_market")
            data["dom_period"] = latest_dom.get("period", "")
            data["dom_quick_sales_pct"] = latest_dom.get("quick_sales_pct")
            if len(timeline) >= 5:
                prev_dom = timeline[-5]
                data["dom_yoy_prev"] = prev_dom.get("median_days_on_market")

    # 3. Sales Volume
    sv_doc = gc_db["precomputed_market_charts"].find_one({"_id": f"{suburb}_sales_volume"})
    if sv_doc:
        timeline = sv_doc.get("timeline", [])
        if timeline:
            latest_sv = timeline[-1]
            data["sales_volume_latest"] = latest_sv.get("sales_count")
            data["sales_volume_period"] = latest_sv.get("period", "")
            data["sales_volume_yoy_change"] = latest_sv.get("yoy_change")
            if len(timeline) >= 2:
                data["sales_volume_prev"] = timeline[-2].get("sales_count")

    # 4. Turnover Rate
    tr_doc = gc_db["precomputed_market_charts"].find_one({"_id": f"{suburb}_turnover_rate"})
    if tr_doc:
        timeline = tr_doc.get("timeline", [])
        if timeline:
            latest_tr = timeline[-1]
            data["turnover_rate"] = latest_tr.get("turnover_rate")
            data["turnover_year"] = latest_tr.get("year")
            data["turnover_sales"] = latest_tr.get("sales")
        data["total_stock"] = tr_doc.get("total_stock")

    # 5. Active Listings
    al_doc = gc_db["precomputed_active_listings"].find_one({"_id": suburb})
    if al_doc:
        snapshots = al_doc.get("snapshots", [])
        if snapshots:
            latest_al = snapshots[-1]
            data["active_listings"] = latest_al.get("active_listings")
            # Month ago comparison
            if len(snapshots) >= 30:
                month_ago = snapshots[-30]
                old_count = month_ago.get("active_listings", 0)
                new_count = latest_al.get("active_listings", 0)
                if old_count:
                    data["active_listings_mom_pct"] = round((new_count - old_count) / old_count * 100, 1)

    # 6. Absorption Rate (calculated: active listings / monthly sales rate)
    active = gc_db[suburb].count_documents({"listing_status": "for_sale"})
    ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    sold_90d = gc_db[suburb].count_documents({
        "listing_status": "sold",
        "sold_date": {"$gte": ninety_days_ago}
    })
    monthly_sales = sold_90d / 3.0 if sold_90d > 0 else 0
    if monthly_sales > 0:
        data["absorption_rate_months"] = round(active / monthly_sales, 1)
        data["absorption_monthly_sales"] = round(monthly_sales, 1)
    data["absorption_active"] = active

    # 7. Price Change Events
    events = list(sm_db["price_change_events"].find(
        {"suburb": {"$regex": suburb.replace("_", " "), "$options": "i"}},
        {"direction": 1, "change_pct": 1, "days_on_market": 1, "_id": 0}
    ).limit(100))
    if events:
        reductions = [e for e in events if e.get("direction") == "reduction"]
        increases = [e for e in events if e.get("direction") == "increase"]
        data["price_reductions_count"] = len(reductions)
        data["price_increases_count"] = len(increases)
        data["price_total_adjustments"] = len(events)

    # 8. Vendor Discount
    pipeline = [
        {"$match": {"listing_status": "sold", "vendor_discount_pct": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": None,
            "avg_discount": {"$avg": "$vendor_discount_pct"},
            "median_discount": {"$avg": "$vendor_discount_pct"},  # approx
            "count": {"$sum": 1}
        }}
    ]
    try:
        vd_result = list(gc_db[suburb].aggregate(pipeline))
        if vd_result:
            data["vendor_discount_avg_pct"] = round(vd_result[0].get("avg_discount", 0), 1)
            data["vendor_discount_count"] = vd_result[0].get("count", 0)
    except Exception:
        pass

    # 9. SQM Asking Prices
    sqm = gc_db["sqm_asking_prices"].find_one({"suburb": {"$regex": display, "$options": "i"}})
    if sqm:
        series = sqm.get("series", [])
        if series:
            latest_sqm = series[-1]
            data["asking_price_houses"] = latest_sqm.get("houses_all")
            data["asking_price_units"] = latest_sqm.get("units_all")
            data["asking_price_combined"] = latest_sqm.get("combined")
            data["asking_price_date"] = latest_sqm.get("date")
            # 3-month trend
            if len(series) >= 13:
                three_months_ago = series[-13]
                old_combined = three_months_ago.get("combined", 0)
                if old_combined:
                    data["asking_price_3m_change_pct"] = round(
                        (latest_sqm.get("combined", 0) - old_combined) / old_combined * 100, 1
                    )

    # 10. Market Signals
    signals_doc = sm_db["market_signals"].find_one({"_id": "market_signals_latest"})
    if signals_doc:
        suburbs_data = signals_doc.get("suburbs", {})
        suburb_signals = suburbs_data.get(suburb, {})
        if suburb_signals:
            data["overall_sentiment"] = suburb_signals.get("overallSentiment")
            signals = suburb_signals.get("signals", [])
            data["market_signals"] = [
                {
                    "indicator": s.get("displayName"),
                    "value": s.get("currentValue"),
                    "trend": s.get("trend"),
                    "signal": s.get("signal"),
                }
                for s in signals
            ]

    # 11. Capital gain comparison (indexed prices for all target suburbs)
    capital_gains = {}
    for s in TARGET_SUBURBS:
        s_idx = gc_db["precomputed_indexed_prices"].find_one({"_id": s})
        if s_idx:
            s_series = s_idx.get("indexed_series", [])
            if s_series:
                capital_gains[DISPLAY_NAMES.get(s, s)] = {
                    "latest_index": s_series[-1].get("index_value"),
                    "latest_median": s_series[-1].get("median_price"),
                }
                if len(s_series) >= 20:
                    capital_gains[DISPLAY_NAMES.get(s, s)]["five_year_index"] = s_series[-20].get("index_value")
    data["capital_gains_comparison"] = capital_gains

    # 12. Asking prices houses vs units divergence
    if "asking_price_houses" in data and "asking_price_units" in data:
        data["asking_house_unit_spread"] = round(
            data["asking_price_houses"] - data["asking_price_units"], 0
        )

    data["suburb_display"] = display
    data["data_date"] = datetime.now().strftime("%Y-%m-%d")

    return data


# ─── Prompt Templates ────────────────────────────────────────────────────────

CATEGORY_PROMPTS = {
    "sell-now": """You are writing a market summary for a homeowner in {suburb} who is considering selling their property.
They are anxious about timing — they don't want to sell too early (miss further gains) or too late (catch a downturn).

Here is the current market data for {suburb}:
{data}

Write a 3-4 sentence market summary that:
1. Opens with "Should you sell your house in {suburb} now?"
2. Gives a direct verdict: conditions currently favour sellers / market is balanced / conditions favour buyers
3. Cites the 2-3 most telling data points (DOM, absorption rate, price adjustments, volume, vendor discount)
4. Ends with one forward-looking sentence — what signal to watch that could change the verdict
5. Format numbers as: $1,250,000 (not "$1.25m"), percentages to 1 decimal

Also return a structured verdict as one of: "strong_sellers_market", "sellers_advantage", "balanced", "buyers_advantage", "strong_buyers_market"
And return 2-3 key_signals as JSON objects with metric, value, and interpretation.

Return your response as JSON:
{{
  "summary": "your 3-4 sentence summary here",
  "verdict": "one of the verdict strings",
  "key_signals": [
    {{"metric": "absorption_rate", "value": "3.2 months", "interpretation": "Below 4 months = seller's market"}}
  ]
}}""",

    "buy": """You are writing for someone considering buying a home in {suburb}.
They want to know: is now a smart time to enter the market, or should they wait?

Here is the current market data for {suburb}:
{data}

Write a 3-4 sentence summary that:
1. Opens with "Is now a good time to buy a house in {suburb}?"
2. Gives a direct assessment of buyer conditions (strong/moderate/limited negotiating power)
3. References price growth momentum, listing supply, and absorption rate
4. Ends with practical context — what the data suggests about price direction

Also return a verdict: "strong_buyer_conditions", "moderate_buyer_conditions", "neutral", "limited_buyer_power", "very_limited_buyer_power"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "crash-risk": """You are writing for someone worried the Gold Coast property market might crash.
They may be an anxious homeowner or a hesitant buyer. They need honest, data-backed reassurance — not dismissal of their fears. If warning signs exist, say so.

IMPORTANT CONTEXT — Our proprietary analysis of 27 economic datasets across 8 Gold Coast suburbs (2015-2025) found that:
- The #1 real-time indicator of market strength is Queensland HOUSEHOLD SPENDING (r=0.914 correlation with house prices)
- The best LEADING indicator is the WAGE PRICE INDEX for QLD — it leads house prices by 3-4 months (r=0.940)
- INTEREST RATES LAG prices by 12 months (r=0.791) — the RBA is reactive, not predictive
- CREDIT/LENDING GROWTH lags prices by 3.5 months (r=0.948) — it confirms what already happened
- The most crash-sensitive suburb is Burleigh Waters (highest economic correlation); Worongary is most insulated

ACADEMIC VALIDATION — Peer-reviewed research (Abelson et al. 2005, The Economic Record) on 33 years of Australian national data confirms:
- Real disposable income has a LONG-RUN ELASTICITY of 1.71 — a 1% income rise produces a 1.71% house price rise (amplification effect)
- Australian house prices are ASYMMETRIC: when rising, the market adjusts to equilibrium in ~4 quarters. When FALLING, it takes ~6 quarters (50% slower). This means sharp crashes are structurally unlikely — prices stagnate rather than collapse.
- Housing SUPPLY per capita has the largest single coefficient (-3.6 elasticity). Rising supply is the biggest structural risk factor.

Your crash risk assessment should primarily reference these leading indicators (wages, household spending) rather than backward-looking metrics. If wages are rising and household spending is up, a crash is unlikely regardless of what interest rates are doing. If wages are plateauing or falling, that IS a genuine warning sign. Also mention the asymmetric adjustment finding — Australian house prices historically fall slowly (6 quarters to adjust), making sudden crashes structurally unlikely.

Here is the current market data for {suburb}:
{data}

Write a 3-4 sentence summary that:
1. Opens with "Is the Gold Coast property market going to crash?"
2. Acknowledges the concern honestly, then assesses crash risk based on the LEADING indicators (wage growth trend, household spending, lending)
3. References the current market signals data and what they mean for crash probability
4. If bearish signals exist, name them honestly. If bullish, explain which leading indicators support continued strength
5. DO NOT reference "10-year resilience" or "long-term price history" — focus on forward-looking indicators

Verdict: "very_low_risk", "low_risk", "moderate_risk", "elevated_risk", "high_risk"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "overview": """You are writing a market overview for {suburb} aimed at someone unfamiliar with the area — perhaps an interstate investor or first-time researcher.

Here is the current market data for {suburb}:
{data}

Write a 3-4 sentence overview that:
1. Opens with "What is the {suburb} property market doing?"
2. Covers the headline numbers: median price, recent sales volume, DOM, active listings
3. Gives context on whether the market is accelerating, stable, or cooling
4. Keeps a neutral, analytical tone

Verdict: "strong_growth", "moderate_growth", "stable", "cooling", "declining"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "houses-vs-units": """You are writing for an investor or buyer in {suburb} deciding between a house and a unit.

Here is the current market data for {suburb}:
{data}

Write a 3-4 sentence summary that:
1. Opens with "Are houses or units a better investment in {suburb}?"
2. Compares asking prices for houses vs units (the spread)
3. References any divergence in price trends between the two types
4. Gives a direct observation on which type is showing stronger momentum

Verdict: "houses_strongly_outperforming", "houses_outperforming", "similar_performance", "units_outperforming", "units_strongly_outperforming"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "direction": """You are writing for someone who wants to know which way the {suburb} property market is heading — they're timing a major buy or sell decision.

IMPORTANT CONTEXT — Research shows:
- Queensland wage growth LEADS house prices by 3-4 months (r=0.940). Current wage trend is the best predictor of where prices are heading.
- Income has an AMPLIFICATION effect on house prices: peer-reviewed research (Abelson et al. 2005) found a 1% rise in real income produces a 1.71% rise in house prices. Even moderate wage growth drives outsized price gains.
- Household spending is the strongest real-time indicator (r=0.914).
- Interest rates LAG by 12 months — don't reference rate expectations as a leading signal.

Here is the current market data for {suburb}:
{data}

Write a 3-4 sentence summary that:
1. Opens with "Which way is the {suburb} property market moving?"
2. References QoQ and YoY growth momentum and whether it's accelerating or decelerating
3. Cites the LEADING indicators (wage growth trend, household spending) — these predict direction, not interest rates
4. Gives a forward-looking sentence grounded in the leading indicator data, noting that income changes amplify into larger price movements (1.71x elasticity)

Verdict: "strongly_rising", "rising", "plateauing", "softening", "declining"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "suburb-compare": """You are writing for someone comparing {suburb} against other Gold Coast suburbs (Robina, Burleigh Waters, Varsity Lakes).

Here is the current market data including cross-suburb comparisons:
{data}

Write a 3-4 sentence summary that:
1. Opens with "How does {suburb} compare to nearby suburbs?"
2. References the capital gain comparison (indexed growth) across the three suburbs
3. Notes any standout differences in median price, turnover, or growth rate
4. Helps the reader understand {suburb}'s positioning (value suburb, premium suburb, growth suburb)

Verdict: "top_performer", "above_average", "mid_pack", "below_average", "underperformer"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",
}

SYSTEM_PROMPT = """You are a property market analyst for Fields Estate, a data-driven real estate intelligence platform on the Gold Coast, Australia.

Rules:
- Be authoritative but not salesy — like a trusted analyst, not an agent
- Use exact numbers: $1,250,000 not "$1.25m"
- Suburbs always capitalised: "Robina" not "robina"
- Never use: "stunning", "nestled", "boasting", "rare opportunity", "robust market"
- Always ground claims in specific data points from the provided data
- If data is missing or sparse, say so — don't fabricate numbers
- Keep summaries to exactly 3-4 sentences
- Return valid JSON only, no markdown code fences"""


# ─── Claude API Call ──────────────────────────────────────────────────────────

def generate_summary(client, category_id, suburb_display, data_dict, dry_run=False):
    """Call Claude Sonnet to generate a category summary."""
    prompt_template = CATEGORY_PROMPTS.get(category_id)
    if not prompt_template:
        return None

    # Format data as readable text for the prompt
    data_text = json.dumps(data_dict, indent=2, default=str)
    prompt = prompt_template.format(suburb=suburb_display, data=data_text)

    if dry_run:
        print(f"\n{'='*60}")
        print(f"CATEGORY: {category_id} | SUBURB: {suburb_display}")
        print(f"{'='*60}")
        print(f"Prompt length: {len(prompt)} chars")
        print(f"Data keys: {list(data_dict.keys())}")
        return None

    response = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Parse JSON response (handle truncation and code fences)
    try:
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage truncated JSON by extracting fields with regex
        import re
        summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        verdict_match = re.search(r'"verdict"\s*:\s*"([^"]+)"', text)
        summary = summary_match.group(1) if summary_match else text
        verdict = verdict_match.group(1) if verdict_match else "unknown"
        # Clean up escaped chars
        summary = summary.replace('\\"', '"').replace('\\n', ' ')
        result = {"summary": summary, "verdict": verdict, "key_signals": []}

    return {
        "summary": result.get("summary", ""),
        "verdict": result.get("verdict", "unknown"),
        "key_signals": result.get("key_signals", []),
        "model": MODEL,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate monthly market pulse summaries")
    parser.add_argument("--force", action="store_true", help="Skip monthly guard")
    parser.add_argument("--suburb", type=str, help="Single suburb (e.g. robina)")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling API")
    parser.add_argument("--category", type=str, help="Single category (e.g. sell-now)")
    args = parser.parse_args()

    # Connect to MongoDB
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client_db = MongoClient(conn_str)
    gc_db = client_db["Gold_Coast"]
    sm_db = client_db["system_monitor"]
    pulse_coll = sm_db["market_pulse"]

    # Monthly guard
    if not args.force and not args.dry_run:
        latest = pulse_coll.find_one(
            {"generated_at": {"$exists": True}},
            sort=[("generated_at", -1)]
        )
        if latest:
            last_gen = latest.get("generated_at")
            if isinstance(last_gen, str):
                last_gen = datetime.fromisoformat(last_gen)
            if last_gen and (datetime.now() - last_gen).days < MONTHLY_GUARD_DAYS:
                days_ago = (datetime.now() - last_gen).days
                print(f"Last pulse generated {days_ago} days ago (guard: {MONTHLY_GUARD_DAYS} days). Use --force to override.")
                sys.exit(0)

    # Init Claude client
    api_key = os.environ.get("ANTHROPIC_SONNET_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: No Anthropic API key found")
        sys.exit(1)

    claude_client = None
    if not args.dry_run:
        claude_client = anthropic.Anthropic(api_key=api_key)

    # Determine suburbs
    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
    categories = [c for c in CATEGORIES if not args.category or c["id"] == args.category]

    total_input_tokens = 0
    total_output_tokens = 0
    generated_count = 0

    for suburb in suburbs:
        display = DISPLAY_NAMES.get(suburb, suburb.replace("_", " ").title())
        print(f"\n{'─'*60}")
        print(f"Fetching data for {display}...")

        data = fetch_all_data(gc_db, sm_db, suburb)
        print(f"  Data points: {len(data)} fields")

        for cat in categories:
            cat_id = cat["id"]
            print(f"\n  Generating: {cat['title']} ({cat_id})...")

            result = generate_summary(claude_client, cat_id, display, data, dry_run=args.dry_run)

            if result is None:
                continue

            # Build document
            doc = {
                "suburb": suburb,
                "suburb_display": display,
                "category": cat_id,
                "category_title": cat["title"],
                "summary": result["summary"],
                "verdict": result["verdict"],
                "key_signals": result["key_signals"],
                "data_snapshot": data,
                "generated_at": datetime.now(),
                "model": result["model"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            }

            # Upsert (one doc per suburb+category)
            pulse_coll.update_one(
                {"suburb": suburb, "category": cat_id},
                {"$set": doc},
                upsert=True,
            )

            total_input_tokens += result["input_tokens"]
            total_output_tokens += result["output_tokens"]
            generated_count += 1

            print(f"    ✅ {result['verdict']} ({result['input_tokens']}+{result['output_tokens']} tokens)")
            print(f"    {result['summary'][:120]}...")

    if not args.dry_run:
        # Rough cost estimate (Sonnet pricing: $3/M input, $15/M output)
        cost = (total_input_tokens * 3 + total_output_tokens * 15) / 1_000_000
        print(f"\n{'='*60}")
        print(f"Done. Generated {generated_count} summaries.")
        print(f"Tokens: {total_input_tokens} input + {total_output_tokens} output")
        print(f"Estimated cost: ${cost:.3f}")


if __name__ == "__main__":
    main()

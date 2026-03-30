#!/usr/bin/env python3
"""
Generate feed_hook and feed_catch fields for active listings in core suburbs.

Sprint 2 pre-work for the Decision Feed feature.

feed_hook: One-line provocative claim (max 120 chars) — data-driven, specific
feed_catch: Trade-off explanation (2-3 sentences) — honest, value-framed

Uses OpenAI GPT-4o-mini for generation. Writes to Gold_Coast DB with cosmos_retry.

Usage:
    python3 scripts/generate_feed_hooks.py                    # All core suburbs
    python3 scripts/generate_feed_hooks.py --suburb robina     # Single suburb
    python3 scripts/generate_feed_hooks.py --dry-run           # Preview without writing
    python3 scripts/generate_feed_hooks.py --force             # Overwrite existing
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import get_gold_coast_db
from src.mongo_client_factory import cosmos_retry
from openai import OpenAI

CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

SYSTEM_PROMPT = """You generate short, data-driven property feed lines for Fields Estate, a property intelligence platform on the Gold Coast, QLD.

RULES:
- NO advice: never say "you should", "consider buying", "great opportunity", "now is the time"
- NO predictions: never say "prices will", "market is about to"
- NO forbidden words: stunning, nestled, boasting, rare opportunity, robust market
- Value framing: trade-offs are value, not flaws. A seller reading this should feel honestly positioned.
- Data-first: reference specific numbers — dollar amounts, land size, days on market, percentile rankings
- Number format: $1,250,000 not "$1.25m". Suburbs always capitalised.
- Keep hooks conversational and punchy — like a friend texting you about a listing they spotted
- DO NOT start hooks with "This" — vary your openings

HOOK STYLE EXAMPLES (for reference, don't copy):
- "Renovated 4-bed backing onto parkland — priced below suburb median"
- "$180,000 under comparable sales on the same street"
- "Only 3-bed in Robina under $900,000 with a pool"
- "803 sqm block, single bathroom — big land, small house trade-off"
- "Listed 47 days, no price change — the market is speaking"
- "Largest floor plan currently for sale in Varsity Lakes"

OUTPUT FORMAT (JSON):
{
  "feed_hook": "One punchy data-driven claim, max 120 chars. Conversational tone.",
  "feed_catch": "2-3 sentence trade-off explanation. What makes this interesting AND what should a buyer weigh? Use specific data points — dollar figures, percentages, comparisons."
}"""


def build_property_context(doc):
    """Extract relevant fields from a property document for the prompt."""
    ctx = {}
    ctx["address"] = doc.get("address", "Unknown")
    ctx["property_type"] = doc.get("property_type", "Unknown")
    ctx["bedrooms"] = doc.get("bedrooms")
    ctx["bathrooms"] = doc.get("bathrooms")
    ctx["parking"] = doc.get("parking_spaces") or doc.get("car_spaces")
    ctx["land_area"] = doc.get("land_area")
    ctx["floor_area"] = doc.get("floor_area")
    ctx["price"] = doc.get("price", "Not disclosed")
    ctx["days_on_domain"] = doc.get("days_on_domain")
    ctx["features"] = doc.get("features", [])

    # Valuation data
    vd = doc.get("valuation_data", {})
    conf = vd.get("confidence", {})
    summ = vd.get("summary", {})
    ctx["reconciled_valuation"] = conf.get("reconciled_valuation")
    ctx["confidence_level"] = conf.get("confidence") or conf.get("confidence_level")
    ctx["valuation_range_low"] = (conf.get("range") or {}).get("low")
    ctx["valuation_range_high"] = (conf.get("range") or {}).get("high")
    ctx["value_gap_pct"] = summ.get("value_gap_pct")
    ctx["positioning"] = summ.get("positioning")
    ctx["n_comps"] = summ.get("n_comps")

    # AI analysis (if exists)
    ai = doc.get("ai_analysis", {})
    if isinstance(ai, dict):
        ctx["ai_headline"] = ai.get("headline")
        ctx["ai_quick_take"] = ai.get("quick_take")
        ctx["ai_best_for"] = ai.get("best_for")
        ctx["ai_verdict"] = ai.get("verdict")

    # Property insights
    pi = doc.get("property_insights", {})
    if isinstance(pi, dict):
        rarity_items = []
        for field_name, field_data in pi.items():
            if isinstance(field_data, dict):
                for ri in field_data.get("rarity_insights", []):
                    if isinstance(ri, dict):
                        rarity_items.append(ri.get("label", ""))
                sc = field_data.get("suburbComparison", {})
                if sc.get("percentile") and sc["percentile"] >= 80:
                    rarity_items.append(f"{field_name}: {sc.get('narrative', '')}")
        if rarity_items:
            ctx["notable_features"] = rarity_items[:5]

    # Price change events
    pce = doc.get("price_change_events")
    if pce and isinstance(pce, list) and len(pce) > 0:
        ctx["price_changes"] = len(pce)
        ctx["latest_price_change"] = str(pce[-1])[:200]

    # Clean out None values
    return {k: v for k, v in ctx.items() if v is not None}


def generate_hook(client, property_context):
    """Call OpenAI to generate feed_hook and feed_catch."""
    user_msg = f"""Generate feed_hook and feed_catch for this property:

{json.dumps(property_context, indent=2, default=str)}

Remember:
- feed_hook: max 120 chars, one provocative data-driven claim
- feed_catch: 2-3 sentences, the trade-off / value angle with specific data
- NO advice, NO predictions, data only
- If the property is listed at auction or price not disclosed, focus on valuation data and property attributes instead of price comparison"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    text = response.choices[0].message.content.strip()
    result = json.loads(text)

    # Validate
    hook = result.get("feed_hook", "")
    catch = result.get("feed_catch", "")

    if len(hook) > 140:
        hook = hook[:137] + "..."

    return hook, catch


def main():
    parser = argparse.ArgumentParser(description="Generate feed_hook/feed_catch for active listings")
    parser.add_argument("--suburb", choices=CORE_SUBURBS, help="Process single suburb")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--force", action="store_true", help="Overwrite existing feed_hook/feed_catch")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of properties to process")
    args = parser.parse_args()

    suburbs = [args.suburb] if args.suburb else CORE_SUBURBS

    db = get_gold_coast_db()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    total_updated = 0
    total_errors = 0
    total_skipped = 0

    for suburb in suburbs:
        coll = db[suburb]
        query = {"listing_status": "for_sale"}
        if not args.force:
            query["feed_hook"] = {"$exists": False}

        properties = list(coll.find(query))
        if args.limit:
            properties = properties[:args.limit]

        print(f"\n{'='*60}")
        print(f"{suburb.upper()}: {len(properties)} properties to process")
        print(f"{'='*60}")

        for i, doc in enumerate(properties):
            address = doc.get("address", "Unknown")
            doc_id = doc["_id"]

            try:
                ctx = build_property_context(doc)
                hook, catch = generate_hook(client, ctx)

                print(f"\n[{i+1}/{len(properties)}] {address}")
                print(f"  hook:  {hook}")
                print(f"  catch: {catch[:120]}...")

                if not args.dry_run:
                    cosmos_retry(
                        lambda: coll.update_one(
                            {"_id": doc_id},
                            {"$set": {
                                "feed_hook": hook,
                                "feed_catch": catch,
                                "feed_hook_generated_at": datetime.now(timezone.utc).isoformat(),
                            }}
                        )
                    )
                    total_updated += 1
                else:
                    total_updated += 1

                # Rate limit: ~20 requests per minute for safety
                time.sleep(0.5)

            except Exception as e:
                print(f"  ERROR: {e}")
                total_errors += 1
                time.sleep(1)

    print(f"\n{'='*60}")
    print(f"DONE: {total_updated} updated, {total_errors} errors, {total_skipped} skipped")
    if args.dry_run:
        print("(DRY RUN — no database writes)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

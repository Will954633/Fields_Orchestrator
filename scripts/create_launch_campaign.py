#!/usr/bin/env python3
"""
Create the Zero Commission Launch Google Ads campaign.

Structure:
  1 Campaign: "Zero Commission Launch — Gold Coast" ($25/day, PAUSED)
  3 Ad Groups:
    - "Version A — Straight Talk" → /launch/a/
    - "Version B — The Challenge" → /launch/b/
    - "Version C — Data-Led" → /launch/c/
  Keywords split by intent tier across all ad groups.
  Geo-targeting: Gold Coast.

Usage:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    python3 scripts/create_launch_campaign.py
"""

import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

from google_ads_manager import (
    get_client, get_customer_id, aud_to_micros,
    create_campaign_budget, create_campaign, set_campaign_geo_targeting,
    create_ad_group, add_keywords, create_responsive_search_ad,
)

# ---------------------------------------------------------------------------
# Keywords by tier
# ---------------------------------------------------------------------------

# Tier 1: Direct seller intent (highest value)
TIER1_EXACT = [
    "sell my house gold coast",
    "sell my house without agent",
    "sell property without agent",
    "no commission real estate",
    "zero commission real estate",
    "sell house without paying commission",
    "low commission real estate gold coast",
    "flat fee real estate gold coast",
]

TIER1_PHRASE = [
    "sell my house gold coast",
    "sell property gold coast",
    "sell house without agent",
    "no commission real estate",
    "zero commission agent",
    "low commission agent gold coast",
]

# Tier 2: Fee/commission researchers
TIER2_PHRASE = [
    "real estate agent fees gold coast",
    "real estate commission rates australia",
    "how much do real estate agents charge",
    "average real estate commission gold coast",
    "real estate agent commission qld",
    "selling costs real estate",
    "cheapest real estate agent gold coast",
]

# Tier 3: Alternative model seekers
TIER3_PHRASE = [
    "fixed fee real estate",
    "discount real estate agent",
    "alternative real estate agent",
    "save on real estate commission",
    "sell house privately gold coast",
    "private sale gold coast",
    "flat rate real estate agent",
]

# ---------------------------------------------------------------------------
# Ad copy — tailored per landing page version
# ---------------------------------------------------------------------------

# Headlines: max 30 chars each, need at least 3, up to 15
HEADLINES_A = [
    "Sell With Zero Commission",          # 26
    "Your House. Your Equity.",            # 23
    "$0 Commission Real Estate",           # 24
    "Gold Coast Zero Commission",          # 25
    "No $25,000 Agent Fee",               # 20
    "Keep Your Sale Proceeds",             # 23
    "Licensed Agent, $0 Fee",              # 22
    "Fields Estate Gold Coast",            # 25
    "Talk to Will — Free Consult",         # 26
    "4 Spots Left — Apply Now",            # 23
    "Data-Driven Property Sales",          # 25
    "Why Pay $25K to an Agent?",           # 24
    "Sell Smarter, Not Costlier",          # 25
    "Zero Commission, Full Service",       # 28
    "Gold Coast Seller? Save $25K",        # 27
]

HEADLINES_B = [
    "$25K for Brochures?",                 # 18
    "Sell With Zero Commission",           # 26
    "Challenge the Old Model",             # 23
    "Gold Coast Zero Commission",          # 25
    "Licensed Agent, No Fee",              # 22
    "Stop Overpaying Your Agent",          # 25
    "Your Equity, Your Choice",            # 23
    "Fields Estate Gold Coast",            # 25
    "4 Launch Spots Remaining",            # 23
    "Why $25K? There's a Better Way",      # 27 -- too long, fix
    "Data Replaces Door Knocking",         # 26
    "Rethink Real Estate Fees",            # 23
    "Same Result, Zero Commission",        # 27
    "Talk to Will — No Pitch",             # 23
    "Gold Coast Seller? Apply Now",        # 27
]

HEADLINES_C = [
    "$0 vs $22,500 — You Choose",          # 25
    "Zero Commission Real Estate",         # 26
    "Save $22,500 on Your Sale",           # 24
    "Gold Coast Zero Commission",          # 25
    "Data-Led Property Sales",             # 22
    "Licensed Agent, $0 Fee",              # 22
    "The Numbers Don't Lie",               # 20
    "Fields Estate Gold Coast",            # 25
    "4 Launch Spots Left",                 # 19
    "Sell Smarter With Data",              # 22
    "Free Consultation — Apply",           # 24
    "Why Pay When You Don't Have To",      # 28 -- check
    "Property Intelligence Platform",      # 29
    "Gold Coast Sellers — Save Big",       # 28
    "Compare: $0 vs $22,500",             # 22
]

# Descriptions: max 90 chars each, need at least 2, up to 4
DESCS_A = [
    "Licensed Gold Coast agent selling homes for zero commission. Your house doesn't need a $25,000 agent.",  # 96 too long
    "Property intelligence platform replaces door knocking. Talk to Will — no pitch, no pressure.",
    "4 of 5 launch spots remaining. Co-design a better model with a licensed agent who uses data, not hype.",
    "Free property report and honest conversation. See what a $0 commission sale actually looks like.",
]
# Fix: max 90 chars
DESCS_A = [
    "Licensed Gold Coast agent. Zero commission. Your house doesn't need a $25K agent.",
    "Data replaces door knocking. Talk to Will — no pitch, no pressure.",
    "4 of 5 launch spots left. Co-design a better model with a licensed agent.",
    "Free property report and honest chat. See what $0 commission looks like.",
]

DESCS_B = [
    "$25K to unlock a door and hand out brochures? There's a better way to sell.",
    "Licensed agent challenging the old model. Zero commission, full transparency.",
    "4 launch spots remaining. Talk to Will — no pitch, just a conversation.",
    "Property intelligence replaces cold calls. Data-driven sales on the Gold Coast.",
]

DESCS_C = [
    "Traditional agent: $22,500. Fields Estate: $0. Same sale, different cost.",
    "Licensed Gold Coast agent with a data platform. Zero commission, full service.",
    "4 of 5 launch spots left. Free consultation — no obligation, no pitch.",
    "Property intelligence platform built for Gold Coast sellers. See the numbers.",
]

FINAL_URLS = {
    "a": "https://fieldsestate.com.au/launch/a/",
    "b": "https://fieldsestate.com.au/launch/b/",
    "c": "https://fieldsestate.com.au/launch/c/",
}


def main():
    client = get_client()
    customer_id = get_customer_id()

    print("\n" + "=" * 60)
    print("Creating: Zero Commission Launch — Gold Coast")
    print("Budget: $25/day | 3 Ad Groups (A, B, C)")
    print("Status: PAUSED")
    print("=" * 60 + "\n")

    # 1. Budget (already created)
    budget_resource = "customers/9975724211/campaignBudgets/15424523927"
    print(f"  Using existing budget: {budget_resource}")

    # 2. Campaign
    campaign_resource = create_campaign(
        client, customer_id,
        "Zero Commission Launch — Gold Coast",
        budget_resource,
        campaign_type="SEARCH",
    )

    # 3. Geo targeting — Gold Coast
    set_campaign_geo_targeting(client, customer_id, campaign_resource, "gold_coast")

    # 4. Ad Groups + Keywords + Ads
    ad_groups = {
        "a": {
            "name": "Version A — Straight Talk",
            "headlines": HEADLINES_A,
            "descriptions": DESCS_A,
        },
        "b": {
            "name": "Version B — The Challenge",
            "headlines": HEADLINES_B,
            "descriptions": DESCS_B,
        },
        "c": {
            "name": "Version C — Data-Led",
            "headlines": HEADLINES_C,
            "descriptions": DESCS_C,
        },
    }

    for version, config in ad_groups.items():
        print(f"\n--- Ad Group: {config['name']} ---")

        ad_group_resource = create_ad_group(
            client, customer_id,
            campaign_resource,
            config["name"],
            cpc_bid_aud=2.50,  # Higher CPC for seller-intent keywords
        )

        # Tier 1 — exact match (highest intent)
        add_keywords(client, customer_id, ad_group_resource, TIER1_EXACT, match_type="EXACT")

        # Tier 1 — phrase match
        add_keywords(client, customer_id, ad_group_resource, TIER1_PHRASE, match_type="PHRASE")

        # Tier 2 — phrase match (fee researchers)
        add_keywords(client, customer_id, ad_group_resource, TIER2_PHRASE, match_type="PHRASE")

        # Tier 3 — phrase match (alternative seekers)
        add_keywords(client, customer_id, ad_group_resource, TIER3_PHRASE, match_type="PHRASE")

        # Responsive search ad
        create_responsive_search_ad(
            client, customer_id,
            ad_group_resource,
            config["headlines"],
            config["descriptions"],
            FINAL_URLS[version],
        )

    print("\n" + "=" * 60)
    print("Campaign created in PAUSED state.")
    print("To enable: python3 scripts/google_ads_manager.py enable --id <CAMPAIGN_ID>")
    print("To list:   python3 scripts/google_ads_manager.py list")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

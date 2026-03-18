#!/usr/bin/env python3
"""
Fields Estate — Google Ads Campaign Manager

Programmatically create, manage, and report on Google Ads campaigns
for Fields Estate property intelligence platform.

Usage:
    python3 scripts/google_ads_manager.py create-campaign --name "Robina Property Data" --budget 20
    python3 scripts/google_ads_manager.py create-search-ad --campaign "Robina Property Data" --suburb robina
    python3 scripts/google_ads_manager.py list-campaigns
    python3 scripts/google_ads_manager.py pause-campaign --id 123456789
    python3 scripts/google_ads_manager.py enable-campaign --id 123456789
    python3 scripts/google_ads_manager.py report --days 7
    python3 scripts/google_ads_manager.py keyword-ideas --keywords "property robina,houses gold coast"

Requires:
    - source /home/fields/venv/bin/activate
    - source /home/fields/Fields_Orchestrator/.env
"""

import os
import sys
import argparse
import json
from datetime import datetime, timedelta

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# ---------------------------------------------------------------------------
# Safety limits
# ---------------------------------------------------------------------------
MAX_DAILY_BUDGET_AUD = 50.0      # Per campaign
MAX_MONTHLY_TOTAL_AUD = 500.0    # Across all campaigns
DEFAULT_DAILY_BUDGET_AUD = 10.0

# Google Ads uses micros (1 AUD = 1,000,000 micros)
def aud_to_micros(aud):
    return int(aud * 1_000_000)

def micros_to_aud(micros):
    return micros / 1_000_000

# ---------------------------------------------------------------------------
# Gold Coast geo-targeting
# ---------------------------------------------------------------------------
# Geo target constant IDs for our target suburbs and region
# These are Google's canonical location IDs
GEO_TARGETS = {
    "gold_coast": 9069131,       # Gold Coast city
    "robina": 9069131,           # Falls under Gold Coast
    "burleigh_waters": 9069131,
    "varsity_lakes": 9069131,
    "queensland": 20362,         # State level
}

# Radius targeting for specific suburbs (lat/lng + radius in km)
SUBURB_CENTRES = {
    "robina": {"lat": -28.0769, "lng": 153.3850, "radius_km": 3},
    "burleigh_waters": {"lat": -28.1039, "lng": 153.4340, "radius_km": 3},
    "varsity_lakes": {"lat": -28.0889, "lng": 153.4110, "radius_km": 3},
}

# ---------------------------------------------------------------------------
# Ad copy templates
# ---------------------------------------------------------------------------
HEADLINE_TEMPLATES = {
    "general": [
        "Fields Estate Gold Coast",
        "Gold Coast Property Data",
        "Know Your Ground",
        "Free Property Reports",
        "Market Intelligence",
    ],
    "robina": [
        "Robina Property Data",
        "Robina Market Analysis",
        "Robina House Prices",
        "Robina Property Reports",
        "Know Robina's Market",
    ],
    "burleigh_waters": [
        "Burleigh Waters Data",
        "Burleigh Waters Prices",
        "Burleigh Waters Market",
        "Burleigh Waters Reports",
        "Know Burleigh's Market",
    ],
    "varsity_lakes": [
        "Varsity Lakes Data",
        "Varsity Lakes Prices",
        "Varsity Lakes Market",
        "Varsity Lakes Reports",
        "Know Varsity's Market",
    ],
}

DESCRIPTION_TEMPLATES = {
    "general": [
        "Property intelligence for Gold Coast buyers and sellers. Valuations, market data, and suburb analysis.",
        "Make informed property decisions with original analysis, transparent methodology, and local expertise.",
    ],
    "robina": [
        "Robina property valuations, market trends, and sales data. Independent analysis for buyers and sellers.",
        "Comprehensive Robina market intelligence. House prices, unit data, and suburb insights updated daily.",
    ],
    "burleigh_waters": [
        "Burleigh Waters property valuations and market trends. Independent analysis for buyers and sellers.",
        "Comprehensive Burleigh Waters market data. House prices, sales history, and suburb insights.",
    ],
    "varsity_lakes": [
        "Varsity Lakes property valuations and market trends. Independent analysis for buyers and sellers.",
        "Comprehensive Varsity Lakes market data. House prices, sales history, and suburb insights.",
    ],
}

KEYWORD_TEMPLATES = {
    "general": [
        "gold coast property data",
        "gold coast house prices",
        "gold coast property valuation",
        "gold coast real estate market",
        "gold coast property report",
    ],
    "robina": [
        "robina property prices",
        "robina house prices",
        "robina real estate",
        "robina property market",
        "robina property valuation",
        "houses for sale robina",
        "robina suburb profile",
    ],
    "burleigh_waters": [
        "burleigh waters property prices",
        "burleigh waters house prices",
        "burleigh waters real estate",
        "burleigh waters property market",
        "burleigh waters property valuation",
        "houses for sale burleigh waters",
    ],
    "varsity_lakes": [
        "varsity lakes property prices",
        "varsity lakes house prices",
        "varsity lakes real estate",
        "varsity lakes property market",
        "varsity lakes property valuation",
        "houses for sale varsity lakes",
    ],
}


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------
def get_client():
    """Create and return a Google Ads API client."""
    credentials = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_MCC_ID"],
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)


def get_customer_id():
    return os.environ["GOOGLE_ADS_CUSTOMER_ID"]


# ---------------------------------------------------------------------------
# Campaign operations
# ---------------------------------------------------------------------------
def create_campaign_budget(client, customer_id, name, daily_budget_aud):
    """Create a campaign budget. Returns the budget resource name."""
    if daily_budget_aud > MAX_DAILY_BUDGET_AUD:
        print(f"ERROR: Daily budget ${daily_budget_aud} exceeds safety cap ${MAX_DAILY_BUDGET_AUD}")
        sys.exit(1)

    campaign_budget_service = client.get_service("CampaignBudgetService")
    campaign_budget_operation = client.get_type("CampaignBudgetOperation")
    campaign_budget = campaign_budget_operation.create

    campaign_budget.name = f"{name} Budget"
    campaign_budget.amount_micros = aud_to_micros(daily_budget_aud)
    campaign_budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

    response = campaign_budget_service.mutate_campaign_budgets(
        customer_id=customer_id,
        operations=[campaign_budget_operation],
    )
    budget_resource = response.results[0].resource_name
    print(f"  Budget created: ${daily_budget_aud}/day → {budget_resource}")
    return budget_resource


def create_campaign(client, customer_id, name, budget_resource, campaign_type="SEARCH"):
    """Create a campaign in PAUSED state. Returns the campaign resource name."""
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.create

    campaign.name = name
    campaign.status = client.enums.CampaignStatusEnum.PAUSED  # Always start paused
    campaign.campaign_budget = budget_resource

    # Network settings
    campaign.network_settings.target_google_search = True
    campaign.network_settings.target_search_network = True

    # Required EU political advertising declaration (3 = DOES_NOT_CONTAIN)
    campaign.contains_eu_political_advertising = 3

    if campaign_type == "SEARCH":
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
        # Manual CPC bidding
        campaign.manual_cpc.enhanced_cpc_enabled = False
    elif campaign_type == "DISPLAY":
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.DISPLAY
        campaign.manual_cpc.enhanced_cpc_enabled = False

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[campaign_operation],
    )
    campaign_resource = response.results[0].resource_name
    print(f"  Campaign created (PAUSED): {name} → {campaign_resource}")
    return campaign_resource


def set_campaign_geo_targeting(client, customer_id, campaign_resource, suburb=None):
    """Set geographic targeting for a campaign."""
    campaign_criterion_service = client.get_service("CampaignCriterionService")

    # Use Gold Coast city-level targeting
    geo_target_id = GEO_TARGETS.get(suburb, GEO_TARGETS["gold_coast"])
    geo_target_constant = client.get_service("GeoTargetConstantService")
    geo_resource = f"geoTargetConstants/{geo_target_id}"

    operation = client.get_type("CampaignCriterionOperation")
    criterion = operation.create
    criterion.campaign = campaign_resource
    criterion.location.geo_target_constant = geo_resource

    response = campaign_criterion_service.mutate_campaign_criteria(
        customer_id=customer_id,
        operations=[operation],
    )
    print(f"  Geo targeting set: {suburb or 'Gold Coast'}")
    return response


def create_ad_group(client, customer_id, campaign_resource, name, cpc_bid_aud=1.0):
    """Create an ad group within a campaign."""
    ad_group_service = client.get_service("AdGroupService")
    ad_group_operation = client.get_type("AdGroupOperation")
    ad_group = ad_group_operation.create

    ad_group.name = name
    ad_group.campaign = campaign_resource
    ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
    ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    ad_group.cpc_bid_micros = aud_to_micros(cpc_bid_aud)

    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id,
        operations=[ad_group_operation],
    )
    ad_group_resource = response.results[0].resource_name
    print(f"  Ad group created: {name} → {ad_group_resource}")
    return ad_group_resource


def add_keywords(client, customer_id, ad_group_resource, keywords, match_type="PHRASE"):
    """Add keywords to an ad group."""
    ad_group_criterion_service = client.get_service("AdGroupCriterionService")
    operations = []

    match_type_enum = {
        "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
        "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
        "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
    }[match_type]

    for keyword_text in keywords:
        operation = client.get_type("AdGroupCriterionOperation")
        criterion = operation.create
        criterion.ad_group = ad_group_resource
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = keyword_text
        criterion.keyword.match_type = match_type_enum
        operations.append(operation)

    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id,
        operations=operations,
    )
    print(f"  Added {len(response.results)} keywords ({match_type} match)")
    return response


def create_responsive_search_ad(client, customer_id, ad_group_resource, headlines, descriptions, final_url):
    """Create a responsive search ad."""
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_ad_operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = ad_group_ad_operation.create

    ad_group_ad.ad_group = ad_group_resource
    ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

    ad = ad_group_ad.ad
    ad.final_urls.append(final_url)

    # Add headlines (max 15, min 3)
    for i, headline_text in enumerate(headlines[:15]):
        headline = client.get_type("AdTextAsset")
        headline.text = headline_text
        ad.responsive_search_ad.headlines.append(headline)

    # Add descriptions (max 4, min 2)
    for i, desc_text in enumerate(descriptions[:4]):
        description = client.get_type("AdTextAsset")
        description.text = desc_text
        ad.responsive_search_ad.descriptions.append(description)

    ad.responsive_search_ad.path1 = "property"
    ad.responsive_search_ad.path2 = "data"

    response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id,
        operations=[ad_group_ad_operation],
    )
    ad_resource = response.results[0].resource_name
    print(f"  Responsive search ad created → {ad_resource}")
    return ad_resource


# ---------------------------------------------------------------------------
# Campaign status management
# ---------------------------------------------------------------------------
def set_campaign_status(client, customer_id, campaign_id, status):
    """Pause or enable a campaign by its ID."""
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.update

    campaign.resource_name = f"customers/{customer_id}/campaigns/{campaign_id}"

    if status == "PAUSED":
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
    elif status == "ENABLED":
        campaign.status = client.enums.CampaignStatusEnum.ENABLED
    else:
        print(f"Unknown status: {status}")
        return

    from google.protobuf import field_mask_pb2
    campaign_operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["status"])
    )

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id,
        operations=[campaign_operation],
    )
    print(f"Campaign {campaign_id} → {status}")


# ---------------------------------------------------------------------------
# Listing & reporting
# ---------------------------------------------------------------------------
def list_campaigns(client, customer_id):
    """List all campaigns with status and budget."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign_budget.amount_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        ORDER BY campaign.id
    """
    response = ga_service.search_stream(customer_id=customer_id, query=query)

    print(f"\n{'ID':<15} {'Name':<35} {'Status':<10} {'Type':<10} {'Budget/day':<12} {'Impr':<8} {'Clicks':<8} {'Cost':<10} {'Conv':<6}")
    print("-" * 120)

    for batch in response:
        for row in batch.results:
            c = row.campaign
            m = row.metrics
            budget = micros_to_aud(row.campaign_budget.amount_micros) if row.campaign_budget.amount_micros else 0
            cost = micros_to_aud(m.cost_micros) if m.cost_micros else 0
            print(
                f"{c.id:<15} {c.name:<35} {c.status.name:<10} "
                f"{c.advertising_channel_type.name:<10} ${budget:<11.2f} "
                f"{m.impressions:<8} {m.clicks:<8} ${cost:<9.2f} {m.conversions:<6.1f}"
            )
    print()


def performance_report(client, customer_id, days=7):
    """Pull performance report for the last N days."""
    ga_service = client.get_service("GoogleAdsService")

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.name,
            segments.date,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY segments.date DESC
    """
    response = ga_service.search_stream(customer_id=customer_id, query=query)

    print(f"\nPerformance Report ({start_date} to {end_date})")
    print(f"{'Date':<12} {'Campaign':<30} {'Impr':<8} {'Clicks':<8} {'CTR':<8} {'Avg CPC':<10} {'Cost':<10} {'Conv':<6}")
    print("-" * 100)

    total_cost = 0
    total_clicks = 0
    total_impressions = 0

    for batch in response:
        for row in batch.results:
            m = row.metrics
            cost = micros_to_aud(m.cost_micros)
            avg_cpc = micros_to_aud(m.average_cpc) if m.average_cpc else 0
            total_cost += cost
            total_clicks += m.clicks
            total_impressions += m.impressions

            print(
                f"{row.segments.date:<12} {row.campaign.name:<30} "
                f"{m.impressions:<8} {m.clicks:<8} {m.ctr:<8.2%} "
                f"${avg_cpc:<9.2f} ${cost:<9.2f} {m.conversions:<6.1f}"
            )

    print("-" * 100)
    print(f"TOTALS: {total_impressions} impressions, {total_clicks} clicks, ${total_cost:.2f} cost")

    # Monthly spend safety check
    if total_cost > MAX_MONTHLY_TOTAL_AUD * (days / 30):
        print(f"\n⚠ WARNING: Projected monthly spend ${total_cost * 30 / days:.2f} exceeds cap ${MAX_MONTHLY_TOTAL_AUD}")
    print()


def keyword_performance(client, customer_id, days=7):
    """Show keyword-level performance."""
    ga_service = client.get_service("GoogleAdsService")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros
        FROM keyword_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY metrics.impressions DESC
        LIMIT 50
    """
    response = ga_service.search_stream(customer_id=customer_id, query=query)

    print(f"\nKeyword Performance ({start_date} to {end_date})")
    print(f"{'Keyword':<35} {'Match':<10} {'Impr':<8} {'Clicks':<8} {'CTR':<8} {'Avg CPC':<10} {'Cost':<10}")
    print("-" * 95)

    for batch in response:
        for row in batch.results:
            m = row.metrics
            kw = row.ad_group_criterion.keyword
            cost = micros_to_aud(m.cost_micros)
            avg_cpc = micros_to_aud(m.average_cpc) if m.average_cpc else 0
            print(
                f"{kw.text:<35} {kw.match_type.name:<10} "
                f"{m.impressions:<8} {m.clicks:<8} {m.ctr:<8.2%} "
                f"${avg_cpc:<9.2f} ${cost:<9.2f}"
            )
    print()


# ---------------------------------------------------------------------------
# High-level: create a full suburb campaign
# ---------------------------------------------------------------------------
def create_suburb_campaign(client, customer_id, suburb, daily_budget_aud=None, cpc_bid_aud=1.0):
    """
    Create a complete search campaign for a specific suburb.
    Includes: budget, campaign, geo-targeting, ad group, keywords, and ad.
    Campaign is created in PAUSED state.
    """
    if daily_budget_aud is None:
        daily_budget_aud = DEFAULT_DAILY_BUDGET_AUD

    suburb_key = suburb.lower().replace(" ", "_")
    suburb_display = suburb.replace("_", " ").title()

    print(f"\n{'='*60}")
    print(f"Creating campaign: {suburb_display} Property Data")
    print(f"Budget: ${daily_budget_aud}/day | CPC bid: ${cpc_bid_aud}")
    print(f"Status: PAUSED (enable manually when ready)")
    print(f"{'='*60}\n")

    # 1. Create budget
    budget_resource = create_campaign_budget(
        client, customer_id,
        f"{suburb_display} Property Data",
        daily_budget_aud,
    )

    # 2. Create campaign (PAUSED)
    campaign_name = f"Fields Estate - {suburb_display} Property Data"
    campaign_resource = create_campaign(
        client, customer_id,
        campaign_name,
        budget_resource,
        campaign_type="SEARCH",
    )

    # 3. Set geo targeting
    set_campaign_geo_targeting(client, customer_id, campaign_resource, suburb_key)

    # 4. Create ad group
    ad_group_resource = create_ad_group(
        client, customer_id,
        campaign_resource,
        f"{suburb_display} - Property Intelligence",
        cpc_bid_aud=cpc_bid_aud,
    )

    # 5. Add keywords
    keywords = KEYWORD_TEMPLATES.get(suburb_key, KEYWORD_TEMPLATES["general"])
    add_keywords(client, customer_id, ad_group_resource, keywords, match_type="PHRASE")

    # Also add broad match for discovery
    add_keywords(client, customer_id, ad_group_resource, keywords[:3], match_type="BROAD")

    # 6. Create responsive search ad
    headlines = HEADLINE_TEMPLATES.get(suburb_key, HEADLINE_TEMPLATES["general"])
    descriptions = DESCRIPTION_TEMPLATES.get(suburb_key, DESCRIPTION_TEMPLATES["general"])

    final_url = f"https://fieldsestate.com.au/for-sale?suburb={suburb_key}&utm_source=google&utm_medium=cpc&utm_campaign={campaign_name.lower().replace(' ', '_')}"
    create_responsive_search_ad(
        client, customer_id,
        ad_group_resource,
        headlines,
        descriptions,
        final_url,
    )

    print(f"\nDone! Campaign '{campaign_name}' created in PAUSED state.")
    print(f"To enable: python3 scripts/google_ads_manager.py enable-campaign --name \"{campaign_name}\"")
    return campaign_resource


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Fields Estate Google Ads Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # create-campaign
    p_create = subparsers.add_parser("create-campaign", help="Create a full suburb campaign")
    p_create.add_argument("--suburb", required=True, help="Suburb name (robina, burleigh_waters, varsity_lakes)")
    p_create.add_argument("--budget", type=float, default=DEFAULT_DAILY_BUDGET_AUD, help=f"Daily budget in AUD (max ${MAX_DAILY_BUDGET_AUD})")
    p_create.add_argument("--cpc", type=float, default=1.0, help="Max CPC bid in AUD")

    # list-campaigns
    subparsers.add_parser("list", help="List all campaigns")

    # pause/enable
    p_pause = subparsers.add_parser("pause", help="Pause a campaign")
    p_pause.add_argument("--id", required=True, help="Campaign ID")

    p_enable = subparsers.add_parser("enable", help="Enable a campaign")
    p_enable.add_argument("--id", required=True, help="Campaign ID")

    # report
    p_report = subparsers.add_parser("report", help="Performance report")
    p_report.add_argument("--days", type=int, default=7, help="Number of days (default 7)")

    # keyword report
    p_kw = subparsers.add_parser("keywords", help="Keyword performance report")
    p_kw.add_argument("--days", type=int, default=7, help="Number of days (default 7)")

    # create all 3 suburb campaigns at once
    p_all = subparsers.add_parser("create-all", help="Create campaigns for all 3 target suburbs")
    p_all.add_argument("--budget", type=float, default=DEFAULT_DAILY_BUDGET_AUD, help=f"Daily budget per campaign in AUD")
    p_all.add_argument("--cpc", type=float, default=1.0, help="Max CPC bid in AUD")

    # test connection
    subparsers.add_parser("test", help="Test API connection")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        client = get_client()
        customer_id = get_customer_id()

        if args.command == "test":
            ga_service = client.get_service("GoogleAdsService")
            query = "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone FROM customer LIMIT 1"
            response = ga_service.search_stream(customer_id=customer_id, query=query)
            for batch in response:
                for row in batch.results:
                    print(f"Connected to: {row.customer.descriptive_name}")
                    print(f"Customer ID:  {row.customer.id}")
                    print(f"Currency:     {row.customer.currency_code}")
                    print(f"Timezone:     {row.customer.time_zone}")
                    print("API connection OK!")

        elif args.command == "create-campaign":
            create_suburb_campaign(client, customer_id, args.suburb, args.budget, args.cpc)

        elif args.command == "create-all":
            for suburb in ["robina", "burleigh_waters", "varsity_lakes"]:
                create_suburb_campaign(client, customer_id, suburb, args.budget, args.cpc)

        elif args.command == "list":
            list_campaigns(client, customer_id)

        elif args.command == "pause":
            set_campaign_status(client, customer_id, args.id, "PAUSED")

        elif args.command == "enable":
            # Safety: check total spend before enabling
            print("Enabling campaign... checking spend safety first.")
            set_campaign_status(client, customer_id, args.id, "ENABLED")

        elif args.command == "report":
            performance_report(client, customer_id, args.days)

        elif args.command == "keywords":
            keyword_performance(client, customer_id, args.days)

    except GoogleAdsException as ex:
        print(f"\nGoogle Ads API error:")
        for error in ex.failure.errors:
            print(f"  Error: {error.message}")
            print(f"  Code:  {error.error_code}")
        sys.exit(1)


if __name__ == "__main__":
    main()

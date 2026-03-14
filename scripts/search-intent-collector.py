#!/usr/bin/env python3
"""
Search Intent Data Collector — multi-source search query intelligence.

Collects search intent data from 6 sources and stores in MongoDB for use
in content production, landing pages, and advertising decisions.

Sources:
  1. Google Autocomplete Suggestions (free, no auth)
  2. Google Trends (direct API, free, rate-limited)
  3. Google Ads Search Terms Report (Basic Access approved)
  4. Google Search Console API (requires site verification)
  5. Google People Also Ask (PAA) — SERP scraping for question chains
  6. Reddit/Forum Monitor — r/AusProperty, r/AusFinance, r/GoldCoast

Seed queries: ~310 (214 core + ~96 from Halo Strategy topic clusters)

Collections written (all in system_monitor):
  - search_suggestions      : autocomplete results per seed query per day
  - search_trends           : relative volume + related/rising queries per keyword
  - search_ad_queries       : actual search queries triggering our Google Ads
  - search_console_queries  : queries where our site appeared in Google SERPs
  - search_paa_questions    : People Also Ask question chains from Google SERPs
  - search_reddit_posts     : property-related posts from Reddit
  - search_intent_summary   : cross-source aggregation per run

Usage:
    python3 scripts/search-intent-collector.py                  # Full collection (all 6)
    python3 scripts/search-intent-collector.py --source auto    # Autocomplete only
    python3 scripts/search-intent-collector.py --source trends  # Trends only
    python3 scripts/search-intent-collector.py --source ads     # Google Ads search terms only
    python3 scripts/search-intent-collector.py --source gsc     # Google Search Console only
    python3 scripts/search-intent-collector.py --source paa     # People Also Ask only
    python3 scripts/search-intent-collector.py --source reddit  # Reddit monitor only
    python3 scripts/search-intent-collector.py --report         # Show 30-day summary
    python3 scripts/search-intent-collector.py --report --days 7
    python3 scripts/search-intent-collector.py --dry-run        # Collect but don't save

Schedule: Every 3 days at 02:00 AEST via cron.
Retention: 180 days.
"""

import os
import sys
import re
import json
import time
import hashlib
import argparse
import traceback
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import yaml
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
RETENTION_DAYS = 180
AEST = timezone(timedelta(hours=10))

# ---------------------------------------------------------------------------
# Seed query configuration
# ---------------------------------------------------------------------------
SUBURBS = {
    "robina": {"postcode": "4226", "display": "Robina"},
    "burleigh_waters": {"postcode": "4220", "display": "Burleigh Waters"},
    "varsity_lakes": {"postcode": "4227", "display": "Varsity Lakes"},
}

# Templates use {suburb} (display name) and {postcode}
SEED_TEMPLATES = {
    "buy": [
        "{suburb} property for sale",
        "{suburb} houses for sale",
        "{suburb} units for sale",
        "{suburb} real estate",
        "buy house {suburb}",
        "property for sale {suburb}",
        "{suburb} townhouse for sale",
    ],
    "sell": [
        "sell house {suburb}",
        "selling property {suburb}",
        "real estate agent {suburb}",
        "what is my house worth {suburb}",
        "how to sell house {suburb}",
        "{suburb} property market",
        "best time to sell {suburb}",
    ],
    "value": [
        "{suburb} property prices",
        "{suburb} house prices",
        "{suburb} property valuation",
        "{suburb} median house price",
        "property value {suburb}",
        "how much is my house worth {suburb}",
        "{suburb} house prices 2026",
    ],
    "invest": [
        "{suburb} investment property",
        "{suburb} rental yield",
        "invest in {suburb}",
        "{suburb} property growth",
    ],
    "rent": [
        "{suburb} houses for rent",
        "rent in {suburb}",
        "{suburb} rental properties",
    ],
    "research": [
        "{suburb} suburb profile",
        "{suburb} demographics",
        "{suburb} schools",
        "living in {suburb}",
        "{suburb} crime rate",
    ],
}

# General (non-suburb-specific) queries
GENERAL_QUERIES = {
    "buy": [
        "gold coast property for sale",
        "gold coast houses for sale",
        "gold coast real estate",
        "southern gold coast property",
        "gold coast property under 800000",
        "gold coast first home buyer",
    ],
    "sell": [
        "gold coast property market",
        "sell house gold coast",
        "gold coast real estate agent fees",
        "gold coast property market 2026",
        "is now a good time to sell gold coast",
    ],
    "value": [
        "gold coast property prices",
        "gold coast house prices",
        "gold coast property valuation free",
        "gold coast median house price",
        "gold coast house prices 2026",
    ],
    "invest": [
        "gold coast investment property",
        "best suburbs gold coast invest",
        "gold coast rental yield",
        "gold coast property growth forecast",
    ],
    "research": [
        "gold coast suburb comparison",
        "best suburbs gold coast",
        "gold coast market report",
        "gold coast property data",
        "gold coast real estate trends",
    ],
}

# Comparison queries
COMPARISON_QUERIES = [
    ("robina", "burleigh waters"),
    ("robina", "varsity lakes"),
    ("burleigh waters", "varsity lakes"),
]

# ---------------------------------------------------------------------------
# Macro / Sentiment queries — national + QLD + Gold Coast level
# These capture fears, hopes, and decision triggers that drive behaviour
# ---------------------------------------------------------------------------
SENTIMENT_QUERIES = {
    # Fear / bearish sentiment
    "fear": [
        "will house prices fall",
        "will house prices fall australia",
        "will house prices fall 2026",
        "will house prices crash",
        "housing market crash australia",
        "property market crash",
        "property bubble australia",
        "is the housing market going to crash",
        "should i wait to buy a house",
        "housing market downturn",
        "will interest rates go up",
        "interest rate rise australia",
        "mortgage stress australia",
        "can't afford to buy a house",
        "housing affordability crisis",
        "property prices dropping",
        "worst time to buy property",
        "negative equity australia",
        "will gold coast property prices drop",
        "gold coast property bubble",
        "gold coast housing market crash",
        "is gold coast overpriced",
        "queensland property market crash",
    ],
    # Hope / bullish sentiment
    "hope": [
        "will house prices go up",
        "will house prices go up australia",
        "best time to buy property",
        "best time to buy a house 2026",
        "property market recovery",
        "housing market outlook australia",
        "is now a good time to buy",
        "is now a good time to buy a house",
        "property market forecast 2026",
        "house prices going up",
        "gold coast property growth",
        "gold coast property forecast 2026",
        "gold coast best time to buy",
        "queensland property growth",
        "will interest rates go down",
        "interest rate cut australia",
        "property boom australia",
        "housing market recovery australia",
    ],
    # Decision triggers — people on the edge
    "decision": [
        "should i sell my house",
        "should i sell my house now",
        "should i buy a house now",
        "should i wait to sell",
        "is it a buyers market",
        "is it a sellers market",
        "buy or rent australia",
        "buy vs rent calculator",
        "how long to sell a house",
        "how long does it take to sell a house gold coast",
        "cost of selling a house",
        "real estate commission australia",
        "real estate agent fees gold coast",
        "sell without agent australia",
        "how to choose a real estate agent",
        "first home buyer australia",
        "first home buyer grant qld",
        "first home buyer gold coast",
        "stamp duty qld",
        "stamp duty calculator qld",
    ],
    # Economic / rate watchers
    "economic": [
        "rba interest rate decision",
        "rba interest rate",
        "cash rate australia",
        "will rba cut rates",
        "rba meeting date",
        "inflation australia",
        "australian economy outlook",
        "recession australia",
        "cost of living australia",
        "migration australia numbers",
        "population growth gold coast",
        "gold coast economy",
        "gold coast jobs",
        "queensland migration",
    ],
    # Lifestyle / relocation sentiment
    "relocation": [
        "move to gold coast",
        "moving to gold coast from sydney",
        "moving to gold coast from melbourne",
        "relocating to gold coast",
        "living on the gold coast pros and cons",
        "is gold coast a good place to live",
        "gold coast vs sunshine coast",
        "gold coast vs brisbane",
        "best places to live gold coast",
        "gold coast lifestyle",
        "gold coast family suburbs",
        "safest suburbs gold coast",
    ],
}


def _load_halo_seeds():
    """Load Halo Strategy seed queries from config/halo_seeds.yaml."""
    halo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "halo_seeds.yaml")
    if not os.path.exists(halo_path):
        return []

    with open(halo_path) as f:
        data = yaml.safe_load(f) or {}

    seeds = []  # list of (query_text, intent_label, suburb_key_or_none)

    # Topic cluster seeds and fears
    for topic_key, topic in (data.get("topics") or {}).items():
        for q in topic.get("seeds", []):
            if "{suburb}" in q:
                for suburb_key, info in SUBURBS.items():
                    expanded = q.format(suburb=info["display"].lower())
                    seeds.append((expanded, "sell", suburb_key))
            else:
                seeds.append((q, "sell", None))
        for q in topic.get("fears", []):
            seeds.append((q, "fear", None))

    # Avatar fears and barriers
    for avatar_key, avatar in (data.get("avatars") or {}).items():
        for q in avatar.get("fears", []):
            seeds.append((q, "fear", None))
        for q in avatar.get("barriers", []):
            seeds.append((q, "decision", None))

    return seeds


def expand_seed_queries():
    """Expand templates into concrete queries with intent and suburb labels."""
    queries = []  # list of (query_text, intent, suburb_key_or_none)
    seen = set()

    # Suburb-specific queries
    for suburb_key, info in SUBURBS.items():
        suburb = info["display"].lower()
        postcode = info["postcode"]
        for intent, templates in SEED_TEMPLATES.items():
            for tmpl in templates:
                q = tmpl.format(suburb=suburb, postcode=postcode)
                if q not in seen:
                    seen.add(q)
                    queries.append((q, intent, suburb_key))

    # General queries
    for intent, qs in GENERAL_QUERIES.items():
        for q in qs:
            if q not in seen:
                seen.add(q)
                queries.append((q, intent, None))

    # Comparison queries
    for a, b in COMPARISON_QUERIES:
        q = f"{a} vs {b}"
        if q not in seen:
            seen.add(q)
            queries.append((q, "research", None))

    # Sentiment / macro queries
    for sentiment, qs in SENTIMENT_QUERIES.items():
        for q in qs:
            if q not in seen:
                seen.add(q)
                queries.append((q, sentiment, None))

    # Halo Strategy seeds (from config/halo_seeds.yaml)
    halo_seeds = _load_halo_seeds()
    halo_count = 0
    for q, intent, suburb_key in halo_seeds:
        q_lower = q.lower().strip()
        if q_lower not in seen:
            seen.add(q_lower)
            queries.append((q_lower, intent, suburb_key))
            halo_count += 1
    if halo_count:
        print(f"  (+{halo_count} Halo Strategy seeds from config/halo_seeds.yaml)")

    return queries


def slug(text, max_len=80):
    """Create a URL-safe slug from text."""
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:max_len]


# ---------------------------------------------------------------------------
# Source 1: Google Autocomplete
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]


def collect_autocomplete(seed_queries):
    """Fetch Google autocomplete suggestions for each seed query."""
    results = []
    errors = []
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")
    ua_idx = 0

    for i, (query, intent, suburb_key) in enumerate(seed_queries):
        try:
            ua = USER_AGENTS[ua_idx % len(USER_AGENTS)]
            ua_idx += 1
            resp = requests.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "q": query, "gl": "au", "hl": "en"},
                headers={"User-Agent": ua},
                timeout=10,
            )

            if resp.status_code == 429:
                errors.append(f"autocomplete: rate limited at query {i} ({query})")
                time.sleep(5)
                continue

            resp.raise_for_status()
            data = resp.json()
            suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []

            results.append({
                "_id": f"auto_{slug(query)}_{date_str}",
                "source": "google_autocomplete",
                "seed_query": query,
                "intent": intent,
                "suburb": suburb_key,
                "suggestions": suggestions,
                "suggestion_count": len(suggestions),
                "date": date_str,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

            # Rate limit: 0.5s between requests
            time.sleep(0.5)

        except Exception as e:
            errors.append(f"autocomplete: {query} — {str(e)[:100]}")
            time.sleep(1)

    return results, errors


# ---------------------------------------------------------------------------
# Source 2: Google Trends (direct API — avoids pytrends urllib3 compat issues)
# ---------------------------------------------------------------------------
TRENDS_EXPLORE_URL = "https://trends.google.com/trends/api/explore"
TRENDS_MULTILINE_URL = "https://trends.google.com/trends/api/widgetdata/multiline"
TRENDS_RELATED_URL = "https://trends.google.com/trends/api/widgetdata/relatedsearches"
TRENDS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _trends_session():
    """Create a requests session with Google Trends cookies."""
    s = requests.Session()
    s.headers.update(TRENDS_HEADERS)
    # Hit the main page to get cookies (NID cookie required)
    s.get("https://trends.google.com/trends/", timeout=10)
    return s


def _parse_trends_json(text):
    """Google Trends API prefixes responses with ')]}' — strip it."""
    if text.startswith(")]}'"):
        text = text[5:]
    return json.loads(text)


def collect_trends(seed_queries):
    """Fetch Google Trends data for keywords using direct API calls."""
    results = []
    errors = []
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")

    # Deduplicate — only trend unique keywords, cap at 30
    unique_keywords = []
    seen = set()
    for query, intent, suburb_key in seed_queries:
        if query not in seen and len(unique_keywords) < 30:
            seen.add(query)
            unique_keywords.append((query, intent, suburb_key))

    try:
        session = _trends_session()
    except Exception as e:
        return [], [f"trends: failed to init session — {str(e)[:100]}"]

    # Process one keyword at a time (Google Trends single-keyword is most reliable)
    for kw_idx, (query, intent, suburb_key) in enumerate(unique_keywords):
        doc = {
            "_id": f"trends_{slug(query)}_{date_str}",
            "source": "google_trends",
            "keyword": query,
            "intent": intent,
            "suburb": suburb_key,
            "date": date_str,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "interest_over_time": [],
            "related_queries_top": [],
            "related_queries_rising": [],
        }

        try:
            # Step 1: Get widget tokens via explore endpoint
            params = {
                "hl": "en-AU",
                "tz": "-600",
                "req": json.dumps({
                    "comparisonItem": [{"keyword": query, "geo": "AU-QLD", "time": "today 3-m"}],
                    "category": 0,
                    "property": "",
                }),
            }
            resp = session.get(TRENDS_EXPLORE_URL, params=params, timeout=15)
            if resp.status_code == 429:
                errors.append(f"trends: rate limited at keyword {kw_idx} ({query})")
                time.sleep(30)
                continue
            resp.raise_for_status()
            explore_data = _parse_trends_json(resp.text)
            widgets = explore_data.get("widgets", [])

            # Step 2: Interest over time (first TIMESERIES widget)
            ts_widget = next((w for w in widgets if w.get("id") == "TIMESERIES"), None)
            if ts_widget and ts_widget.get("token"):
                ts_params = {
                    "hl": "en-AU",
                    "tz": "-600",
                    "req": json.dumps(ts_widget["request"]),
                    "token": ts_widget["token"],
                }
                ts_resp = session.get(TRENDS_MULTILINE_URL, params=ts_params, timeout=15)
                if ts_resp.status_code == 200:
                    ts_data = _parse_trends_json(ts_resp.text)
                    timeline = ts_data.get("default", {}).get("timelineData", [])
                    for point in timeline:
                        doc["interest_over_time"].append({
                            "week": point.get("formattedTime", ""),
                            "value": point["value"][0] if point.get("value") else 0,
                        })
                time.sleep(1)

            # Step 3: Related queries (RELATED_QUERIES widget)
            rq_widget = next((w for w in widgets if w.get("id") == "RELATED_QUERIES"), None)
            if rq_widget and rq_widget.get("token"):
                rq_params = {
                    "hl": "en-AU",
                    "tz": "-600",
                    "req": json.dumps(rq_widget["request"]),
                    "token": rq_widget["token"],
                }
                rq_resp = session.get(TRENDS_RELATED_URL, params=rq_params, timeout=15)
                if rq_resp.status_code == 200:
                    rq_data = _parse_trends_json(rq_resp.text)
                    default = rq_data.get("default", {})

                    # Top related queries
                    ranked = default.get("rankedList", [])
                    if len(ranked) > 0:
                        for item in ranked[0].get("rankedKeyword", [])[:10]:
                            doc["related_queries_top"].append({
                                "query": item.get("query", ""),
                                "value": item.get("value", 0),
                            })
                    # Rising related queries
                    if len(ranked) > 1:
                        for item in ranked[1].get("rankedKeyword", [])[:10]:
                            doc["related_queries_rising"].append({
                                "query": item.get("query", ""),
                                "value": str(item.get("formattedValue", item.get("value", 0))),
                            })

            results.append(doc)
            time.sleep(3)  # Rate limit between keywords

        except Exception as e:
            err_str = str(e)[:100]
            if "429" in err_str:
                errors.append(f"trends: rate limited at keyword {kw_idx} ({query}), waiting 30s")
                time.sleep(30)
            else:
                errors.append(f"trends: {query} — {err_str}")
                # Still append the doc with empty data so we have a record
                results.append(doc)
                time.sleep(3)

    return results, errors


# ---------------------------------------------------------------------------
# Source 3: Google Ads Search Terms Report
# ---------------------------------------------------------------------------
def collect_ads_search_terms():
    """Fetch actual search queries from Google Ads search_term_view."""
    results = []
    errors = []
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")

    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException
    except ImportError:
        return [], ["google-ads: not installed"]

    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN")
    mcc_id = os.environ.get("GOOGLE_ADS_MCC_ID")
    customer_id = os.environ.get("GOOGLE_ADS_CUSTOMER_ID")

    if not all([dev_token, client_id, client_secret, refresh_token, mcc_id, customer_id]):
        return [], ["google-ads: missing credentials in .env"]

    try:
        client = GoogleAdsClient.load_from_dict({
            "developer_token": dev_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "login_customer_id": mcc_id,
            "use_proto_plus": True,
        })

        ga_service = client.get_service("GoogleAdsService")
        start_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        query = f"""
            SELECT
                search_term_view.search_term,
                campaign.name,
                segments.date,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.cost_micros,
                metrics.conversions
            FROM search_term_view
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY metrics.impressions DESC
            LIMIT 500
        """

        response = ga_service.search_stream(customer_id=customer_id, query=query)

        for batch in response:
            for row in batch.results:
                term = row.search_term_view.search_term
                seg_date = row.segments.date
                m = row.metrics
                cost_aud = m.cost_micros / 1_000_000 if m.cost_micros else 0

                results.append({
                    "_id": f"adq_{slug(term)}_{seg_date}",
                    "source": "google_ads_search_terms",
                    "search_term": term,
                    "campaign_name": row.campaign.name,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": round(float(m.ctr), 4) if m.ctr else 0,
                    "cost_aud": round(cost_aud, 2),
                    "conversions": float(m.conversions) if m.conversions else 0,
                    "date": seg_date,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })

        print(f"  Google Ads: {len(results)} search terms collected")

    except GoogleAdsException as gae:
        errors.append(f"google-ads: {str(gae)[:200]}")
    except Exception as e:
        errors.append(f"google-ads: {str(e)[:200]}")

    return results, errors


# ---------------------------------------------------------------------------
# Source 4: Google Search Console
# ---------------------------------------------------------------------------
def collect_search_console():
    """Fetch query performance from Google Search Console."""
    results = []
    errors = []
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return [], ["google-api-python-client: not installed"]

    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_INDEXING_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        return [], ["gsc: missing credentials (GOOGLE_INDEXING_REFRESH_TOKEN)"]

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )

        service = build("searchconsole", "v1", credentials=creds)

        # Query last 5 days (GSC has 2-3 day data lag)
        end_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        request_body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query", "date"],
            "rowLimit": 1000,
        }

        response = service.searchanalytics().query(
            siteUrl="https://fieldsestate.com.au",
            body=request_body,
        ).execute()

        for row in response.get("rows", []):
            query = row["keys"][0]
            row_date = row["keys"][1]

            results.append({
                "_id": f"gsc_{slug(query)}_{row_date}",
                "source": "google_search_console",
                "query": query,
                "impressions": int(row.get("impressions", 0)),
                "clicks": int(row.get("clicks", 0)),
                "ctr": round(row.get("ctr", 0), 4),
                "position": round(row.get("position", 0), 1),
                "date": row_date,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        print(f"  Search Console: {len(results)} query rows collected")

    except Exception as e:
        err = str(e)[:200]
        if "not found" in err.lower() or "forbidden" in err.lower() or "not a verified" in err.lower():
            errors.append("gsc: site not verified — verify fieldsestate.com.au in Google Search Console")
        else:
            errors.append(f"gsc: {err}")

    return results, errors


# ---------------------------------------------------------------------------
# Source 5: Question Discovery (autocomplete question-prefix expansion)
# ---------------------------------------------------------------------------
# Google PAA boxes aren't accessible from cloud IPs. Instead, we use
# autocomplete with question prefixes (why, how, what, can I, should I, etc.)
# to discover the same questions people are asking. This is actually richer
# than PAA because we get ~10 suggestions per prefix per topic.

PAA_SEEDS = [
    # Top Halo Strategy topics
    "real estate agent fees",
    "real estate agent commission",
    "choose a real estate agent",
    "property settlement queensland",
    "capital gains tax property",
    "selling property with tenant",
    "property valuation",
    "best time to sell house",
    "auction vs private sale",
    "sell house without agent",
    "cost of selling a house",
    "same day settlement property",
    "cooling off period property",
    "stamp duty queensland",
    "building and pest inspection",
    "property contract conditions",
    # Avatar fears
    "sell my house",
    "sell house fast",
    "sell house as is",
    "coordinate selling and buying house",
    # Macro
    "house prices australia",
    "gold coast property market",
    "interest rates property",
    "gold coast real estate",
    "investment property gold coast",
    # Suburb
    "robina property",
    "burleigh waters property",
    "varsity lakes property",
]

QUESTION_PREFIXES = [
    "why", "how", "how much", "what", "what is", "what are",
    "can I", "should I", "do I need to", "is it",
    "when to", "where to",
]


def collect_paa(seeds=None):
    """Discover questions via autocomplete question-prefix expansion.

    For each seed topic, prepends question prefixes (why, how, what, can I, etc.)
    and fetches autocomplete suggestions. This reveals the exact questions people
    are typing into Google — equivalent to PAA question chains.
    """
    if seeds is None:
        seeds = PAA_SEEDS

    results = []
    errors = []
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")
    seen_questions = set()
    ua_idx = 0

    for seed in seeds:
        for prefix in QUESTION_PREFIXES:
            query = f"{prefix} {seed}"
            ua = USER_AGENTS[ua_idx % len(USER_AGENTS)]
            ua_idx += 1

            try:
                resp = requests.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client": "firefox", "q": query, "gl": "au", "hl": "en"},
                    headers={"User-Agent": ua},
                    timeout=10,
                )

                if resp.status_code == 429:
                    errors.append(f"paa: rate limited at '{query[:50]}'")
                    time.sleep(5)
                    continue

                if resp.status_code != 200:
                    continue

                data = resp.json()
                suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []

                for s in suggestions:
                    s_norm = s.lower().strip()
                    if s_norm in seen_questions:
                        continue
                    # Filter: must be question-like or contain the seed topic
                    if not (s_norm.startswith(("how", "why", "what", "can", "should",
                                               "do", "is", "when", "where"))
                            or "?" in s_norm):
                        continue
                    seen_questions.add(s_norm)
                    results.append({
                        "_id": f"paa_{slug(s_norm)}_{date_str}",
                        "source": "google_paa",
                        "seed_query": seed,
                        "question": s,
                        "prefix": prefix,
                        "depth": 0,
                        "date": date_str,
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                    })

                time.sleep(0.5)

            except Exception as e:
                errors.append(f"paa: {query[:40]} — {str(e)[:80]}")
                time.sleep(1)

        if len(results) > 1000:
            errors.append("paa: hit 1000 question cap, stopping early")
            break

    return results, errors


# ---------------------------------------------------------------------------
# Source 6: Reddit/Forum Monitor
# ---------------------------------------------------------------------------
REDDIT_SUBREDDITS = ["AusProperty", "AusFinance", "GoldCoast"]
REDDIT_SEARCH_TERMS = [
    "gold coast property", "gold coast house", "gold coast real estate",
    "robina", "burleigh waters", "varsity lakes",
    "sell house queensland", "buy house gold coast",
    "property market crash", "house prices falling", "interest rates property",
    "real estate agent fees", "property valuation",
    "should I sell", "should I buy",
]
REDDIT_UA = "FieldsEstate/1.0 (property research; will@fieldsestate.com.au)"


def collect_reddit():
    """Monitor Reddit for property-related questions and fears.

    Uses RSS feeds (JSON API blocked from cloud VMs since ~2025).
    Fetches new/hot posts from target subreddits plus targeted searches.
    """
    results = []
    errors = []
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")
    seen_ids = set()
    headers = {"User-Agent": REDDIT_UA}

    def _fetch_rss(url, params=None):
        """Fetch a Reddit RSS feed and parse entries."""
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 429:
                errors.append(f"reddit: rate limited on {url[:60]}")
                time.sleep(10)
                return []
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "xml")
            return soup.find_all("entry")
        except Exception as e:
            errors.append(f"reddit: {url[:50]} — {str(e)[:80]}")
            return []

    def _is_property_relevant(title, content=""):
        """Quick keyword check for property relevance."""
        text = (title + " " + content).lower()
        kw = ["property", "house", "real estate", "mortgage", "sell", "buy",
              "auction", "agent", "valuation", "settlement", "stamp duty",
              "gold coast", "robina", "burleigh", "varsity", "investment property",
              "rent", "tenant", "strata", "conveyancer", "cgt", "capital gains",
              "home loan", "interest rate", "downsizing", "upgrading"]
        return any(k in text for k in kw)

    def _entry_to_doc(entry, subreddit, search_term):
        """Convert an RSS entry to a MongoDB document."""
        # Extract post ID from link
        link_el = entry.find("link")
        href = link_el.get("href", "") if link_el else ""
        m = re.search(r"/comments/([a-z0-9]+)/", href)
        post_id = m.group(1) if m else ""

        if not post_id or post_id in seen_ids:
            return None
        seen_ids.add(post_id)

        title = entry.find("title").text.strip() if entry.find("title") else ""
        # Extract text content from HTML content field
        content_el = entry.find("content")
        content_html = content_el.text if content_el else ""
        # Strip HTML to get plain text
        content_text = BeautifulSoup(content_html, "html.parser").get_text(" ", strip=True)[:500]

        author_el = entry.find("author")
        author = ""
        if author_el:
            name_el = author_el.find("name")
            author = name_el.text.replace("/u/", "") if name_el else ""

        updated = entry.find("updated")
        updated_str = updated.text if updated else ""

        if not _is_property_relevant(title, content_text):
            return None

        return {
            "_id": f"reddit_{post_id}",
            "source": "reddit",
            "subreddit": subreddit,
            "title": title,
            "selftext": content_text,
            "author": author,
            "score": 0,  # Not available in RSS
            "num_comments": 0,  # Not available in RSS
            "permalink": href,
            "created_utc": updated_str,
            "search_term": search_term,
            "date": date_str,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    # 1. Fetch "new" posts from each subreddit (RSS gives ~25 per feed)
    for sub in REDDIT_SUBREDDITS:
        entries = _fetch_rss(f"https://www.reddit.com/r/{sub}/new.rss")
        for entry in entries:
            doc = _entry_to_doc(entry, sub, "feed_new")
            if doc:
                results.append(doc)
        time.sleep(1)

    # 2. Fetch "hot" posts
    for sub in REDDIT_SUBREDDITS:
        entries = _fetch_rss(f"https://www.reddit.com/r/{sub}/hot.rss")
        for entry in entries:
            doc = _entry_to_doc(entry, sub, "feed_hot")
            if doc:
                results.append(doc)
        time.sleep(1)

    # 3. Search each subreddit for key terms (RSS search)
    for sub in REDDIT_SUBREDDITS:
        for term in REDDIT_SEARCH_TERMS:
            entries = _fetch_rss(
                f"https://www.reddit.com/r/{sub}/search.rss",
                params={"q": term, "sort": "new", "restrict_sr": "1", "t": "month"},
            )
            for entry in entries:
                doc = _entry_to_doc(entry, sub, term)
                if doc:
                    results.append(doc)
            time.sleep(1)

    # Classify intent and sentiment on results
    for doc in results:
        text = doc.get("title", "") + " " + doc.get("selftext", "")
        doc["intent"] = classify_intent(text)
        doc["sentiment"] = _classify_sentiment(text)

    return results, errors


def _classify_sentiment(text):
    """Simple sentiment classification for a text snippet."""
    text_lower = text.lower()
    fear_words = ["crash", "bubble", "fall", "drop", "worried", "scared", "afraid",
                  "can't afford", "stress", "nightmare", "disaster", "rip off",
                  "scam", "losing", "lost", "negative equity", "downturn", "recession"]
    hope_words = ["growth", "opportunity", "recovery", "going up", "boom", "best time",
                  "good time", "optimistic", "positive", "excited", "upgrade", "dream"]

    fear_score = sum(1 for w in fear_words if w in text_lower)
    hope_score = sum(1 for w in hope_words if w in text_lower)

    if fear_score > hope_score:
        return "fear"
    elif hope_score > fear_score:
        return "hope"
    return "neutral"


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------
INTENT_PATTERNS = {
    # Sentiment categories (check first — these are broader macro queries)
    "fear": re.compile(r"\b(crash|bubble|fall|drop|downturn|negative equity|overpriced|worst time|can't afford|affordability crisis|mortgage stress)\b", re.I),
    "hope": re.compile(r"\b(go up|recovery|boom|best time to buy|good time to buy|forecast|outlook|growth)\b", re.I),
    "decision": re.compile(r"\b(should i (sell|buy|wait)|buyers market|sellers market|buy or rent|buy vs rent|first home buyer|stamp duty|choose a real estate|without agent|commission)\b", re.I),
    "economic": re.compile(r"\b(rba|interest rate|cash rate|inflation|recession|cost of living|migration|population growth|economy)\b", re.I),
    "relocation": re.compile(r"\b(move to|moving to|relocating|pros and cons|good place to live|lifestyle|family suburb|safest suburb)\b", re.I),
    # Property-specific intents
    "buy": re.compile(r"\b(for sale|buy|buying|purchase|houses for sale|units for sale|townhouse for sale)\b", re.I),
    "sell": re.compile(r"\b(sell|selling|agent fee|what is my house worth|how to sell|best time to sell|list my)\b", re.I),
    "value": re.compile(r"\b(price|valuation|value|median|how much|worth|house prices)\b", re.I),
    "invest": re.compile(r"\b(invest|yield|rental yield|capital growth|roi)\b", re.I),
    "rent": re.compile(r"\b(rent|rental|lease|tenant)\b", re.I),
    "research": re.compile(r"\b(suburb profile|demographics|schools|crime|vs |comparison|report|data|trends|living in)\b", re.I),
}


def classify_intent(query_text):
    """Classify a search query by intent using keyword patterns."""
    for intent, pattern in INTENT_PATTERNS.items():
        if pattern.search(query_text):
            return intent
    return "other"


# ---------------------------------------------------------------------------
# New query detection
# ---------------------------------------------------------------------------
def detect_new_queries(sm_db, current_suggestions, lookback_days=30):
    """Find suggestions not seen in the last N days."""
    cutoff = (datetime.now(AEST) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    today = datetime.now(AEST).strftime("%Y-%m-%d")

    # Get all previous suggestions
    prev_docs = list(sm_db["search_suggestions"].find(
        {"date": {"$gte": cutoff, "$lt": today}},
        {"suggestions": 1},
    ))

    previous_set = set()
    for doc in prev_docs:
        for s in doc.get("suggestions", []):
            previous_set.add(s.lower().strip())

    # Get current suggestions
    current_set = set()
    for doc in current_suggestions:
        for s in doc.get("suggestions", []):
            current_set.add(s.lower().strip())

    new_queries = sorted(current_set - previous_set)
    return new_queries


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------
def build_summary(auto_results, trends_results, ads_results, gsc_results,
                   paa_results, reddit_results, new_queries, errors):
    """Build a cross-source summary document."""
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")

    # Collect all unique query strings across all sources
    all_queries = set()
    for doc in auto_results:
        for s in doc.get("suggestions", []):
            all_queries.add(s.lower().strip())
    for doc in ads_results:
        all_queries.add(doc.get("search_term", "").lower().strip())
    for doc in gsc_results:
        all_queries.add(doc.get("query", "").lower().strip())
    for doc in paa_results:
        all_queries.add(doc.get("question", "").lower().strip())

    # Intent distribution
    intent_dist = {}
    for q in all_queries:
        intent = classify_intent(q)
        intent_dist[intent] = intent_dist.get(intent, 0) + 1

    # Rising queries from trends
    trending_up = []
    for doc in trends_results:
        for rq in doc.get("related_queries_rising", []):
            trending_up.append(rq["query"])

    # Reddit sentiment breakdown
    reddit_sentiment = {"fear": 0, "hope": 0, "neutral": 0}
    for doc in reddit_results:
        s = doc.get("sentiment", "neutral")
        reddit_sentiment[s] = reddit_sentiment.get(s, 0) + 1

    # Top PAA questions (unique)
    paa_questions = list({doc.get("question", ""): doc for doc in paa_results}.keys())[:30]

    return {
        "_id": f"summary_{date_str}",
        "date": date_str,
        "total_unique_queries": len(all_queries),
        "total_autocomplete_docs": len(auto_results),
        "total_trends_keywords": len(trends_results),
        "total_ad_queries": len(ads_results),
        "total_gsc_queries": len(gsc_results),
        "total_paa_questions": len(paa_results),
        "total_reddit_posts": len(reddit_results),
        "new_queries": new_queries[:50],  # Cap at 50
        "new_query_count": len(new_queries),
        "trending_up": trending_up[:20],
        "top_paa_questions": paa_questions,
        "reddit_sentiment": reddit_sentiment,
        "intent_distribution": intent_dist,
        "errors": errors,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# MongoDB persistence (follows fb-metrics-collector.py pattern)
# ---------------------------------------------------------------------------
def batched_bulk_write(collection, ops, batch_size=10, delay=0.5, label=""):
    """Write operations in small batches with delays to avoid Cosmos DB RU throttling."""
    total_upserted = 0
    total_modified = 0
    for i in range(0, len(ops), batch_size):
        batch = ops[i:i + batch_size]
        retries = 0
        while retries < 3:
            try:
                result = collection.bulk_write(batch, ordered=False)
                total_upserted += result.upserted_count
                total_modified += result.modified_count
                break
            except BulkWriteError as bwe:
                total_upserted += bwe.details.get("nUpserted", 0)
                total_modified += bwe.details.get("nModified", 0)
                errors = bwe.details.get("writeErrors", [])
                throttled = [e for e in errors if e.get("code") == 16500]
                if throttled:
                    retries += 1
                    if retries < 3:
                        time.sleep(2)
                    continue
                break
        time.sleep(delay)

    if label:
        print(f"  {label}: {total_upserted} inserted, {total_modified} updated")
    return total_upserted, total_modified


def ensure_indexes(sm_db):
    """Create indexes on search collections (idempotent)."""
    for coll_name in ["search_suggestions", "search_trends", "search_ad_queries",
                       "search_console_queries", "search_paa_questions", "search_reddit_posts"]:
        coll = sm_db[coll_name]
        coll.create_index("date")
    sm_db["search_intent_summary"].create_index("date")


def prune_old_data(sm_db, retention_days=180):
    """Delete docs older than retention period."""
    cutoff = (datetime.now(AEST) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    total = 0
    for coll_name in ["search_suggestions", "search_trends", "search_ad_queries",
                       "search_console_queries", "search_paa_questions",
                       "search_reddit_posts", "search_intent_summary"]:
        result = sm_db[coll_name].delete_many({"date": {"$lt": cutoff}})
        total += result.deleted_count
    if total > 0:
        print(f"  Pruned {total} docs older than {retention_days} days")


# ---------------------------------------------------------------------------
# Report mode
# ---------------------------------------------------------------------------
def print_report(sm_db, days=30):
    """Print a summary report of collected search intent data."""
    cutoff = (datetime.now(AEST) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Get summaries
    summaries = list(sm_db["search_intent_summary"].find(
        {"date": {"$gte": cutoff}},
    ).sort("date", -1))

    if not summaries:
        print(f"No data found in the last {days} days. Run a collection first.")
        return

    print(f"\n{'='*60}")
    print(f"SEARCH INTENT REPORT — Last {days} days")
    print(f"{'='*60}")

    # Collection runs
    print(f"\nCollection runs: {len(summaries)}")
    for s in summaries[:5]:
        print(f"  {s['date']}: {s.get('total_unique_queries', 0)} unique queries, "
              f"{s.get('new_query_count', 0)} new, "
              f"{len(s.get('errors', []))} errors")

    # Latest intent distribution
    latest = summaries[0]
    intent_dist = latest.get("intent_distribution", {})
    if intent_dist:
        print(f"\nIntent Distribution (latest run {latest['date']}):")
        total = sum(intent_dist.values())
        for intent, count in sorted(intent_dist.items(), key=lambda x: -x[1]):
            pct = count / total * 100 if total > 0 else 0
            bar = "█" * int(pct / 2)
            print(f"  {intent:<12} {count:>4}  ({pct:5.1f}%)  {bar}")

    # Sentiment Gauge — fear vs hope balance
    SENTIMENT_CATS = ["fear", "hope", "decision", "economic", "relocation"]
    sentiment_counts = {cat: intent_dist.get(cat, 0) for cat in SENTIMENT_CATS}
    sentiment_total = sum(sentiment_counts.values())
    if sentiment_total > 0:
        fear_count = sentiment_counts.get("fear", 0)
        hope_count = sentiment_counts.get("hope", 0)
        fear_hope_total = fear_count + hope_count
        if fear_hope_total > 0:
            fear_pct = fear_count / fear_hope_total * 100
            hope_pct = hope_count / fear_hope_total * 100
            # Visual gauge: FEAR ████░░░░ HOPE
            gauge_width = 30
            fear_bars = int(fear_pct / 100 * gauge_width)
            hope_bars = gauge_width - fear_bars
            print(f"\nSentiment Gauge:")
            print(f"  FEAR {'█' * fear_bars}{'░' * hope_bars} HOPE")
            print(f"  {fear_pct:.0f}% fearful / {hope_pct:.0f}% hopeful  ({fear_count} vs {hope_count} queries)")

        print(f"\nSentiment Breakdown:")
        for cat in SENTIMENT_CATS:
            count = sentiment_counts[cat]
            if count > 0:
                pct = count / sentiment_total * 100
                emoji = {"fear": "😰", "hope": "🟢", "decision": "🤔", "economic": "📊", "relocation": "🏠"}
                print(f"  {emoji.get(cat, '  ')} {cat:<12} {count:>3}  ({pct:5.1f}%)")

        # Show top sentiment queries from autocomplete
        auto_sentiment_docs = list(sm_db["search_suggestions"].find(
            {"date": latest["date"], "intent": {"$in": SENTIMENT_CATS}},
            {"seed_query": 1, "suggestions": 1, "intent": 1},
        ))
        if auto_sentiment_docs:
            print(f"\n  Top Sentiment Autocomplete (what people are actually typing):")
            sent_suggestions = {}
            for doc in auto_sentiment_docs:
                cat = doc.get("intent", "other")
                for s in doc.get("suggestions", []):
                    key = (cat, s.lower().strip())
                    sent_suggestions[key] = sent_suggestions.get(key, 0) + 1
            for (cat, q), freq in sorted(sent_suggestions.items(), key=lambda x: -x[1])[:15]:
                label = {"fear": "FEAR", "hope": "HOPE", "decision": "DECIDE",
                         "economic": "ECON", "relocation": "RELO"}.get(cat, cat.upper())
                print(f"    {freq}x  [{label:<6}]  {q}")

    # New queries from latest run
    new_queries = latest.get("new_queries", [])
    if new_queries:
        print(f"\nNew Queries ({len(new_queries)} found on {latest['date']}):")
        for q in new_queries[:15]:
            print(f"  • {q}")
        if len(new_queries) > 15:
            print(f"  ... and {len(new_queries) - 15} more")

    # Trending up
    trending = latest.get("trending_up", [])
    if trending:
        print(f"\nTrending Up (Google Trends rising queries):")
        for q in trending[:10]:
            print(f"  ↑ {q}")

    # Top autocomplete suggestions (aggregate across all seed queries)
    auto_docs = list(sm_db["search_suggestions"].find(
        {"date": latest["date"]},
        {"suggestions": 1, "seed_query": 1},
    ))
    suggestion_freq = {}
    for doc in auto_docs:
        for s in doc.get("suggestions", []):
            s_lower = s.lower().strip()
            suggestion_freq[s_lower] = suggestion_freq.get(s_lower, 0) + 1

    if suggestion_freq:
        print(f"\nTop 20 Autocomplete Suggestions (by frequency across seeds):")
        top_20 = sorted(suggestion_freq.items(), key=lambda x: -x[1])[:20]
        for q, freq in top_20:
            intent = classify_intent(q)
            print(f"  {freq:>2}x  [{intent:<8}]  {q}")

    # Google Ads search terms (if any) — sort in Python (Cosmos can't sort on unindexed fields)
    ad_docs = sorted(
        sm_db["search_ad_queries"].find({"date": {"$gte": cutoff}}),
        key=lambda d: d.get("impressions", 0), reverse=True,
    )[:15]
    if ad_docs:
        print(f"\nTop Google Ads Search Terms:")
        print(f"  {'Term':<40} {'Impr':>6} {'Clicks':>6} {'Cost':>8}")
        print(f"  {'-'*62}")
        for d in ad_docs:
            print(f"  {d['search_term']:<40} {d['impressions']:>6} "
                  f"{d['clicks']:>6} ${d.get('cost_aud', 0):>7.2f}")

    # GSC queries (if any) — sort in Python
    gsc_docs = sorted(
        sm_db["search_console_queries"].find({"date": {"$gte": cutoff}}),
        key=lambda d: d.get("impressions", 0), reverse=True,
    )[:15]
    if gsc_docs:
        print(f"\nTop Google Search Console Queries:")
        print(f"  {'Query':<40} {'Impr':>6} {'Clicks':>6} {'CTR':>6} {'Pos':>5}")
        print(f"  {'-'*65}")
        for d in gsc_docs:
            print(f"  {d['query']:<40} {d['impressions']:>6} "
                  f"{d['clicks']:>6} {d['ctr']:>5.1%} {d['position']:>5.1f}")

    # PAA Questions
    paa_docs = list(sm_db["search_paa_questions"].find(
        {"date": {"$gte": cutoff}},
        {"question": 1, "seed_query": 1, "depth": 1},
    ))
    if paa_docs:
        print(f"\nPeople Also Ask — {len(paa_docs)} questions discovered:")
        # Frequency: how many times each question appeared across runs
        q_freq = {}
        for doc in paa_docs:
            q = doc.get("question", "")
            q_freq[q] = q_freq.get(q, 0) + 1
        for q, freq in sorted(q_freq.items(), key=lambda x: -x[1])[:15]:
            intent = classify_intent(q)
            print(f"  {freq}x  [{intent:<8}]  {q}")

    # Reddit Pulse
    reddit_docs = list(sm_db["search_reddit_posts"].find(
        {"date": {"$gte": cutoff}},
        {"title": 1, "subreddit": 1, "score": 1, "num_comments": 1, "sentiment": 1},
    ))
    if reddit_docs:
        print(f"\nReddit Pulse — {len(reddit_docs)} property-related posts:")
        # Sentiment breakdown
        r_sent = {"fear": 0, "hope": 0, "neutral": 0}
        for doc in reddit_docs:
            s = doc.get("sentiment", "neutral")
            r_sent[s] = r_sent.get(s, 0) + 1
        total_r = sum(r_sent.values())
        if total_r > 0:
            print(f"  Sentiment: fear {r_sent['fear']}/{total_r} ({r_sent['fear']/total_r*100:.0f}%) | "
                  f"hope {r_sent['hope']}/{total_r} ({r_sent['hope']/total_r*100:.0f}%) | "
                  f"neutral {r_sent['neutral']}/{total_r} ({r_sent['neutral']/total_r*100:.0f}%)")

        # Top posts by engagement (score + comments)
        top_posts = sorted(reddit_docs,
                          key=lambda d: d.get("score", 0) + d.get("num_comments", 0),
                          reverse=True)[:10]
        for doc in top_posts:
            score = doc.get("score", 0)
            comments = doc.get("num_comments", 0)
            sub = doc.get("subreddit", "?")
            title = doc.get("title", "")[:70]
            sent = doc.get("sentiment", "?")
            print(f"  [{sent:<7}] r/{sub}: {title}  (+{score}, {comments}💬)")

    # Data source status
    print(f"\nData Sources:")
    print(f"  Autocomplete:    {sm_db['search_suggestions'].count_documents({'date': {'$gte': cutoff}})} docs")
    print(f"  Google Trends:   {sm_db['search_trends'].count_documents({'date': {'$gte': cutoff}})} docs")
    print(f"  Google Ads:      {sm_db['search_ad_queries'].count_documents({'date': {'$gte': cutoff}})} docs")
    print(f"  Search Console:  {sm_db['search_console_queries'].count_documents({'date': {'$gte': cutoff}})} docs")
    print(f"  PAA Questions:   {sm_db['search_paa_questions'].count_documents({'date': {'$gte': cutoff}})} docs")
    print(f"  Reddit Posts:    {sm_db['search_reddit_posts'].count_documents({'date': {'$gte': cutoff}})} docs")

    print(f"\n{'='*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Search Intent Data Collector")
    parser.add_argument("--source", choices=["all", "auto", "trends", "ads", "gsc", "paa", "reddit"],
                        default="all", help="Which source(s) to collect from")
    parser.add_argument("--report", action="store_true", help="Print summary report instead of collecting")
    parser.add_argument("--days", type=int, default=30, help="Days to include in report (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Collect but don't save to MongoDB")
    args = parser.parse_args()

    client = MongoClient(COSMOS_URI)
    sm_db = client["system_monitor"]

    if args.report:
        print_report(sm_db, days=args.days)
        client.close()
        return

    print(f"Search Intent Collector — {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}")
    print(f"Source: {args.source}")
    print()

    # Expand seed queries
    seed_queries = expand_seed_queries()
    print(f"Seed queries: {len(seed_queries)}")

    all_errors = []
    auto_results = []
    trends_results = []
    ads_results = []
    gsc_results = []
    paa_results = []
    reddit_results = []

    # Collect from each source
    if args.source in ("all", "auto"):
        print("\n[1/6] Google Autocomplete...")
        auto_results, errs = collect_autocomplete(seed_queries)
        all_errors.extend(errs)
        total_suggestions = sum(d.get("suggestion_count", 0) for d in auto_results)
        print(f"  Collected {len(auto_results)} seed results with {total_suggestions} total suggestions")

    if args.source in ("all", "trends"):
        print("\n[2/6] Google Trends...")
        # Use high-volume keywords that Trends actually has data for
        # (suburb-specific queries like "robina property for sale" return zeros)
        TRENDS_KEYWORDS = [
            ("gold coast property", "buy", None),
            ("gold coast real estate", "buy", None),
            ("house prices australia", "value", None),
            ("property market crash", "fear", None),
            ("interest rates australia", "economic", None),
            ("first home buyer", "decision", None),
            ("real estate agent fees", "sell", None),
            ("stamp duty calculator", "decision", None),
            ("property valuation", "value", None),
            ("housing market australia", "research", None),
            ("capital gains tax property", "sell", None),
            ("gold coast house prices", "value", None),
            ("mortgage rates australia", "economic", None),
            ("robina", "research", "robina"),
            ("burleigh waters", "research", "burleigh_waters"),
            ("varsity lakes", "research", "varsity_lakes"),
            ("gold coast", "research", None),
            ("property market australia", "research", None),
            ("sell house australia", "sell", None),
            ("buy house gold coast", "buy", None),
        ]
        trends_results, errs = collect_trends(TRENDS_KEYWORDS)
        all_errors.extend(errs)
        print(f"  Collected {len(trends_results)} trend docs")

    if args.source in ("all", "ads"):
        print("\n[3/6] Google Ads Search Terms...")
        ads_results, errs = collect_ads_search_terms()
        all_errors.extend(errs)

    if args.source in ("all", "gsc"):
        print("\n[4/6] Google Search Console...")
        gsc_results, errs = collect_search_console()
        all_errors.extend(errs)

    if args.source in ("all", "paa"):
        print("\n[5/6] Google People Also Ask...")
        paa_results, errs = collect_paa()
        all_errors.extend(errs)
        print(f"  Collected {len(paa_results)} PAA questions")

    if args.source in ("all", "reddit"):
        print("\n[6/6] Reddit Monitor...")
        reddit_results, errs = collect_reddit()
        all_errors.extend(errs)
        print(f"  Collected {len(reddit_results)} Reddit posts")

    # Detect new queries
    new_queries = detect_new_queries(sm_db, auto_results) if auto_results else []

    # Build summary
    summary = build_summary(auto_results, trends_results, ads_results, gsc_results,
                            paa_results, reddit_results, new_queries, all_errors)

    if args.dry_run:
        print(f"\n--- DRY RUN (not saving) ---")
        print(f"Would save: {len(auto_results)} autocomplete, {len(trends_results)} trends, "
              f"{len(ads_results)} ad queries, {len(gsc_results)} gsc queries, "
              f"{len(paa_results)} PAA questions, {len(reddit_results)} Reddit posts")
        print(f"New queries: {len(new_queries)}")
        if new_queries:
            for q in new_queries[:10]:
                print(f"  NEW: {q}")
        if paa_results:
            print(f"\nTop PAA Questions:")
            for doc in paa_results[:10]:
                print(f"  ? {doc['question']}")
        if reddit_results:
            print(f"\nReddit Posts:")
            for doc in reddit_results[:10]:
                print(f"  [{doc.get('sentiment','?'):<7}] r/{doc.get('subreddit','?')}: {doc['title'][:70]}")
        print(f"\nIntent distribution: {summary.get('intent_distribution', {})}")
        if all_errors:
            print(f"\nErrors ({len(all_errors)}):")
            for e in all_errors:
                print(f"  ⚠ {e}")
        client.close()
        return

    # Save to MongoDB
    print(f"\nSaving to MongoDB...")
    ensure_indexes(sm_db)

    if auto_results:
        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in auto_results]
        batched_bulk_write(sm_db["search_suggestions"], ops, label="search_suggestions")

    if trends_results:
        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in trends_results]
        batched_bulk_write(sm_db["search_trends"], ops, label="search_trends")

    if ads_results:
        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in ads_results]
        batched_bulk_write(sm_db["search_ad_queries"], ops, label="search_ad_queries")

    if gsc_results:
        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in gsc_results]
        batched_bulk_write(sm_db["search_console_queries"], ops, label="search_console_queries")

    if paa_results:
        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in paa_results]
        batched_bulk_write(sm_db["search_paa_questions"], ops, label="search_paa_questions")

    if reddit_results:
        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in reddit_results]
        batched_bulk_write(sm_db["search_reddit_posts"], ops, label="search_reddit_posts")

    # Save summary
    sm_db["search_intent_summary"].update_one(
        {"_id": summary["_id"]}, {"$set": summary}, upsert=True
    )
    print(f"  search_intent_summary: saved")

    # Prune old data
    prune_old_data(sm_db, RETENTION_DAYS)

    # Print summary
    print(f"\n--- Summary ---")
    print(f"  Unique queries discovered: {summary['total_unique_queries']}")
    print(f"  New queries (not seen in 30d): {len(new_queries)}")
    if new_queries:
        for q in new_queries[:5]:
            print(f"    NEW: {q}")
        if len(new_queries) > 5:
            print(f"    ... and {len(new_queries) - 5} more")
    print(f"  Intent: {summary.get('intent_distribution', {})}")
    if summary.get("trending_up"):
        print(f"  Trending up: {', '.join(summary['trending_up'][:5])}")
    if all_errors:
        print(f"\n  Errors ({len(all_errors)}):")
        for e in all_errors[:10]:
            print(f"    ⚠ {e}")

    print(f"\nDone.")
    client.close()


if __name__ == "__main__":
    main()

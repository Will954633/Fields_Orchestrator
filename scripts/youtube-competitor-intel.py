#!/usr/bin/env python3
"""
YouTube Competitor Intelligence — find what real estate content works in Australia.

Uses YouTube Data API v3 to:
  1. Search for Australian real estate content across all topics/locations
  2. Discover top-performing channels (by views, subscribers, consistency)
  3. Pull every channel's top videos (sorted by view count)
  4. Extract topic patterns, title formats, and keywords that drive views
  5. Feed winning patterns back into search-intent-collector as YouTube seeds

Env: YOUTUBE_API_KEY (in .env)
Quota: ~10,000 units/day free. Search = 100 units, video list = 1 unit, channel list = 1 unit.

Collections written (all in system_monitor):
  - youtube_competitor_channels  : channels with stats, top videos
  - youtube_competitor_videos    : individual videos with exact view/like counts

Usage:
    python3 scripts/youtube-competitor-intel.py                # Full scan (discover + analyse)
    python3 scripts/youtube-competitor-intel.py --discover      # Find channels + pull their videos
    python3 scripts/youtube-competitor-intel.py --analyse       # Analyse existing data only
    python3 scripts/youtube-competitor-intel.py --dry-run       # Collect but don't save
"""

import os
import re
import json
import time
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
YT_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
AEST = timezone(timedelta(hours=10))

YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YT_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YT_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YT_PLAYLIST_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

# Track quota usage (10,000/day limit)
quota_used = 0

def _api_get(url, params, cost=1):
    """Make a YouTube API request, tracking quota."""
    global quota_used
    params["key"] = YT_API_KEY
    resp = requests.get(url, params=params, timeout=15)
    quota_used += cost
    if resp.status_code == 403:
        error = resp.json().get("error", {}).get("errors", [{}])[0]
        if error.get("reason") == "quotaExceeded":
            print(f"\n  ⚠ QUOTA EXCEEDED (used ~{quota_used} units). Try again tomorrow.")
            raise SystemExit(1)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Search queries — broad Australian real estate + specific topics
# ---------------------------------------------------------------------------
DISCOVERY_QUERIES = [
    # Broad
    "australian property market",
    "australia real estate",
    "property investment australia",
    "australian housing market",
    "property market update australia",

    # Major cities (find what works everywhere, not just GC)
    "gold coast property",
    "gold coast real estate",
    "brisbane property market",
    "sydney property market",
    "melbourne property market",
    "perth property market",
    "adelaide property market",

    # Topic types that might get views
    "suburb review australia",
    "should i buy a house australia",
    "property market crash australia",
    "first home buyer tips australia",
    "how to invest in property australia",
    "selling house tips australia",
    "real estate agent tips",
    "property auction australia",
    "house tour australia",
    "property data analysis australia",
    "rental yield australia explained",
    "negative gearing australia",
    "property valuation explained",
    "interest rate property australia",

    # Queensland specific
    "queensland property market",
    "gold coast suburb guide",
    "brisbane suburb review",
    "southeast queensland property",
]


def search_videos(query, max_results=25):
    """Search YouTube for videos matching a query. Returns video IDs + basic info."""
    results = []
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "regionCode": "AU",
        "relevanceLanguage": "en",
        "maxResults": min(max_results, 50),
        "order": "relevance",
    }

    data = _api_get(YT_SEARCH_URL, params, cost=100)

    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        results.append({
            "video_id": item.get("id", {}).get("videoId", ""),
            "title": snippet.get("title", ""),
            "channel_id": snippet.get("channelId", ""),
            "channel_name": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
            "description": snippet.get("description", "")[:300],
            "query": query,
        })

    return results


def get_video_stats(video_ids):
    """Get exact view/like counts for a batch of videos. Max 50 per call."""
    if not video_ids:
        return {}

    stats = {}
    # Process in batches of 50
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        params = {
            "part": "statistics,contentDetails",
            "id": ",".join(batch),
        }
        data = _api_get(YT_VIDEOS_URL, params, cost=1)

        for item in data.get("items", []):
            vid = item["id"]
            s = item.get("statistics", {})
            cd = item.get("contentDetails", {})
            stats[vid] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
                "duration": cd.get("duration", ""),
            }

    return stats


def get_channel_stats(channel_ids):
    """Get subscriber count, total views, video count for channels."""
    if not channel_ids:
        return {}

    stats = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        params = {
            "part": "statistics,snippet,contentDetails",
            "id": ",".join(batch),
        }
        data = _api_get(YT_CHANNELS_URL, params, cost=1)

        for item in data.get("items", []):
            cid = item["id"]
            s = item.get("statistics", {})
            snippet = item.get("snippet", {})
            cd = item.get("contentDetails", {})
            stats[cid] = {
                "subscribers": int(s.get("subscriberCount", 0)),
                "total_views": int(s.get("viewCount", 0)),
                "total_videos": int(s.get("videoCount", 0)),
                "channel_name": snippet.get("title", ""),
                "description": snippet.get("description", "")[:500],
                "created_at": snippet.get("publishedAt", ""),
                "uploads_playlist": (cd.get("relatedPlaylists", {}).get("uploads", "")),
            }

    return stats


def get_channel_top_videos(uploads_playlist_id, max_results=30):
    """Get video IDs from a channel's uploads playlist."""
    video_ids = []
    params = {
        "part": "contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": min(max_results, 50),
    }

    try:
        data = _api_get(YT_PLAYLIST_URL, params, cost=1)
        for item in data.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId", "")
            if vid:
                video_ids.append(vid)
    except Exception as e:
        print(f"    Playlist error: {str(e)[:80]}")

    return video_ids


def discover_channels(sm_db, dry_run=False):
    """Full discovery: search → find channels → get their stats → pull top videos."""
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")

    # Step 1: Search to find videos and channels
    print(f"\n[1/4] Searching {len(DISCOVERY_QUERIES)} queries...")
    all_search_results = []

    for i, query in enumerate(DISCOVERY_QUERIES):
        print(f"  [{i+1}/{len(DISCOVERY_QUERIES)}] {query}", end="", flush=True)
        try:
            results = search_videos(query, max_results=25)
            all_search_results.extend(results)
            print(f" → {len(results)} videos")
        except Exception as e:
            print(f" → ERROR: {str(e)[:60]}")
        time.sleep(0.2)

    # Deduplicate videos
    seen_vids = {}
    for v in all_search_results:
        vid = v["video_id"]
        if vid and vid not in seen_vids:
            seen_vids[vid] = v

    unique_videos = list(seen_vids.values())
    print(f"\n  Unique videos from search: {len(unique_videos)}")

    # Collect unique channel IDs
    channel_ids = list({v["channel_id"] for v in unique_videos if v["channel_id"]})
    print(f"  Unique channels found: {len(channel_ids)}")
    print(f"  Quota used so far: ~{quota_used} units")

    # Step 2: Get channel statistics
    print(f"\n[2/4] Getting channel statistics for {len(channel_ids)} channels...")
    channel_stats = get_channel_stats(channel_ids)
    print(f"  Got stats for {len(channel_stats)} channels")

    # Step 3: Get video statistics for search results
    print(f"\n[3/4] Getting video statistics for {len(unique_videos)} videos...")
    video_ids = [v["video_id"] for v in unique_videos]
    video_stats = get_video_stats(video_ids)
    print(f"  Got stats for {len(video_stats)} videos")

    # Merge stats into video records
    for v in unique_videos:
        stats = video_stats.get(v["video_id"], {})
        v.update(stats)

    # Step 4: For top channels, pull their recent uploads and find their best videos
    print(f"\n[4/4] Pulling top videos from best channels...")

    # Rank channels by engagement from search results
    channel_video_map = defaultdict(list)
    for v in unique_videos:
        channel_video_map[v["channel_id"]].append(v)

    # Score channels: total views from discovered videos
    channel_scores = []
    for cid, vids in channel_video_map.items():
        total_views = sum(v.get("views", 0) for v in vids)
        cs = channel_stats.get(cid, {})
        channel_scores.append({
            "channel_id": cid,
            "channel_name": cs.get("channel_name", vids[0].get("channel_name", "")),
            "subscribers": cs.get("subscribers", 0),
            "total_channel_views": cs.get("total_views", 0),
            "total_videos": cs.get("total_videos", 0),
            "discovered_video_views": total_views,
            "discovered_video_count": len(vids),
            "uploads_playlist": cs.get("uploads_playlist", ""),
            "description": cs.get("description", ""),
            "created_at": cs.get("created_at", ""),
        })

    channel_scores.sort(key=lambda c: -c["subscribers"])

    # Pull recent uploads from top 30 channels (by subscribers)
    top_channels = [c for c in channel_scores if c["uploads_playlist"]][:30]
    extra_video_ids = []

    for i, ch in enumerate(top_channels):
        print(f"  [{i+1}/{len(top_channels)}] {ch['channel_name']} ({ch['subscribers']:,} subs)", end="", flush=True)
        vids = get_channel_top_videos(ch["uploads_playlist"], max_results=30)
        new_vids = [v for v in vids if v not in seen_vids]
        extra_video_ids.extend(new_vids)
        print(f" → {len(new_vids)} new videos")
        time.sleep(0.1)

    # Get stats for new videos
    if extra_video_ids:
        print(f"\n  Getting stats for {len(extra_video_ids)} additional videos...")
        extra_stats = get_video_stats(extra_video_ids)

        # We need titles too — get snippet info
        for i in range(0, len(extra_video_ids), 50):
            batch = extra_video_ids[i:i+50]
            params = {
                "part": "snippet",
                "id": ",".join(batch),
            }
            data = _api_get(YT_VIDEOS_URL, params, cost=1)
            for item in data.get("items", []):
                vid = item["id"]
                snippet = item.get("snippet", {})
                stats = extra_stats.get(vid, {})
                if vid not in seen_vids:
                    seen_vids[vid] = {
                        "video_id": vid,
                        "title": snippet.get("title", ""),
                        "channel_id": snippet.get("channelId", ""),
                        "channel_name": snippet.get("channelTitle", ""),
                        "published_at": snippet.get("publishedAt", ""),
                        "description": snippet.get("description", "")[:300],
                        "query": "channel_upload",
                        **stats,
                    }

    all_videos = list(seen_vids.values())
    all_videos.sort(key=lambda v: -v.get("views", 0))

    print(f"\n  Total videos collected: {len(all_videos)}")
    print(f"  Total quota used: ~{quota_used} units")

    # Print results
    print(f"\n{'='*110}")
    print(f"  TOP 30 CHANNELS (by subscribers)")
    print(f"{'='*110}")
    print(f"  {'Channel':<35} {'Subs':>10} {'Total Views':>14} {'Videos':>7} {'Discovered':>10}")
    print(f"  {'-'*80}")
    for ch in channel_scores[:30]:
        print(f"  {ch['channel_name']:<35} {ch['subscribers']:>10,} {ch['total_channel_views']:>14,} "
              f"{ch['total_videos']:>7,} {ch['discovered_video_count']:>10}")

    print(f"\n{'='*110}")
    print(f"  TOP 50 VIDEOS (by views)")
    print(f"{'='*110}")
    print(f"  {'Views':>12} {'Channel':<30} {'Title'}")
    print(f"  {'-'*100}")
    for v in all_videos[:50]:
        print(f"  {v.get('views', 0):>12,} {v.get('channel_name', ''):<30} {v.get('title', '')[:55]}")

    # Save to MongoDB
    if not dry_run:
        print(f"\n  Saving to MongoDB...")

        # Channel docs
        channel_docs = []
        for ch in channel_scores:
            # Attach top videos
            ch_vids = [v for v in all_videos if v.get("channel_id") == ch["channel_id"]]
            ch_vids.sort(key=lambda v: -v.get("views", 0))
            top_vids = [{
                "video_id": v["video_id"],
                "title": v.get("title", ""),
                "views": v.get("views", 0),
                "likes": v.get("likes", 0),
                "published_at": v.get("published_at", ""),
            } for v in ch_vids[:20]]

            channel_docs.append({
                "_id": f"ytch_{ch['channel_id']}",
                "channel_id": ch["channel_id"],
                "channel_name": ch["channel_name"],
                "subscribers": ch["subscribers"],
                "total_channel_views": ch["total_channel_views"],
                "total_videos": ch["total_videos"],
                "description": ch["description"],
                "created_at": ch["created_at"],
                "top_videos": top_vids,
                "date": date_str,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in channel_docs]
        _batched_bulk_write(sm_db["youtube_competitor_channels"], ops, "youtube_competitor_channels")

        # Video docs
        video_docs = []
        for v in all_videos:
            if not v.get("video_id"):
                continue
            video_docs.append({
                "_id": f"ytv_{v['video_id']}",
                "video_id": v["video_id"],
                "title": v.get("title", ""),
                "channel_name": v.get("channel_name", ""),
                "channel_id": v.get("channel_id", ""),
                "views": v.get("views", 0),
                "likes": v.get("likes", 0),
                "comments": v.get("comments", 0),
                "duration": v.get("duration", ""),
                "published_at": v.get("published_at", ""),
                "description": v.get("description", ""),
                "discovery_query": v.get("query", ""),
                "date": date_str,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in video_docs]
        _batched_bulk_write(sm_db["youtube_competitor_videos"], ops, "youtube_competitor_videos")

    return channel_scores, all_videos


def analyse_topics(sm_db):
    """Analyse collected competitor videos to extract winning topic patterns."""
    print(f"\n{'='*110}")
    print(f"  TOPIC ANALYSIS")
    print(f"{'='*110}")

    # Cosmos DB can't sort on unindexed fields — sort in Python
    videos = list(sm_db["youtube_competitor_videos"].find())
    videos.sort(key=lambda v: -v.get("views", 0))
    if not videos:
        print("  No competitor videos found. Run --discover first.")
        return

    print(f"  {len(videos)} videos to analyse")

    # Topic classifiers
    TOPIC_PATTERNS = {
        "market_update": re.compile(r"(market\s*(update|report|analysis|crash|prediction|forecast|outlook|wrap)|property\s*market|housing\s*market)", re.I),
        "suburb_review": re.compile(r"(suburb\s*(review|profile|guide|analysis|tour|report)|where\s*to\s*(buy|invest|live)|best\s*suburb|worst\s*suburb)", re.I),
        "buying_guide": re.compile(r"(how\s*to\s*buy|first\s*home\s*buyer|buying\s*(tips|guide|advice)|things\s*to\s*know\s*before\s*buying|step.*buy)", re.I),
        "selling_guide": re.compile(r"(how\s*to\s*sell|selling\s*(tips|guide|advice|strategy)|getting\s*the\s*best\s*price|prepare.*sell)", re.I),
        "investment": re.compile(r"(invest(ing|ment)?\s*(property|strateg|portfolio|tip)|rental\s*yield|cash\s*flow|passive\s*income|buy\s*to\s*let|wealth\s*through\s*property)", re.I),
        "walkthrough": re.compile(r"(walk\s*through|property\s*tour|walkthrough|inside\s*look|luxury\s*home|dream\s*home|house\s*tour|home\s*tour)", re.I),
        "crash_fear": re.compile(r"(crash|bubble|collapse|crisis|warning|danger|avoid|mistake|don.?t\s*buy|overpriced|overvalued)", re.I),
        "finance": re.compile(r"(mortgage|interest\s*rate|loan|refinance|stamp\s*duty|deposit|equity|borrowing|serviceability|repayment)", re.I),
        "data_analysis": re.compile(r"(data|numbers|statistics|median|chart|graph|analysis|report\s*card|scorecard)", re.I),
        "agent_tips": re.compile(r"(real\s*estate\s*agent|agent\s*(tips|advice|secrets|commission|tricks|lies)|choosing\s*an?\s*agent|agent.*wrong)", re.I),
        "renovation": re.compile(r"(renovat|flip|reno\b|transform|before\s*and\s*after|makeover|fix.*sell)", re.I),
        "auction": re.compile(r"(auction|bidding|bid|hammer|under\s*the\s*hammer|live\s*auction)", re.I),
        "lifestyle": re.compile(r"(living\s*in|move\s*to|relocat|lifestyle|cost\s*of\s*living|pros?\s*and\s*cons|why\s*i\s*moved)", re.I),
        "tax_finance": re.compile(r"(tax\s*(deduct|benefit|tip|strateg)|negative\s*gearing|capital\s*gains|depreciation|smsf\s*property)", re.I),
    }

    topic_stats = {k: {"count": 0, "total_views": 0, "videos": []} for k in TOPIC_PATTERNS}
    unclassified = []

    for v in videos:
        title = v.get("title", "")
        classified = False
        for name, pattern in TOPIC_PATTERNS.items():
            if pattern.search(title):
                topic_stats[name]["count"] += 1
                topic_stats[name]["total_views"] += v.get("views", 0)
                topic_stats[name]["videos"].append(v)
                classified = True
                break
        if not classified:
            unclassified.append(v)

    # Averages
    for stats in topic_stats.values():
        if stats["count"] > 0:
            stats["avg_views"] = stats["total_views"] // stats["count"]
            stats["videos"].sort(key=lambda v: -v.get("views", 0))

    ranked = sorted(topic_stats.items(), key=lambda x: -x[1].get("avg_views", 0))

    print(f"\n  Topic Performance (ranked by avg views):")
    print(f"  {'Topic':<20} {'Videos':>7} {'Avg Views':>12} {'Total Views':>14} {'Best Performer'}")
    print(f"  {'-'*110}")
    for name, stats in ranked:
        if stats["count"] == 0:
            continue
        best = stats["videos"][0].get("title", "")[:45]
        best_views = stats["videos"][0].get("views", 0)
        print(f"  {name:<20} {stats['count']:>7} {stats['avg_views']:>12,} {stats['total_views']:>14,} {best} ({best_views:,})")

    # Top title keywords from high-view videos
    print(f"\n  Title Keywords (from top 100 videos by views):")
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "is", "it",
                 "and", "or", "but", "with", "from", "by", "as", "this", "that",
                 "are", "was", "be", "have", "has", "do", "does", "will", "would",
                 "i", "you", "he", "she", "we", "they", "my", "your", "our",
                 "not", "no", "so", "if", "up", "out", "just", "about", "how",
                 "what", "why", "when", "where", "which", "who", "all", "can",
                 "|", "-", "–", "—", "don't", "it's", "i'm"}
    word_views = defaultdict(lambda: {"count": 0, "total_views": 0})

    for v in videos[:100]:
        words = set(re.findall(r'[a-z]+', v.get("title", "").lower()))
        for w in words:
            if w not in stopwords and len(w) > 2:
                word_views[w]["count"] += 1
                word_views[w]["total_views"] += v.get("views", 0)

    # Rank by total views associated with that word
    word_ranked = sorted(word_views.items(), key=lambda x: -x[1]["total_views"])
    for word, data in word_ranked[:30]:
        avg = data["total_views"] // data["count"]
        print(f"    {data['count']:>3}x  {avg:>10,} avg views  {word}")

    # Channels with highest avg views per video (the real gold — consistent performers)
    print(f"\n  Best Channels by Avg Views (min 3 videos):")
    channels = list(sm_db["youtube_competitor_channels"].find())
    channel_avgs = []
    for ch in channels:
        vids = ch.get("top_videos", [])
        if len(vids) >= 3:
            avg = sum(v.get("views", 0) for v in vids) // len(vids)
            channel_avgs.append({
                "name": ch["channel_name"],
                "subs": ch.get("subscribers", 0),
                "avg_views": avg,
                "video_count": len(vids),
                "top_title": vids[0].get("title", "") if vids else "",
            })

    channel_avgs.sort(key=lambda c: -c["avg_views"])
    print(f"  {'Channel':<35} {'Subs':>10} {'Avg Views':>12} {'Vids':>5} {'Top Video'}")
    print(f"  {'-'*110}")
    for ch in channel_avgs[:20]:
        print(f"  {ch['name']:<35} {ch['subs']:>10,} {ch['avg_views']:>12,} {ch['video_count']:>5} {ch['top_title'][:40]}")

    # Generate YouTube seed queries from top-performing video titles
    print(f"\n  Suggested seeds from top competitor videos (for --youtube-deep):")
    seeds = set()
    for v in videos[:200]:
        title = v.get("title", "").lower()
        title = re.sub(r'[|/\\].*', '', title)
        title = re.sub(r'\(.*?\)', '', title)
        title = re.sub(r'\[.*?\]', '', title)
        title = re.sub(r'#\w+', '', title)
        title = re.sub(r'\b\d{4}\b', '', title)  # Strip years
        title = title.strip(' -–—:!?,.')
        if 5 <= len(title) <= 80:
            seeds.add(title)

    for s in sorted(seeds)[:30]:
        print(f"    • {s}")
    print(f"\n  Total potential new seeds: {len(seeds)}")

    return topic_stats


def _batched_bulk_write(collection, ops, label="", batch_size=10, delay=0.5):
    """Write in small batches for Cosmos DB."""
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


def main():
    parser = argparse.ArgumentParser(description="YouTube Competitor Intelligence")
    parser.add_argument("--discover", action="store_true", help="Find channels + pull top videos")
    parser.add_argument("--analyse", action="store_true", help="Analyse existing data only")
    parser.add_argument("--dry-run", action="store_true", help="Collect but don't save")
    args = parser.parse_args()

    if not YT_API_KEY:
        print("ERROR: YOUTUBE_API_KEY not set in .env")
        raise SystemExit(1)

    client = MongoClient(COSMOS_URI)
    sm_db = client["system_monitor"]

    print(f"YouTube Competitor Intelligence — {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}")

    if args.analyse:
        analyse_topics(sm_db)
    else:
        discover_channels(sm_db, dry_run=args.dry_run)
        analyse_topics(sm_db)

    print(f"\n  Total API quota used: ~{quota_used} units (daily limit: 10,000)")
    client.close()


if __name__ == "__main__":
    main()

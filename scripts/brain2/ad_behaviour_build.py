#!/usr/bin/env python3
"""
ad_behaviour_build.py — Brain 2 Layer 4a: granular per-session behaviour store.

For every ad-attributable session, reconstruct exactly what the visitor consumed
on the site — which articles they read and HOW FAR they scrolled, which feed
sections they hit, which properties they viewed, which cards they saw (with our
editorial classification), rage-clicks, dwell time — and whether they converted.

All from the PostHog event stream in bulk (no per-session API calls; PostHog's own
AI summaries reject personal-API-key access, so Layer 4b generates our own with
Opus from this data instead).

Writes:
  system_monitor.ad_session_behaviour  — one doc per (ad_id, session)
  system_monitor.ad_content_affinity   — per-ad rollup: what this ad's traffic reads

Usage: python3 scripts/brain2/ad_behaviour_build.py [--days 220]
"""
import os, sys, json, argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts/brain2")
from shared.db import get_client  # noqa: E402
from organic_journey_build import funnel_regime  # noqa: E402  (single source of truth for the regime cutover)

PID = os.environ["POSTHOG_PROJECT_ID"]
KEY = os.environ["POSTHOG_PERSONAL_API_KEY"]
import urllib.request

CONV_EVENTS = ["analyse_home_submit_start", "analyse_home_submit_success",
               "analyse_home_address_submit", "analyse_v3_address_selected",
               "analyse_v2_address_selected", "analyse_v3_jobs_queued"]


def hog(sql):
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    req = urllib.request.Request(
        f"https://us.posthog.com/api/projects/{PID}/query/", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["results"]


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=220)
    args = ap.parse_args()
    since = f"now() - INTERVAL {args.days} DAY"
    db = get_client()["system_monitor"]
    our_ids = set(db.ad_profiles.distinct("_id"))

    # session -> ad (exact utm_content match)
    rows = hog(f"""SELECT properties.$session_id, properties.utm_content FROM events
        WHERE timestamp > {since} AND properties.$session_id IS NOT NULL
          AND match(properties.utm_content, '^[0-9]+$') LIMIT 1000000""")
    sess_ad = {}
    for sid, c in rows:
        if sid and c in our_ids and sid not in sess_ad:
            sess_ad[sid] = c
    if not sess_ad:
        print("no attributable sessions"); return
    print(f"{len(sess_ad)} attributable sessions")

    # bulk event stream with all granular props
    sid_list = ",".join("'" + s.replace("'", "") + "'" for s in sess_ad)
    events = ("$pageview,time_on_page,scroll_depth,article_view,v3_section_marker_view,"
              "property_view,v3_card_impression,v3_card_click,address_search,$rageclick,"
              + ",".join(CONV_EVENTS))
    ev_in = ",".join("'" + e + "'" for e in events.split(","))
    ev = hog(f"""SELECT properties.$session_id, timestamp, event, properties.$pathname,
        properties.duration, properties.max_depth, properties.article_id,
        properties.article_title, properties.article_category, properties.marker_id,
        properties.property_id, properties.classification, properties.card_type,
        properties.suburb, properties.distinct_id, properties.address
        FROM events WHERE properties.$session_id IN ({sid_list})
          AND event IN ({ev_in}) AND timestamp > {since}
        ORDER BY properties.$session_id, timestamp LIMIT 5000000""")

    S = defaultdict(lambda: {
        "pages": [], "articles": {}, "sections": set(), "properties": {},
        "cards": [], "searches": 0, "rageclicks": 0, "dwell_total": 0.0,
        "converted": False, "conv_events": set(), "person": None, "timeline": []})
    for (sid, ts, event, path, dur, depth, art_id, art_title, art_cat, marker,
         prop_id, classif, card_type, suburb, person, address) in ev:
        s = S[sid]
        if person and not s["person"]:
            s["person"] = person
        # permanent timestamped timeline entry (compact — non-null fields only).
        # This is the raw time-series that survives PostHog's ~30-90d retention.
        te = {"t": ts, "e": event}
        for k, v in (("path", path), ("property_id", prop_id), ("address", address),
                     ("max_depth", depth), ("dur", dur), ("article_id", art_id),
                     ("marker", marker), ("classification", classif), ("card_type", card_type)):
            if v is not None and v != "":
                te[k] = v
        s["timeline"].append(te)
        if event == "$pageview":
            s["pages"].append(path or "?")
        elif event == "time_on_page":
            d = num(dur)
            if d:
                s["dwell_total"] += d
        elif event == "scroll_depth":
            d = num(depth)
            key = art_id or path or "?"
            if d is not None:
                s["articles"].setdefault(key, {"title": art_title, "category": art_cat, "max_scroll": 0})
                s["articles"][key]["max_scroll"] = max(s["articles"][key]["max_scroll"], d)
        elif event == "article_view":
            key = art_id or path
            s["articles"].setdefault(key, {"title": art_title, "category": art_cat, "max_scroll": 0})
        elif event == "v3_section_marker_view":
            if marker:
                s["sections"].add(marker)
        elif event == "property_view":
            if prop_id:
                s["properties"][prop_id] = suburb
        elif event == "v3_card_impression":
            if prop_id:
                s["cards"].append({"property_id": prop_id, "classification": classif, "suburb": suburb})
        elif event == "address_search":
            s["searches"] += 1
        elif event == "$rageclick":
            s["rageclicks"] += 1
        elif event in CONV_EVENTS:
            s["converted"] = True
            s["conv_events"].add(event)

    # authoritative session metrics from the native `sessions` table (real
    # duration/bounce/entry-exit/channel) — beats the event-derived dwell approx.
    smeta = {}
    sm = hog(f"""SELECT session_id, $session_duration, $is_bounce, $entry_pathname,
        $exit_pathname, $channel_type, $pageview_count
        FROM sessions
        WHERE session_id IN ({sid_list}) AND $start_timestamp > {since}
        LIMIT 1000000""")
    for row in sm:
        smeta[row[0]] = {
            "session_duration_s": row[1], "is_bounce": bool(row[2]),
            "entry_path": row[3], "exit_path": row[4],
            "channel_type": row[5], "pageview_count": row[6],
        }

    # replay metadata from session_replay_events (activity_score, real click/
    # keypress/active-time). Survives longer than the rrweb snapshot blobs, so
    # this is the reliably-available richer engagement signal.
    replaymeta = {}
    try:
        rm = hog(f"""SELECT session_id, surfacing_score, click_count, keypress_count,
            mouse_activity_count, active_milliseconds, console_error_count
            FROM session_replay_events
            WHERE session_id IN ({sid_list}) LIMIT 1000000""")
        for row in rm:
            replaymeta[row[0]] = {
                "surfacing_score": row[1], "click_count": row[2],
                "keypress_count": row[3], "mouse_activity_count": row[4],
                "active_seconds": round((row[5] or 0) / 1000, 1),
                "console_errors": row[6],
            }
    except Exception as e:
        print(f"replay metadata pull skipped: {str(e)[:100]}")

    # write per-session docs + accumulate per-ad affinity
    now = datetime.now(timezone.utc).isoformat()
    beh = db.ad_session_behaviour
    beh.create_index("ad_id")
    beh.delete_many({})  # rebuilt each run
    affinity = defaultdict(lambda: {
        "sessions": 0, "converters": 0, "articles": Counter(), "article_titles": {},
        "scroll_sum": defaultdict(float), "scroll_n": defaultdict(int),
        "sections": Counter(), "properties": Counter(), "classifications": Counter(),
        "dwell_sum": 0.0, "rageclick_sessions": 0, "searches": 0,
        "dur_sum": 0.0, "dur_n": 0, "bounces": 0})
    batch = []
    for sid, s in S.items():
        aid = sess_ad[sid]
        arts = [{"key": k, "title": v["title"], "category": v["category"],
                 "max_scroll_pct": v["max_scroll"]} for k, v in s["articles"].items()]
        doc = {
            "ad_id": aid, "session_id": sid, "distinct_id": s["person"],
            "n_pages": len(s["pages"]), "pages": s["pages"][:25],
            "articles_read": arts,
            "sections_viewed": sorted(s["sections"]),
            "properties_viewed": [{"property_id": k, "suburb": v} for k, v in s["properties"].items()],
            "cards_seen": s["cards"][:40],
            "n_searches": s["searches"], "rageclicks": s["rageclicks"],
            "dwell_seconds": round(s["dwell_total"], 1),  # event-derived (active reading)
            "session": smeta.get(sid, {}),  # authoritative: duration/bounce/entry-exit/channel
            "replay": replaymeta.get(sid, {}),  # activity_score/clicks/active-time from replay
            "timeline": s["timeline"][:3000],  # full timestamped event sequence (permanent)
            "funnel_regime": funnel_regime(s["timeline"][0]["t"] if s["timeline"] else None),
            "converted": s["converted"], "conversion_events": sorted(s["conv_events"]),
            "computed_at": now,
        }
        batch.append(doc)
        af = affinity[aid]
        af["sessions"] += 1
        af["converters"] += 1 if s["converted"] else 0
        af["dwell_sum"] += s["dwell_total"]
        af["searches"] += s["searches"]
        af["rageclick_sessions"] += 1 if s["rageclicks"] else 0
        _m = smeta.get(sid)
        if _m:
            if _m.get("session_duration_s") is not None:
                af["dur_sum"] += _m["session_duration_s"]; af["dur_n"] += 1
            if _m.get("is_bounce"):
                af["bounces"] += 1
        for k, v in s["articles"].items():
            af["articles"][k] += 1
            if v["title"]:
                af["article_titles"][k] = v["title"]
            if v["max_scroll"]:
                af["scroll_sum"][k] += v["max_scroll"]; af["scroll_n"][k] += 1
        for sec in s["sections"]:
            af["sections"][sec] += 1
        for k in s["properties"]:
            af["properties"][k] += 1
        for c in s["cards"]:
            if c.get("classification"):
                af["classifications"][c["classification"]] += 1
    if batch:
        beh.insert_many(batch)

    aff = db.ad_content_affinity
    aff.delete_many({})
    for aid, af in affinity.items():
        prof = db.ad_profiles.find_one({"_id": aid}, {"name": 1})
        top_articles = []
        for k, n in af["articles"].most_common(8):
            avg = round(af["scroll_sum"][k] / af["scroll_n"][k], 0) if af["scroll_n"][k] else None
            top_articles.append({"article": af["article_titles"].get(k, k), "sessions": n,
                                 "avg_max_scroll_pct": avg})
        aff.insert_one({
            "_id": aid, "ad_id": aid, "ad_name": (prof or {}).get("name", ""),
            "sessions": af["sessions"], "converters": af["converters"],
            "avg_dwell_seconds": round(af["dwell_sum"] / af["sessions"], 1) if af["sessions"] else 0,
            "avg_session_duration_s": round(af["dur_sum"] / af["dur_n"], 1) if af["dur_n"] else None,
            "bounce_rate_pct": round(100 * af["bounces"] / af["sessions"], 1) if af["sessions"] else None,
            "rageclick_session_pct": round(100 * af["rageclick_sessions"] / af["sessions"], 1) if af["sessions"] else 0,
            "total_searches": af["searches"],
            "top_articles_read": top_articles,
            "top_sections": [{"marker": m, "n": n} for m, n in af["sections"].most_common(8)],
            "top_properties": [{"property_id": p, "n": n} for p, n in af["properties"].most_common(8)],
            "card_classifications_seen": dict(af["classifications"]),
            "computed_at": now,
        })

    print(f"wrote {len(batch)} session behaviour docs, {len(affinity)} ad affinity docs")
    # peek: top converter's content affinity
    d = aff.find_one({"converters": {"$gt": 0}}, sort=[("converters", -1)])
    if d:
        print(f"\nTop converter: {d['ad_name'][:50]}")
        print(f"  {d['converters']} conv / {d['sessions']} sess | avg dwell {d['avg_dwell_seconds']}s | "
              f"rageclick sessions {d['rageclick_session_pct']}%")
        print(f"  top articles read: {[(a['article'][:40], a['avg_max_scroll_pct']) for a in d['top_articles_read'][:4]]}")
        print(f"  top sections: {[s['marker'] for s in d['top_sections'][:6]]}")


if __name__ == "__main__":
    main()

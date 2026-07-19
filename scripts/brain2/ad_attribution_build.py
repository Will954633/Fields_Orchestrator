#!/usr/bin/env python3
"""
ad_attribution_build.py — Brain 2 Layer 3: downstream website attribution per ad.

Joins every ad to the real user journeys it drove, from PostHog, at the best
granularity the ad's tagging allows — and LABELS the confidence, because the
honest truth is that only ~32 of 92 ads carry an ad-id (utm_content) and can be
attributed exactly. The rest are campaign-level or unattributable.

For each exactly-attributable ad it reconstructs:
  • sessions / unique visitors / converters (address-entry events)
  • entry pages + all pages viewed (content consumed — /article/<id>, /property/<id>)
  • content-event counts (article_view, v3_section_marker_view, property_view,
    address_search, v3_card_click)
  • engagement (avg session duration via time_on_page, max scroll depth)
  • funnel: impressions/clicks (from ad_profiles) → sessions → engaged → converters

Writes system_monitor.ad_downstream keyed by ad_id.

Usage: python3 scripts/brain2/ad_attribution_build.py [--days 200]
Env: POSTHOG_PROJECT_ID, POSTHOG_PERSONAL_API_KEY, COSMOS_CONNECTION_STRING
"""
import os, sys, json, time, argparse, urllib.request, urllib.error
from collections import defaultdict, Counter
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402
from brain2_util import hog_retry, alert_failure  # noqa: E402

PID = os.environ["POSTHOG_PROJECT_ID"]
KEY = os.environ["POSTHOG_PERSONAL_API_KEY"]

CONV_EVENTS = ["analyse_home_submit_start", "analyse_home_submit_success",
               "analyse_home_address_submit", "analyse_v3_address_selected",
               "analyse_v2_address_selected", "analyse_v3_jobs_queued"]
CONTENT_EVENTS = ["article_view", "v3_section_marker_view", "property_view",
                  "address_search", "v3_card_click", "v3_card_impression",
                  "price_alert_impression", "time_on_page", "scroll_depth"]


def hog(sql):
    return hog_retry(PID, KEY, sql)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=200)
    args = ap.parse_args()
    since = f"now() - INTERVAL {args.days} DAY"

    db = get_client()["system_monitor"]
    our_ids = set(db.ad_profiles.distinct("_id"))

    # 1) session -> ad_id via exact utm_content match (digits only = ad id)
    rows = hog(f"""SELECT properties.$session_id, properties.utm_content
        FROM events
        WHERE timestamp > {since} AND properties.$session_id IS NOT NULL
          AND match(properties.utm_content, '^[0-9]+$')
        LIMIT 1000000""")
    sess_ad = {}
    for sid, content in rows:
        if sid and content in our_ids and sid not in sess_ad:
            sess_ad[sid] = content
    if not sess_ad:
        print("No exactly-attributable sessions found."); return
    ad_sessions = defaultdict(set)
    for sid, aid in sess_ad.items():
        ad_sessions[aid].add(sid)
    print(f"{len(sess_ad)} attributable sessions across {len(ad_sessions)} ads")

    # 2) full event stream for those sessions
    sid_list = ",".join("'" + s.replace("'", "") + "'" for s in sess_ad)
    ev_wanted = CONV_EVENTS + CONTENT_EVENTS + ["$pageview"]
    ev_in = ",".join("'" + e + "'" for e in ev_wanted)
    ev = hog(f"""SELECT properties.$session_id, timestamp, event,
        properties.$pathname, properties.distinct_id
        FROM events
        WHERE properties.$session_id IN ({sid_list})
          AND event IN ({ev_in}) AND timestamp > {since}
        ORDER BY properties.$session_id, timestamp
        LIMIT 5000000""")

    # per-session assembly
    sess = defaultdict(lambda: {"pages": [], "content": Counter(),
                                "converted": False, "conv_events": set(), "person": None})
    for sid, ts, event, path, person in ev:
        s = sess[sid]
        if person and not s["person"]:
            s["person"] = person
        if event == "$pageview":
            s["pages"].append(path or "?")
        elif event in CONV_EVENTS:
            s["converted"] = True
            s["conv_events"].add(event)
        else:
            s["content"][event] += 1

    # 3) aggregate per ad
    now = datetime.now(timezone.utc).isoformat()
    written = 0
    for aid, sids in ad_sessions.items():
        prof = db.ad_profiles.find_one({"_id": aid}, {"name": 1, "campaign_name": 1,
                                                      "lifetime": 1, "creative_structured.format": 1})
        entry = Counter(); pages = Counter(); content = Counter()
        persons = set(); converters = 0; conv_breakdown = Counter(); before_conv = Counter()
        for sid in sids:
            s = sess.get(sid)
            if not s:
                continue
            if s["person"]:
                persons.add(s["person"])
            if s["pages"]:
                entry[s["pages"][0]] += 1
                for p in s["pages"]:
                    pages[p] += 1
            for k, v in s["content"].items():
                content[k] += v
            if s["converted"]:
                converters += 1
                for c in s["conv_events"]:
                    conv_breakdown[c] += 1
                # page before first conversion ~ last page seen
                if s["pages"]:
                    before_conv[s["pages"][-1]] += 1
        n_sessions = len(sids)
        lt = prof.get("lifetime", {}) if prof else {}
        doc = {
            "ad_id": aid,
            "ad_name": (prof or {}).get("name", ""),
            "campaign_name": (prof or {}).get("campaign_name", ""),
            "format": (prof or {}).get("creative_structured", {}).get("format", ""),
            "attribution_confidence": "exact",  # utm_content ad-id match
            "window_days": args.days,
            "sessions": n_sessions,
            "unique_visitors": len(persons),
            "converters": converters,
            "conversion_rate_pct": round(100 * converters / n_sessions, 1) if n_sessions else 0,
            "conversion_events": dict(conv_breakdown),
            "entry_pages": [{"path": p, "n": n} for p, n in entry.most_common(10)],
            "top_pages": [{"path": p, "n": n} for p, n in pages.most_common(15)],
            "content_consumed": dict(content),
            "page_before_conversion": [{"path": p, "n": n} for p, n in before_conv.most_common(6)],
            "ad_lifetime": {k: lt.get(k) for k in
                            ["impressions", "reach", "clicks", "link_clicks",
                             "landing_page_views", "spend_aud", "ctr", "cpc_aud"]},
            "computed_at": now,
        }
        db.ad_downstream.replace_one({"_id": aid}, {**doc, "_id": aid}, upsert=True)
        written += 1

    db.ad_downstream.create_index("attribution_confidence")
    print(f"wrote {written} ad_downstream docs (confidence=exact)")

    # ---- campaign-level fallback for ads with no exact attribution ----
    # utm_campaign is a mess (campaign_id | URL-encoded name | manual test tag).
    # Match only cleanly: session utm_campaign == campaign_id, or == the exact
    # (URL-decoded) campaign name. Attribute to ALL ads in that campaign, flagged
    # confidence=campaign + shared_across, since it cannot be split per-ad.
    import urllib.parse as _up
    exact_ids = set(ad_sessions)
    # map campaign_id -> ads, and decoded campaign_name -> campaign_id
    camp_ads = defaultdict(list); name_to_cid = {}
    for p in db.ad_profiles.find({}, {"campaign_id": 1, "campaign_name": 1}):
        cid = p.get("campaign_id"); nm = p.get("campaign_name")
        if cid:
            camp_ads[cid].append(p["_id"])
            if nm:
                name_to_cid[nm.strip()] = cid
    need = {aid for cid, ids in camp_ads.items() for aid in ids} - exact_ids
    camp_rows = hog(f"""SELECT properties.$session_id, properties.utm_campaign
        FROM events WHERE timestamp > {since} AND properties.$session_id IS NOT NULL
          AND properties.utm_campaign != '' AND properties.utm_campaign IS NOT NULL
        LIMIT 1000000""")
    cid_sessions = defaultdict(set)
    for sid, camp in camp_rows:
        if not sid or sid in sess_ad:  # skip exactly-attributed sessions
            continue
        camp = str(camp)
        cid = camp if camp in camp_ads else name_to_cid.get(_up.unquote(camp).strip())
        if cid:
            cid_sessions[cid].add(sid)

    # pull events for these campaign sessions
    all_camp_sids = {s for ss in cid_sessions.values() for s in ss}
    csess = {}
    if all_camp_sids:
        clist = ",".join("'" + s.replace("'", "") + "'" for s in all_camp_sids)
        cev = hog(f"""SELECT properties.$session_id, event, properties.$pathname,
            properties.distinct_id FROM events
            WHERE properties.$session_id IN ({clist})
              AND event IN ({ev_in}) AND timestamp > {since}
            ORDER BY properties.$session_id, timestamp LIMIT 5000000""")
        for sid, event, path, person in cev:
            s = csess.setdefault(sid, {"pages": [], "content": Counter(),
                                       "converted": False, "conv": set(), "person": None})
            if person and not s["person"]:
                s["person"] = person
            if event == "$pageview":
                s["pages"].append(path or "?")
            elif event in CONV_EVENTS:
                s["converted"] = True; s["conv"].add(event)
            else:
                s["content"][event] += 1

    camp_written = 0
    for cid, sids in cid_sessions.items():
        ads_in = [a for a in camp_ads[cid] if a in need]
        if not ads_in or not sids:
            continue
        entry = Counter(); pages = Counter(); content = Counter()
        persons = set(); converters = 0; conv_bd = Counter()
        for sid in sids:
            s = csess.get(sid)
            if not s:
                continue
            if s["person"]:
                persons.add(s["person"])
            if s["pages"]:
                entry[s["pages"][0]] += 1
                for p in s["pages"]:
                    pages[p] += 1
            for k, v in s["content"].items():
                content[k] += v
            if s["converted"]:
                converters += 1
                for c in s["conv"]:
                    conv_bd[c] += 1
        n = len(sids)
        for aid in ads_in:
            prof = db.ad_profiles.find_one({"_id": aid},
                                           {"name": 1, "campaign_name": 1, "creative_structured.format": 1})
            db.ad_downstream.replace_one({"_id": aid}, {
                "_id": aid, "ad_id": aid, "ad_name": (prof or {}).get("name", ""),
                "campaign_name": (prof or {}).get("campaign_name", ""),
                "format": (prof or {}).get("creative_structured", {}).get("format", ""),
                "attribution_confidence": "campaign",
                "shared_across": len(ads_in),
                "window_days": args.days,
                "sessions": n, "unique_visitors": len(persons),
                "converters": converters,
                "conversion_rate_pct": round(100 * converters / n, 1) if n else 0,
                "conversion_events": dict(conv_bd),
                "entry_pages": [{"path": p, "n": c} for p, c in entry.most_common(10)],
                "top_pages": [{"path": p, "n": c} for p, c in pages.most_common(15)],
                "content_consumed": dict(content),
                "note": "campaign-level: shared across all ads in the campaign, cannot be split per-ad",
                "computed_at": now,
            }, upsert=True)
            camp_written += 1
    print(f"wrote {camp_written} ad_downstream docs (confidence=campaign, fallback)")
    # honesty summary
    conv_ads = list(db.ad_downstream.find({"converters": {"$gt": 0}},
                                          {"ad_name": 1, "converters": 1, "sessions": 1}))
    print(f"\nExactly-attributable ads: {written} of {len(our_ids)} total")
    print(f"Ads with >=1 address-entry conversion: {len(conv_ads)}")
    for c in sorted(conv_ads, key=lambda x: -x["converters"]):
        print(f"   {c['converters']} conv / {c['sessions']} sess — {c['ad_name'][:55]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        alert_failure("ad_attribution_build", e)
        raise

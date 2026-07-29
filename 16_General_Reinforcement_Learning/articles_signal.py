#!/usr/bin/env python3
"""
articles_signal.py — Articles domain: the SEO/CONTENT SENSOR — which articles earn engagement + convert.

The SENSE half of the Articles sub-workflow — same pattern as seo_signal.py / ads_signal.py, applied to
the self-hosted article store. Read-only over `content_articles` (the store), `organic_landing_affinity`
(sessions / engaged / converters per entry page) and `seo_landing_performance` (GSC impressions / clicks /
position); writes `system_monitor.rl_articles_signal` (+ history). The STEER half is the Claude Articles
cycle that reads this + the shared reward ledger to decide topics / cadence / hooks.

Per article (joined slug↔path) it ties who READS it (organic affinity) to how it's FOUND (GSC) and flags:
  - CONVERTING — converters>0: topics/formats that actually produce identified sellers → make more of.
  - HIGH-IMPR / LOW-CTR — impressions high but CTR below what the rank should earn: title/hook opportunity.
  - DEAD — published article with ~0 sessions and ~0 impressions over the window: dead topic.

Usage: python3 articles_signal.py [--dry-run]
"""
import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_articles_signal"

# Core suburbs we cover — tag/title match rolls an article up to a suburb (else "general").
SUBURBS = ["burleigh waters", "burleigh heads", "varsity lakes", "robina", "mermaid waters",
           "mermaid beach", "miami", "palm beach", "broadbeach", "surfers paradise",
           "mudgeeraba", "reedy creek", "nobby beach", "burleigh"]


# Rough CTR-by-position benchmark (organic) — spot articles under-earning their rank (mirrors seo_signal).
def expected_ctr(pos):
    if pos <= 1: return 0.28
    if pos <= 2: return 0.15
    if pos <= 3: return 0.10
    if pos <= 5: return 0.06
    if pos <= 10: return 0.025
    if pos <= 20: return 0.008
    return 0.003


def _slug_of(path):
    """Extract the article identifier segment from /article(s)/<slug> (domain-stripped, trailing-slash-safe)."""
    p = re.sub(r"^https?://[^/]+", "", path or "").strip("/")
    parts = p.split("/")
    if len(parts) >= 2 and parts[0] in ("article", "articles"):
        return parts[1]
    return None


def _suburb_topic(art):
    tags = [str(t).lower() for t in (art.get("tags") or [])]
    hay = " ".join(tags) + " " + str(art.get("title") or "").lower()
    suburb = next((s.title() for s in SUBURBS if s in hay), "General")
    topic = (art.get("page_type") or (tags[0] if tags else None) or "uncategorised")
    return suburb, str(topic)


def build(dry_run=False):
    sm = get_client()["system_monitor"]

    # --- article store + resolver (slug / _id / ghost_id all map to the same doc) ---
    articles = {}          # key(article _id str) -> record
    resolve = {}           # any path-segment identifier -> article _id str
    for a in sm["content_articles"].find({}, {"html": 0, "content": 0}):
        aid = str(a["_id"])
        suburb, topic = _suburb_topic(a)
        articles[aid] = {
            "id": aid, "title": (a.get("title") or "")[:80], "slug": a.get("slug"),
            "status": a.get("status"), "suburb": suburb, "topic": topic,
            "published_at": a.get("published_at"),
            "sessions": 0, "engaged": 0, "converters": 0,
            "clicks": 0, "impressions": 0, "pos_wsum": 0.0,
            "top_query": None, "top_query_impr": 0, "paths": set(),
        }
        for key in (a.get("slug"), a.get("ghost_id"), aid):
            if key:
                resolve[str(key)] = aid

    # --- who READS it: organic affinity per article entry page ---
    for d in sm["organic_landing_affinity"].find({"entry_path": {"$regex": r"^/articles?/"}}):
        aid = resolve.get(_slug_of(d.get("entry_path")))
        if not aid:
            continue
        r = articles[aid]
        r["sessions"] += int(d.get("sessions") or 0)
        r["engaged"] += int(d.get("engaged") or 0)
        r["converters"] += int(d.get("converters") or 0)
        r["paths"].add(d.get("entry_path"))

    # --- how it's FOUND: GSC per-query rows aggregated up to the article ---
    for d in sm["seo_landing_performance"].find({"page": {"$regex": "/articles?/"}}):
        aid = resolve.get(_slug_of(d.get("page")))
        if not aid:
            continue
        r = articles[aid]
        impr = int(d.get("impressions") or 0)
        r["clicks"] += int(d.get("clicks") or 0)
        r["impressions"] += impr
        r["pos_wsum"] += float(d.get("position") or 0) * impr
        if impr > r["top_query_impr"]:
            r["top_query_impr"] = impr
            r["top_query"] = d.get("query")

    # --- rows: every published article (so DEAD is visible) + any article with traffic ---
    rows = []
    for r in articles.values():
        has_traffic = r["sessions"] > 0 or r["impressions"] > 0
        if r["status"] != "published" and not has_traffic:
            continue
        impr = r["impressions"]
        ctr = (r["clicks"] / impr) if impr else 0.0
        pos = (r["pos_wsum"] / impr) if impr else None
        exp = expected_ctr(pos or 99)
        flags = []
        if r["converters"] > 0:
            flags.append("converting")
        if impr >= 50 and ctr < exp * 0.6:
            flags.append("high_impr_low_ctr")
        if r["status"] == "published" and r["sessions"] == 0 and impr == 0:
            flags.append("dead")
        rows.append({
            "id": r["id"], "title": r["title"], "slug": r["slug"], "status": r["status"],
            "suburb": r["suburb"], "topic": r["topic"],
            "sessions": r["sessions"], "engaged": r["engaged"], "converters": r["converters"],
            "impressions": impr, "clicks": r["clicks"],
            "ctr": round(ctr, 4), "expected_ctr": exp,
            "avg_position": round(pos, 1) if pos else None,
            "top_query": r["top_query"], "flags": flags,
        })

    # rank: converting first, then by impressions (reach), then sessions
    rows.sort(key=lambda r: (-(r["converters"] > 0), -r["impressions"], -r["sessions"]))

    # --- rollups ---
    def _rollup(keyf):
        agg = defaultdict(lambda: {"articles": 0, "sessions": 0, "converters": 0,
                                   "impressions": 0, "clicks": 0})
        for r in rows:
            g = agg[keyf(r)]
            g["articles"] += 1
            g["sessions"] += r["sessions"]; g["converters"] += r["converters"]
            g["impressions"] += r["impressions"]; g["clicks"] += r["clicks"]
        out = [{"key": k, **v} for k, v in agg.items()]
        out.sort(key=lambda g: (-g["converters"], -g["impressions"]))
        return out

    tot_sessions = sum(r["sessions"] for r in rows)
    tot_impr = sum(r["impressions"] for r in rows)
    tot_clicks = sum(r["clicks"] for r in rows)
    tot_conv = sum(r["converters"] for r in rows)

    led = sm["rl_reward_ledger"].find_one({"_id": "latest"}) or \
        sm["rl_reward_ledger"].find_one(sort=[("computed_at", -1)]) or {}

    snapshot = {
        "kind": "articles_signal_snapshot", "_id": "latest", "computed_at": NOW.isoformat(),
        "base_conversion_rate": led.get("base_conversion_rate"),
        "totals": {"articles": len(rows), "sessions": tot_sessions, "converters": tot_conv,
                   "impressions": tot_impr, "clicks": tot_clicks,
                   "ctr": round(tot_clicks / tot_impr, 4) if tot_impr else 0},
        "opportunities": {
            "converting": [r for r in rows if "converting" in r["flags"]][:15],
            "high_impr_low_ctr": [r for r in rows if "high_impr_low_ctr" in r["flags"]][:15],
            "dead": [r for r in rows if "dead" in r["flags"]][:25],
        },
        "top_articles": rows[:25],
        "by_topic": _rollup(lambda r: r["topic"]),
        "by_suburb": _rollup(lambda r: r["suburb"]),
        "note": ("SENSE half of the Articles sub-workflow. Ties article readership (organic affinity: "
                 "sessions/engaged/converters) to discovery (GSC impressions/clicks/position) so the "
                 "Articles cycle can steer topics/cadence/hooks. Read-only; feeds the reward ledger."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, snapshot, upsert=True)
        c.insert_one({k: v for k, v in {**snapshot, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return snapshot


def _summary(s):
    t = s["totals"]
    print(f"\n=== ARTICLES SIGNAL — {t['articles']} articles, {t['sessions']} sessions, "
          f"{t['converters']} converters, {t['impressions']} impr / {t['clicks']} clicks "
          f"(CTR {t['ctr']*100:.1f}%) ===")
    for label in ("converting", "high_impr_low_ctr", "dead"):
        opp = s["opportunities"][label]
        print(f"\n{label.upper()} ({len(opp)}):")
        for r in opp[:6]:
            print(f"  {r['title'][:44]:<44} sess={r['sessions']:>3} conv={r['converters']} "
                  f"impr={r['impressions']:>5} pos={r['avg_position'] or '-':>4} ctr={r['ctr']*100:>4.1f}%")
    print("\nBy suburb:")
    for g in s["by_suburb"][:6]:
        print(f"  {(g['key'] or '—')[:20]:<20} art={g['articles']:>3} sess={g['sessions']:>4} "
              f"conv={g['converters']} impr={g['impressions']:>5}")
    print("\nBy topic:")
    for g in s["by_topic"][:6]:
        print(f"  {(g['key'] or '—')[:28]:<28} art={g['articles']:>3} sess={g['sessions']:>4} "
              f"conv={g['converters']} impr={g['impressions']:>5}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("rl_articles_signal", cadence_hours=24, title="General RL — Articles (content) sensor") as beat:
            s = build(dry_run=False)
            _summary(s)
            beat.detail = (f"{s['totals']['articles']} articles; "
                           f"{len(s['opportunities']['converting'])} converting, "
                           f"{len(s['opportunities']['high_impr_low_ctr'])} low-ctr, "
                           f"{len(s['opportunities']['dead'])} dead")
    else:
        s = build(dry_run=args.dry_run)
        _summary(s)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()

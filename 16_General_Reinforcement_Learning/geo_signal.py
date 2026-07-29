#!/usr/bin/env python3
"""
geo_signal.py — General RL Phase 1 flagship: the AI-channel (GEO) SENSOR.

The SENSE half of the GEO/AI-channel feedback loop (00_SCOPING §2.2). Read-only over
`organic_journeys`; writes one collection `system_monitor.rl_geo_signal` (+ history).
The STEER/ACQUIRE half is the Claude analyst cycle (geo_cycle.sh) that reads this.

Classifies every session's engine from `ai_source` + `referring_domain`, then per engine:
  - sessions / users / conversions / conversion-rate (shrunk) vs the site base rate,
  - which pages the engine lands people on (GEO targets),
  - weekly trend (last ~8 ISO weeks) + DORMANT detection — a channel that used to send
    traffic and went dark is a top-priority "why did they stop / win them back" signal.

Usage:
  python3 geo_signal.py [--dry-run]
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_geo_signal"

# engine classification: (label, is_ai_chat).  ai_chat = generative engine (GEO target);
# ai_adjacent = search engine with AI surfaces (Bing powers Copilot; DDG has AI answers).
def classify(j):
    src = (j.get("ai_source") or "").strip().lower()
    ref = (j.get("referring_domain") or "").strip().lower()
    # explicit ai_source wins
    m = {"chatgpt": ("ChatGPT", True), "openai": ("ChatGPT", True),
         "copilot": ("Copilot", True), "gemini": ("Gemini", True), "bard": ("Gemini", True),
         "perplexity": ("Perplexity", True), "claude": ("Claude", True), "you.com": ("You", True)}
    for k, v in m.items():
        if k in src:
            return v
    # referrer-based
    if "chatgpt.com" in ref or "chat.openai" in ref:
        return ("ChatGPT", True)
    if "copilot.microsoft" in ref:
        return ("Copilot", True)
    if "perplexity" in ref:
        return ("Perplexity", True)
    if "gemini.google" in ref or "bard.google" in ref:
        return ("Gemini", True)
    if "claude.ai" in ref:
        return ("Claude", True)
    if "you.com" in ref:
        return ("You", True)
    if "bing.com" in ref:
        return ("Bing", False)          # ai_adjacent
    if "duckduckgo" in ref:
        return ("DuckDuckGo", False)    # ai_adjacent
    return (None, False)


def _isoweek(s):
    try:
        d = datetime.strptime(str(s)[:10], "%Y-%m-%d")
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    except Exception:
        return None


def _shrink(conv, n, base, strength=8.0):
    return (conv + strength * base) / (n + strength) if (n or strength) else base


def build(dry_run=False):
    sm = get_client()["system_monitor"]
    journeys = [j for j in sm["organic_journeys"].find({}) if not j.get("is_bot")]
    n_all = len(journeys)
    all_users = {j.get("distinct_id") for j in journeys}
    conv_users_all = {j.get("distinct_id") for j in journeys if j.get("converted")}
    base_rate = (len(conv_users_all) / len(all_users)) if all_users else 0.0

    weeks_all = sorted({w for j in journeys if (w := _isoweek(j.get("t_last")))})
    recent_weeks = weeks_all[-8:]
    last_week = weeks_all[-1] if weeks_all else None

    eng = defaultdict(lambda: {"sessions": 0, "users": set(), "conv_users": set(),
                               "is_ai_chat": False, "landing": defaultdict(int),
                               "weekly": defaultdict(int), "referrers": defaultdict(int)})
    ai_chat_users, ai_chat_conv = set(), set()
    for j in journeys:
        label, is_chat = classify(j)
        if not label:
            continue
        e = eng[label]
        e["is_ai_chat"] = is_chat
        e["sessions"] += 1
        did = j.get("distinct_id")
        e["users"].add(did)
        if did in conv_users_all:
            e["conv_users"].add(did)
        e["landing"][j.get("entry_path") or "?"] += 1
        w = _isoweek(j.get("t_last"))
        if w:
            e["weekly"][w] += 1
        if j.get("referring_domain"):
            e["referrers"][j["referring_domain"].lower()] += 1
        if is_chat:
            ai_chat_users.add(did)
            if did in conv_users_all:
                ai_chat_conv.add(did)

    engines = []
    for label, e in eng.items():
        uu, cc = len(e["users"]), len(e["conv_users"])
        weekly = {w: e["weekly"].get(w, 0) for w in recent_weeks}
        last_active = max((w for w, n in e["weekly"].items() if n), default=None)
        total_sessions = sum(e["weekly"].values())
        # DORMANT = had real traffic but silent for the last TWO week-buckets. Using two weeks
        # (not one) avoids false-flagging on the current, still-incomplete ISO week.
        last2 = [e["weekly"].get(w, 0) for w in recent_weeks[-2:]]
        dormant = bool(total_sessions >= 2 and sum(last2) == 0 and last_active)
        engines.append({
            "engine": label, "is_ai_chat": e["is_ai_chat"],
            "sessions": e["sessions"], "users": uu, "conversions": cc,
            "conv_rate": round(_shrink(cc, uu, base_rate), 4),
            "raw_conv_rate": round(cc / uu, 4) if uu else 0,
            "lift_vs_base": round(_shrink(cc, uu, base_rate) / base_rate, 2) if base_rate else None,
            "top_landing_pages": sorted(e["landing"].items(), key=lambda x: -x[1])[:5],
            "weekly_sessions": weekly, "last_active_week": last_active, "dormant": dormant,
            "top_referrers": sorted(e["referrers"].items(), key=lambda x: -x[1])[:3],
        })
    engines.sort(key=lambda x: (-x["is_ai_chat"], -x["conversions"], -x["users"]))

    ai_chat_total_users = len(ai_chat_users)
    snapshot = {
        "kind": "geo_signal_snapshot", "computed_at": NOW.isoformat(),
        "window_weeks": recent_weeks, "n_sessions": n_all, "n_users": len(all_users),
        "base_conversion_rate": round(base_rate, 4),
        "ai_chat_summary": {
            "users": ai_chat_total_users, "conversions": len(ai_chat_conv),
            "conv_rate": round(len(ai_chat_conv) / ai_chat_total_users, 4) if ai_chat_total_users else 0,
            "share_of_traffic": round(ai_chat_total_users / len(all_users), 4) if all_users else 0,
        },
        "engines": engines,
        "dormant_channels": [e["engine"] for e in engines if e["dormant"]],
        "note": ("SENSE half of the GEO loop. ai_chat = generative engines (GEO targets); "
                 "ai_adjacent (Bing/DuckDuckGo) = search w/ AI surfaces. Feeds geo_cycle.sh."),
    }

    if not dry_run:
        c = sm[COLL]
        c.insert_one(dict(snapshot))
        c.replace_one({"_id": "latest"}, {**snapshot, "_id": "latest"}, upsert=True)
    return snapshot


def _summary(s):
    a = s["ai_chat_summary"]
    print(f"\n=== GEO / AI-CHANNEL SIGNAL  ({s['window_weeks'][0] if s['window_weeks'] else '?'}"
          f" → {s['window_weeks'][-1] if s['window_weeks'] else '?'}) ===")
    print(f"AI-chat traffic: {a['users']} users ({a['share_of_traffic']*100:.1f}% of all), "
          f"{a['conversions']} conv (rate {a['conv_rate']:.3f}) vs base {s['base_conversion_rate']:.3f}")
    print(f"\n  {'engine':<13}{'chat':>5}{'users':>6}{'conv':>5}{'rate':>7}{'lift':>6}  recent weekly")
    for e in s["engines"]:
        wk = " ".join(str(v) for v in e["weekly_sessions"].values())
        flag = " ⚠DORMANT" if e["dormant"] else ""
        lift = f"{e['lift_vs_base']:.2f}" if e["lift_vs_base"] is not None else "-"
        print(f"  {e['engine']:<13}{'Y' if e['is_ai_chat'] else '·':>5}{e['users']:>6}"
              f"{e['conversions']:>5}{e['conv_rate']:>7.3f}{lift:>6}  [{wk}]{flag}")
    if s["dormant_channels"]:
        print(f"\n  ⚠ DORMANT (had traffic, none last week — win-back candidates): "
              f"{', '.join(s['dormant_channels'])}")
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
        with job_run("rl_geo_signal", cadence_hours=24,
                     title="General RL — GEO/AI-channel sensor") as beat:
            s = build(dry_run=False)
            _summary(s)
            beat.detail = (f"{s['ai_chat_summary']['users']} AI-chat users, "
                           f"{len(s['engines'])} engines, {len(s['dormant_channels'])} dormant")
            beat.metrics = {"ai_chat_users": s["ai_chat_summary"]["users"],
                            "engines": len(s["engines"])}
    else:
        s = build(dry_run=args.dry_run)
        _summary(s)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()

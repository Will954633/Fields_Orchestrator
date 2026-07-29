#!/usr/bin/env python3
"""
change_epoch_analysis.py — learn from our OWN natural experiments.

Every flow/deck change is an A/B in time: the sessions BEFORE vs AFTER a change on the
same surface reveal the change's effect. This bootstraps the off-market RL policy from
history instead of a cold start — the cycle reads it as a learned prior (Will, 2026-07-29:
"why is it not learning from all the sessions since the last flow change?").

For each change boundary it segments off-market sessions into pre/post epochs, **per arm**
(deck engagement events like `card_viewed` fire only in the deck arms — comparing across an
arm-mix shift would be an artifact), and diffs the engagement funnel:
  report_view → deck engagement (card_viewed) → deck depth → menu_sell → qualify → forward.

Writes `system_monitor.rl_change_epochs` (cycle reads it) + prints a human summary.
Honest by construction: reports N, partial-window flags, and per-arm splits — directional, not significant.

Change log lives in `system_monitor.rl_change_log` (seeded below; the cycle appends new changes
as it ships them, so future changes auto-analyse). Usage: python3 change_epoch_analysis.py [--window-days 14]
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts/brain2")
from shared.db import get_client                     # noqa: E402
from brain2_util import hog_retry                    # noqa: E402

PID = os.environ["POSTHOG_PROJECT_ID"]
KEY = os.environ.get("POSTHOG_ALL_ACCESS_KEY") or os.environ["POSTHOG_PERSONAL_API_KEY"]

# Seed change log — the clearest off-market boundaries. The cycle APPENDS as it ships changes.
SEED_CHANGES = [
    {"_id": "offmarket_intent_menu_2026-07-27", "date": "2026-07-27", "surface": "/off-market",
     "label": "Intent-menu redesign — fused hero+menu replaced the 0-converting ownership gate",
     "arm": "ladder_dark"},
]

REPORT_VIEW = "offmarket_report_view"


def hog(sql):
    return hog_retry(PID, KEY, sql)


def epoch_metrics(surface, arm, start, end):
    """Funnel metrics for one arm over [start, end). Rates are per report_view session."""
    arm_clause = f"AND properties.arm = '{arm}'" if arm else ""
    # sessions that viewed the deck (denominator)
    rows = hog(f"""
      SELECT
        uniqIf(properties.$session_id, event='{REPORT_VIEW}')                     AS views,
        uniqIf(properties.$session_id, event='card_viewed')                       AS engaged,
        uniqIf(properties.$session_id, event='offmarket_menu_sell')               AS menu_sell,
        uniqIf(properties.$session_id, event='offmarket_qualify')                 AS qualify,
        uniqIf(properties.$session_id, event='forward_cta_clicked')               AS forward,
        countIf(event='card_viewed')                                              AS card_views_total,
        uniqIf(properties.$session_id, event='deck_exit')                         AS deck_exits
      FROM events
      WHERE timestamp >= '{start}' AND timestamp < '{end}'
        AND startsWith(properties.$pathname, '{surface}')
        {arm_clause}
        AND event IN ('{REPORT_VIEW}','card_viewed','offmarket_menu_sell','offmarket_qualify','forward_cta_clicked','deck_exit')
    """)
    v, eng, ms, q, fwd, cvt, dx = (rows[0] if rows else [0, 0, 0, 0, 0, 0, 0])
    v = int(v or 0)
    def rate(n):
        return round(int(n or 0) / v, 3) if v else None
    return {"views": v, "engaged_rate": rate(eng), "menu_sell_rate": rate(ms),
            "qualify_rate": rate(q), "forward_rate": rate(fwd),
            "cards_per_engaged": round(int(cvt or 0) / int(eng), 2) if int(eng or 0) else None,
            "deck_exit_rate": rate(dx),
            "_counts": {"engaged": int(eng or 0), "menu_sell": int(ms or 0),
                        "qualify": int(q or 0), "forward": int(fwd or 0)}}


def analyse_change(ch, window_days):
    d = datetime.strptime(ch["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    pre_start = (d.timestamp() - window_days * 86400)
    def iso(ts):
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now(timezone.utc)
    post_end = min(d.timestamp() + window_days * 86400, now.timestamp())
    pre = epoch_metrics(ch["surface"], ch.get("arm"), iso(pre_start), ch["date"] + " 00:00:00")
    post = epoch_metrics(ch["surface"], ch.get("arm"), ch["date"] + " 00:00:00", iso(post_end))
    post_days = round((post_end - d.timestamp()) / 86400, 1)
    deltas = {}
    for k in ("engaged_rate", "menu_sell_rate", "qualify_rate", "forward_rate", "cards_per_engaged", "deck_exit_rate"):
        a, b = pre.get(k), post.get(k)
        deltas[k] = round(b - a, 3) if (a is not None and b is not None) else None
    return {"change": ch["label"], "date": ch["date"], "arm": ch.get("arm"),
            "window_days": window_days, "post_days_available": post_days,
            "pre": pre, "post": post, "deltas": deltas,
            "caveats": ["directional (small N)",
                        f"post window only {post_days}d of {window_days}d" if post_days < window_days else None,
                        "per-arm to avoid arm-mix artifact" if ch.get("arm") else "arm not segmented"]}


def run(window_days):
    c = get_client(); sm = c["system_monitor"]
    log = sm["rl_change_log"]
    for ch in SEED_CHANGES:
        log.update_one({"_id": ch["_id"]}, {"$setOnInsert": ch}, upsert=True)
    changes = list(log.find({}))
    results = [analyse_change(ch, window_days) for ch in changes]
    stamp = datetime.now(timezone.utc).isoformat()
    sm["rl_change_epochs"].update_one({"_id": "latest"},
        {"$set": {"computed_at": stamp, "window_days": window_days, "changes": results}}, upsert=True)

    print(f"# Off-Market change-epoch analysis @ {stamp} (±{window_days}d)\n")
    for r in results:
        print(f"## {r['date']} — {r['change']}  [arm={r['arm']}, post={r['post_days_available']}d]")
        print(f"{'metric':18}{'pre':>10}{'post':>10}{'delta':>10}")
        for k in ("engaged_rate", "cards_per_engaged", "menu_sell_rate", "forward_rate", "qualify_rate", "deck_exit_rate"):
            print(f"  {k:16}{str(r['pre'].get(k)):>10}{str(r['post'].get(k)):>10}{str(r['deltas'].get(k)):>10}")
        print(f"  views pre={r['pre']['views']} post={r['post']['views']} | caveats: "
              f"{[c for c in r['caveats'] if c]}\n")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=14)
    args = ap.parse_args()
    run(args.window_days)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
seo_signal.py — 2nd autonomous domain: the SEO (Google organic) SENSOR.

The SENSE half of the SEO sub-workflow — the same pattern as geo_signal.py, applied to Google
organic (our biggest channel, ~68% of traffic). Read-only over the GSC + affinity collections;
writes `system_monitor.rl_seo_signal` (+ history). The STEER/ACQUIRE half is the Claude analyst
cycle (seo_cycle.sh) that reads this + the shared reward ledger.

Per page it joins GSC performance (impressions / clicks / CTR / position) with the conversion tie
(organic_landing_affinity: sessions / converters) and flags the opportunities an SEO cycle acts on:
  - STRIKING DISTANCE — position ~5-20 with real impressions: small gains → page-1 / higher.
  - LOW-CTR — high impressions but CTR well below what the position should earn: title/snippet opportunity.
  - CONVERTING — organic entry pages that actually convert (protect + amplify; tie to the reward ledger).

Usage: python3 seo_signal.py [--dry-run]
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
COLL = "rl_seo_signal"

# Rough CTR-by-position benchmark (organic), to spot pages under-earning their rank.
def expected_ctr(pos):
    if pos <= 1: return 0.28
    if pos <= 2: return 0.15
    if pos <= 3: return 0.10
    if pos <= 5: return 0.06
    if pos <= 10: return 0.025
    if pos <= 20: return 0.008
    return 0.003


def build(dry_run=False):
    sm = get_client()["system_monitor"]

    # GSC per-page (aggregate the per-query rows in seo_landing_performance up to the page)
    pages = defaultdict(lambda: {"clicks": 0, "impressions": 0, "pos_wsum": 0.0, "queries": 0,
                                 "top_query": None, "top_query_impr": 0})
    for d in sm["seo_landing_performance"].find({}):
        pg = d.get("page")
        if not pg:
            continue
        p = pages[pg]
        impr = int(d.get("impressions") or 0)
        p["clicks"] += int(d.get("clicks") or 0)
        p["impressions"] += impr
        p["pos_wsum"] += float(d.get("position") or 0) * impr
        p["queries"] += 1
        if impr > p["top_query_impr"]:
            p["top_query_impr"] = impr
            p["top_query"] = d.get("query")

    # conversion tie (organic entry pages that convert)
    affinity = {d.get("entry_path"): d for d in sm["organic_landing_affinity"].find({})}

    rows = []
    for pg, p in pages.items():
        impr = p["impressions"]
        if impr <= 0:
            continue
        ctr = p["clicks"] / impr
        pos = p["pos_wsum"] / impr if impr else None
        aff = affinity.get(pg) or {}
        converters = int(aff.get("converters") or 0)
        sessions = int(aff.get("sessions") or 0)
        exp = expected_ctr(pos or 99)
        flags = []
        if pos and 4.5 <= pos <= 20 and impr >= 20:
            flags.append("striking_distance")
        if impr >= 50 and ctr < exp * 0.6:
            flags.append("low_ctr")
        if converters > 0:
            flags.append("converting")
        rows.append({
            "page": pg, "clicks": p["clicks"], "impressions": impr,
            "ctr": round(ctr, 4), "expected_ctr": exp, "avg_position": round(pos, 1) if pos else None,
            "top_query": p["top_query"], "sessions": sessions, "converters": converters,
            "flags": flags,
        })

    # rank: converting first, then striking-distance/low-ctr by impressions
    rows.sort(key=lambda r: (-(r["converters"] > 0), -("striking_distance" in r["flags"] or "low_ctr" in r["flags"]), -r["impressions"]))

    tot_impr = sum(r["impressions"] for r in rows)
    tot_clicks = sum(r["clicks"] for r in rows)
    snapshot = {
        "kind": "seo_signal_snapshot", "_id": "latest", "computed_at": NOW.isoformat(),
        "totals": {"pages": len(rows), "impressions": tot_impr, "clicks": tot_clicks,
                   "ctr": round(tot_clicks / tot_impr, 4) if tot_impr else 0},
        "opportunities": {
            "striking_distance": [r for r in rows if "striking_distance" in r["flags"]][:15],
            "low_ctr": [r for r in rows if "low_ctr" in r["flags"]][:15],
            "converting": [r for r in rows if "converting" in r["flags"]][:15],
        },
        "top_pages": rows[:25],
        "note": ("SENSE half of the SEO sub-workflow. Google organic (~68% of traffic). Joins GSC "
                 "per-page performance with the reward-ledger conversion tie. Feeds seo_cycle.sh."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, snapshot, upsert=True)
        c.insert_one({k: v for k, v in {**snapshot, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return snapshot


def _summary(s):
    t = s["totals"]
    print(f"\n=== SEO SIGNAL (Google organic) — {t['pages']} pages, {t['impressions']} impr, "
          f"{t['clicks']} clicks (CTR {t['ctr']*100:.1f}%) ===")
    for label in ("converting", "striking_distance", "low_ctr"):
        opp = s["opportunities"][label]
        print(f"\n{label.upper()} ({len(opp)}):")
        for r in opp[:6]:
            print(f"  {r['page'][:48]:<48} impr={r['impressions']:>5} pos={r['avg_position'] or '-':>4} "
                  f"ctr={r['ctr']*100:>4.1f}% conv={r['converters']}  «{(r['top_query'] or '')[:30]}»")
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
        with job_run("rl_seo_signal", cadence_hours=168, title="General RL — SEO (Google organic) sensor") as beat:
            s = build(dry_run=False)
            _summary(s)
            beat.detail = (f"{s['totals']['pages']} pages; "
                           f"{len(s['opportunities']['striking_distance'])} striking, "
                           f"{len(s['opportunities']['converting'])} converting")
    else:
        s = build(dry_run=args.dry_run)
        _summary(s)
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()

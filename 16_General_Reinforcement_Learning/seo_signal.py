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

    # GSC per-page.
    # ⚠ AUTHORITATIVE rows are dims='page'. Do NOT aggregate the per-query rows up to the
    # page to get a total: Search Console withholds anonymized queries entirely, so those
    # rows carried 9% of impressions and 7% of clicks (measured 90d to 2026-08-30). This
    # sensor did exactly that until 2026-08-30 and reported the channel as ~5.3k impressions
    # / 78 clicks when it was 58.4k / 1,178 — see [SEO-QUERY-DIMENSION-BLINDNESS]. Every
    # priority the SEO domain set between 2026-07 and 2026-08 was ranked on that 9% sample.
    pages = defaultdict(lambda: {"clicks": 0, "impressions": 0, "pos_wsum": 0.0, "queries": 0,
                                 "top_query": None, "top_query_impr": 0})
    for d in sm["seo_landing_performance"].find({"dims": "page"}):
        pg = d.get("page")
        if not pg:
            continue
        p = pages[pg]
        impr = int(d.get("impressions") or 0)
        p["clicks"] += int(d.get("clicks") or 0)
        p["impressions"] += impr
        p["pos_wsum"] += float(d.get("position") or 0) * impr

    # Query attribution only — names the query, never contributes to a total.
    for d in sm["seo_landing_performance"].find({"dims": "page,query,device"}):
        pg = d.get("page")
        if not pg or pg not in pages:
            continue
        p = pages[pg]
        impr = int(d.get("impressions") or 0)
        p["queries"] += 1
        if impr > p["top_query_impr"]:
            p["top_query_impr"] = impr
            p["top_query"] = d.get("query")

    site_totals = sm["seo_landing_performance"].find_one({"dims": "__site_totals__"}) or {}

    # conversion tie (organic entry pages that convert).
    # ⚠ organic_landing_affinity is keyed by PATH ('/property/x'); GSC pages are absolute
    # URLs ('https://fieldsestate.com.au/property/x'). Looking one up with the other never
    # matched, so `converters` was 0 on every row and the CONVERTING arm — the one the
    # mandate calls the most valuable — never fired once. Fixed 2026-08-30, see
    # [SEO-SIGNAL-AFFINITY-KEY-MISMATCH]. Trailing slashes are normalised too.
    def _path_of(u):
        p = str(u or "").replace("https://fieldsestate.com.au", "").split("?")[0].split("#")[0]
        return (p.rstrip("/") or "/")

    affinity = {}
    for d in sm["organic_landing_affinity"].find({}):
        affinity[_path_of(d.get("entry_path"))] = d

    rows = []
    for pg, p in pages.items():
        impr = p["impressions"]
        if impr <= 0:
            continue
        ctr = p["clicks"] / impr
        pos = p["pos_wsum"] / impr if impr else None
        aff = affinity.get(_path_of(pg)) or {}
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

    # Template rollup — with ~12k ranking URLs the per-page list no longer shows the shape
    # of the channel. This is what actually tells you where the traffic lives.
    tmpl = defaultdict(lambda: {"urls": 0, "impressions": 0, "clicks": 0, "pos_wsum": 0.0})
    for r in rows:
        path = r["page"].replace("https://fieldsestate.com.au", "") or "/"
        key = next((t for t in ("/property/", "/off-market/", "/articles/", "/article/",
                                "/market-intelligence/", "/market-metrics/", "/houses-for-sale/",
                                "/report/", "/sold/", "/news", "/about")
                    if path.startswith(t)), path if len(path) < 25 else "other")
        t = tmpl[key]
        t["urls"] += 1
        t["impressions"] += r["impressions"]
        t["clicks"] += r["clicks"]
        t["pos_wsum"] += (r["avg_position"] or 0) * r["impressions"]
    templates = sorted(
        ({"template": k, "urls": v["urls"], "impressions": v["impressions"], "clicks": v["clicks"],
          "ctr": round(v["clicks"] / v["impressions"], 4) if v["impressions"] else 0,
          "avg_position": round(v["pos_wsum"] / v["impressions"], 1) if v["impressions"] else None}
         for k, v in tmpl.items()), key=lambda x: -x["impressions"])

    snapshot = {
        "kind": "seo_signal_snapshot", "_id": "latest", "computed_at": NOW.isoformat(),
        "totals": {"pages": len(rows), "impressions": tot_impr, "clicks": tot_clicks,
                   "ctr": round(tot_clicks / tot_impr, 4) if tot_impr else 0,
                   "window_days": site_totals.get("window_days"),
                   "site_impressions": site_totals.get("impressions"),
                   "site_clicks": site_totals.get("clicks")},
        "templates": templates,
        "opportunities": {
            "striking_distance": [r for r in rows if "striking_distance" in r["flags"]][:15],
            "low_ctr": [r for r in rows if "low_ctr" in r["flags"]][:15],
            "converting": [r for r in rows if "converting" in r["flags"]][:15],
        },
        "top_pages": rows[:25],
        "note": ("SENSE half of the SEO sub-workflow. Google organic (~68% of traffic). Joins GSC "
                 "per-page performance with the reward-ledger conversion tie. Feeds seo_cycle.sh. "
                 "Totals are from GSC dims='page' (authoritative). The per-query rows are a ~9% "
                 "sample because Google withholds anonymized queries — they name a page's top "
                 "query and must never be summed into a total ([SEO-QUERY-DIMENSION-BLINDNESS], "
                 "fixed 2026-08-30)."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, snapshot, upsert=True)
        c.insert_one({k: v for k, v in {**snapshot, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return snapshot


def _summary(s):
    t = s["totals"]
    win = f" over {t['window_days']}d" if t.get("window_days") else ""
    print(f"\n=== SEO SIGNAL (Google organic) — {t['pages']} ranking URLs, {t['impressions']} impr, "
          f"{t['clicks']} clicks (CTR {t['ctr']*100:.1f}%){win} ===")
    if t.get("site_impressions"):
        print(f"    site totals (GSC, exact): {t['site_impressions']} impr / {t['site_clicks']} clicks")
    if s.get("templates"):
        print(f"\n{'TEMPLATE':26} {'urls':>6} {'impr':>7} {'clicks':>7} {'CTR':>7} {'pos':>5}")
        for r in s["templates"][:10]:
            print(f"  {r['template'][:24]:24} {r['urls']:6d} {r['impressions']:7d} {r['clicks']:7d} "
                  f"{r['ctr']*100:6.2f}% {r['avg_position'] or 0:5.1f}")
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

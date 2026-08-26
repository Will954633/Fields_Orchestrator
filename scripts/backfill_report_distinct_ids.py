#!/usr/bin/env python3
"""
backfill_report_distinct_ids.py — recover the REAL PostHog session for reports
whose stored `owner.posthog_distinct_id` has zero ingested events.

Why
---
A report captures the PostHog distinct_id at SUBMIT time. If posthog-js minted a
fresh anonymous id between the landing pageview and the submit (the Facebook /
Instagram in-app browser resets storage mid-funnel), the id written onto the report
has NO events and cannot be joined to the session that actually produced the lead.
See memory report_posthog_distinctid_rotation. The FE fix (register device_token as
a super-property + emit `report_created`) stops it going forward; this script
recovers the sessions already stranded.

Method (conservative — only reconciles a CONFIDENT single match)
---------------------------------------------------------------
For each user-generated report whose stored id has 0 events:
  1. Build the set of pathnames that funnel would have produced — the recorded
     first_touch.landing_page, `/find/<report-suburb>`, and the report's own
     `/your-home/<slug>` / `/off-market/<slug>` pages.
  2. Query events in [created_at - 6min, created_at + 30s] on those paths, from any
     distinct_id EXCEPT the report's own and known internal ids.
  3. If exactly ONE distinct_id matches on a funnel path (best: the exact landing
     page or the report slug) with its last event before created_at, reconcile it
     with confidence=high. Otherwise record candidates and leave it (Rule 8: an
     ambiguous match is not evidence — never guess a join).

Writes (only with --apply): a NEW field, never overwriting the original —
  owner.posthog_distinct_id_reconciled       the recovered id
  owner.posthog_distinct_id_reconcile        {method, confidence, matched_path,
                                              lag_seconds, candidates, at}

Usage
  python3 scripts/backfill_report_distinct_ids.py --dry-run
  python3 scripts/backfill_report_distinct_ids.py --apply
  python3 scripts/backfill_report_distinct_ids.py --dry-run --days 120
"""
from __future__ import annotations
import argparse
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from shared.db import get_client                        # noqa: E402
from crm_sync import posthog_query, INTERNAL_IDS        # noqa: E402

CORE_SUBURB_SLUG = {
    "robina": "robina", "varsity_lakes": "varsity-lakes",
    "burleigh_waters": "burleigh-waters",
}
# reports that are our own builds, not a person asking for one — skip entirely.
NOT_A_USER_SOURCE_BITS = ("mint", "prewarm", "test", "demo", "comparison",
                          "diagnostic", "e2e", "fallback")

WINDOW_BEFORE = timedelta(minutes=6)
WINDOW_AFTER = timedelta(seconds=30)


def _q(v: str) -> str:
    return v.replace("'", "")


def user_reports(sm, days: int) -> list[dict]:
    """Reports with a captured user distinct_id that aren't our own builds/tests."""
    since = datetime.utcnow() - timedelta(days=days)
    out = []
    for d in sm.property_reports.find({"created_at": {"$gte": since}}):
        o = d.get("owner") or {}
        did = o.get("posthog_distinct_id")
        if not did:
            continue
        if d.get("is_test") or o.get("is_internal"):
            continue
        src = (d.get("source") or "").lower()
        if any(b in src for b in NOT_A_USER_SOURCE_BITS):
            continue
        out.append(d)
    return out


def ids_with_events(dids: list[str]) -> set[str]:
    """Subset of dids that have >=1 ingested PostHog event."""
    have = set()
    CHUNK = 100
    for i in range(0, len(dids), CHUNK):
        chunk = dids[i:i + CHUNK]
        idlist = ", ".join("'" + _q(x) + "'" for x in chunk)
        rows = posthog_query(
            f"select distinct_id, count() from events "
            f"where distinct_id in ({idlist}) group by distinct_id")
        have.update(r[0] for r in rows if r[1])
    return have


def expected_paths(d: dict) -> set[str]:
    o = d.get("owner") or {}
    paths = set()
    lp = ((o.get("attribution") or {}).get("first_touch") or {}).get("landing_page")
    if lp:
        paths.add(lp.split("?")[0])
    sub = (d.get("suburb_key") or d.get("suburb") or "").lower().replace(" ", "_")
    if sub in CORE_SUBURB_SLUG:
        paths.add(f"/find/{CORE_SUBURB_SLUG[sub]}")
    slug = d.get("slug")
    if slug:
        paths.add(f"/your-home/{slug}")
        paths.add(f"/off-market/{slug}")
        paths.add(f"/analyse-your-home/building/{slug}")
    return {p for p in paths if p}


def find_session(d: dict) -> dict | None:
    """Recover the real distinct_id for one report, or None if not confident."""
    created = d.get("created_at")
    if not isinstance(created, datetime):
        return None
    own = (d.get("owner") or {}).get("posthog_distinct_id")
    t0 = (created - WINDOW_BEFORE).strftime("%Y-%m-%d %H:%M:%S")
    t1 = (created + WINDOW_AFTER).strftime("%Y-%m-%d %H:%M:%S")
    paths = expected_paths(d)
    if not paths:
        return None
    path_pred = " or ".join(f"properties.$pathname = '{_q(p)}'" for p in paths)
    rows = posthog_query(
        "select distinct_id, properties.$pathname, max(timestamp) as last_ts, "
        "count() as n, any(properties.$browser) as browser "
        "from events "
        f"where timestamp > toDateTime('{t0}') and timestamp < toDateTime('{t1}') "
        f"and ({path_pred}) "
        "group by distinct_id, properties.$pathname order by last_ts asc")

    # collapse to one row per distinct_id (its strongest, latest funnel hit)
    by_id: dict[str, dict] = {}
    for did, path, last_ts, n, browser in rows:
        if did == own or did in INTERNAL_IDS:
            continue
        # last event must be at/before the report was created (they submitted, THEN
        # the report row was written) with a small +30s slop for clock skew.
        cand = by_id.setdefault(did, {"did": did, "paths": set(), "last_ts": last_ts,
                                      "n": 0, "browser": browser})
        cand["paths"].add(path)
        cand["n"] += n
        if last_ts > cand["last_ts"]:
            cand["last_ts"] = last_ts

    if not by_id:
        return None

    def parse_ts(t):
        return t if isinstance(t, datetime) else datetime.fromisoformat(str(t).replace("Z", "+00:00"))

    cands = list(by_id.values())
    # Confident only when exactly one candidate sits on a funnel path in-window.
    matched_path = None
    for c in cands:
        c["last_dt"] = parse_ts(c["last_ts"])
    cands.sort(key=lambda c: c["last_dt"], reverse=True)

    result = {
        "reconciled": None, "confidence": "none",
        "candidates": [{"did": c["did"], "paths": sorted(c["paths"]),
                        "browser": c.get("browser")} for c in cands],
        "matched_path": None, "lag_seconds": None,
    }
    if len(cands) == 1:
        c = cands[0]
        created_utc = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        lag = (created_utc - c["last_dt"]).total_seconds()
        result.update(reconciled=c["did"], confidence="high",
                      matched_path=sorted(c["paths"])[0], lag_seconds=round(lag))
    return result


def run(days: int, apply: bool) -> dict:
    c = get_client()
    sm = c["system_monitor"]
    try:
        reports = user_reports(sm, days)
        have = ids_with_events([(r["owner"] or {}).get("posthog_distinct_id") for r in reports])
        broken = [r for r in reports
                  if (r["owner"] or {}).get("posthog_distinct_id") not in have]

        print(f"user reports (last {days}d): {len(reports)}  |  "
              f"with events: {len(have)}  |  ZERO events (broken join): {len(broken)}\n")

        reconciled = ambiguous = 0
        for r in sorted(broken, key=lambda x: str(x.get("created_at"))):
            res = find_session(r)
            slug = r.get("slug")
            src = r.get("source")
            when = str(r.get("created_at"))[:19]
            if res and res["confidence"] == "high":
                reconciled += 1
                print(f"  ✓ {when}  {slug:<42} [{src}]")
                print(f"       stored {(r['owner'] or {}).get('posthog_distinct_id')}  ->  "
                      f"{res['reconciled']}  ({res['matched_path']}, "
                      f"{res['lag_seconds']}s before, {res['candidates'][0].get('browser')})")
                if apply:
                    sm.property_reports.update_one(
                        {"_id": r["_id"]},
                        {"$set": {
                            "owner.posthog_distinct_id_reconciled": res["reconciled"],
                            "owner.posthog_distinct_id_reconcile": {
                                "method": "landing_window_v1",
                                "confidence": res["confidence"],
                                "matched_path": res["matched_path"],
                                "lag_seconds": res["lag_seconds"],
                                "candidates": res["candidates"],
                                "at": datetime.utcnow(),
                            }}})
            else:
                ambiguous += 1
                n = len(res["candidates"]) if res else 0
                print(f"  ? {when}  {slug:<42} [{src}]  — no confident match "
                      f"({n} candidate(s) in window)")

        print(f"\n{'APPLIED' if apply else 'DRY RUN'}: "
              f"{reconciled} reconciled, {ambiguous} left ambiguous, "
              f"{len(broken)} broken of {len(reports)} user reports.")
        return {"reports": len(reports), "broken": len(broken),
                "reconciled": reconciled, "ambiguous": ambiguous}
    finally:
        c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    run(args.days, apply=args.apply)


if __name__ == "__main__":
    main()

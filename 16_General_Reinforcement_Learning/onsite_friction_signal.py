#!/usr/bin/env python3
"""
onsite_friction_signal.py — the ONSITE FRICTION sensor: surface WHERE THE SITE IS BREAKING.

Sibling to onsite_signal.py. Where onsite_signal answers "who is hot" (opportunity), this
answers "what is broken" (friction) — the class of issue that was previously only found by a
human happening to glance at PostHog. On 2026-07-30 a real Robina seller searched their own
address ~40× on /analyse-your-home, got 0 results every time (stored "Glen Eagles" vs typed
"Gleneagles"), abandoned, and left — an unreachable warm lead lost to a bug the growth-optimising
onsite agent had no way to see (it scores POSITIVE intent; a high-search-no-submit session even
reads as a warm lead). This sensor closes that blind spot.

Reads (read-only): raw PostHog events (freshest — carries the search_query TEXT and result_count)
via the Query API, enriched with `organic_journeys` for `searched_address_category` (so an
out-of-coverage search that legitimately returns nothing is NOT flagged, but an IN-COVERAGE /
home-owner address that returns nothing IS — that's a real bug). Writes `system_monitor.rl_onsite_friction`
(+ history). The onsite cycle reads this alongside rl_onsite_signal; HIGH-severity incidents are
Telegrammed to Will and become Conductor directives to the owning domain.

Incident types (v1, search-funnel-focused — the surface that just bit us):
  SEARCH_NO_SUBMIT   — session with >= MIN_SEARCHES address_search and 0 submit (esp. + abandon)
  SEARCH_RETRY_LOOP  — many searches converging on ONE address string (retyping, nothing matches)
  SEARCH_ZERO_RESULT — address_search with result_count == 0 (only once the frontend emits it)
  CLIENT_ERROR       — $exception (JS error) clustered on a key funnel page

Usage: python3 onsite_friction_signal.py [--days N] [--dry-run] [--telegram]
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "rl_onsite_friction"
MIN_SEARCHES = 5          # >= this many searches with 0 submit = struggling
KEY_FUNNEL = "/analyse-your-home"
# categories where a returned-nothing search is a REAL bug (the address exists / is ours to know)
IN_COVERAGE = {"current_listing", "recent_listing", "withdrawn_listing", "likely_home_owner", "home_owner"}


def _norm(q):
    return re.sub(r"[^a-z0-9]", "", (q or "").lower())


def _posthog(days):
    """Pull search-funnel + error events for the window, grouped by session. [] if unconfigured."""
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY") or os.environ.get("POSTHOG_ALL_ACCESS_KEY")
    pid = os.environ.get("POSTHOG_PROJECT_ID", "348370")
    if not key:
        return []
    q = f"""
    SELECT properties.$session_id AS sid, distinct_id, timestamp, event,
           properties.search_query AS q, properties.result_count AS rc,
           properties.$pathname AS path, properties.$exception_message AS exc
    FROM events
    WHERE timestamp >= now() - INTERVAL {int(days)} DAY
      AND event IN ('address_search','analyse_home_address_submit','analyse_home_submit_success',
                    'analyse_abandoned','$exception')
    ORDER BY sid, timestamp
    LIMIT 100000
    """
    req = urllib.request.Request(
        f"https://us.posthog.com/api/projects/{pid}/query/",
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": q}}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r).get("results", [])


def build(days=7, dry_run=False):
    sm = get_client()["system_monitor"]

    # session_id -> searched_address_category (from the nightly journey rollup), to tell a real
    # bug (in-coverage address returned nothing) from an expected miss (out-of-coverage).
    cat_by_session = {}
    for j in sm["organic_journeys"].find({}, {"session_id": 1, "searched_address_category": 1}):
        if j.get("session_id"):
            cat_by_session[j["session_id"]] = j.get("searched_address_category")

    rows = _posthog(days)
    by_sess = defaultdict(list)
    for sid, did, ts, event, qtext, rc, path, exc in rows:
        by_sess[sid or f"anon:{did}"].append(
            {"did": did, "ts": ts, "event": event, "q": qtext, "rc": rc, "path": path, "exc": exc})

    incidents = []
    err_pages = defaultdict(int)
    for sid, evs in by_sess.items():
        searches = [e for e in evs if e["event"] == "address_search"]
        submits = [e for e in evs if e["event"] in ("analyse_home_address_submit", "analyse_home_submit_success")]
        abandoned = any(e["event"] == "analyse_abandoned" for e in evs)
        for e in evs:
            if e["event"] == "$exception":
                err_pages[(e.get("path") or "?")] += 1
        if not searches:
            continue
        did = searches[0]["did"]
        cat = cat_by_session.get(sid)
        in_cov = cat in IN_COVERAGE
        n = len(searches)
        queries = [s["q"] for s in searches if s.get("q")]
        longest = max(queries, key=len) if queries else ""
        nlong = _norm(longest)
        # retry-loop: most queries are prefixes/variants converging on ONE address string
        conv = sum(1 for q in queries if nlong and (_norm(q) in nlong or nlong in _norm(q)
                    or _norm(q)[:6] == nlong[:6])) if nlong else 0
        retry_loop = len(queries) >= MIN_SEARCHES and nlong and (conv / max(len(queries), 1)) >= 0.6 and len(nlong) >= 8
        zero_results = [s for s in searches if str(s.get("rc")) == "0"]

        typ = sev = None
        if zero_results and (in_cov or len(_norm(zero_results[-1].get("q"))) >= 8):
            typ, base = "SEARCH_ZERO_RESULT", 40
        elif not submits and n >= MIN_SEARCHES:
            typ = "SEARCH_RETRY_LOOP" if retry_loop else "SEARCH_NO_SUBMIT"
            base = 25 if retry_loop else 15
        if not typ:
            continue
        score = base + min(n, 20) * 1.5 + (10 if abandoned else 0) + (20 if in_cov else 0) + (10 if retry_loop else 0)
        sev = "HIGH" if score >= 55 else ("MEDIUM" if score >= 35 else "LOW")
        incidents.append({
            "type": typ, "severity": sev, "score": round(score, 1),
            "session_id": sid, "distinct_id": did, "surface": KEY_FUNNEL,
            "n_searches": n, "submitted": len(submits), "abandoned": abandoned,
            "zero_result_hits": len(zero_results),
            "address_category": cat, "in_coverage": in_cov, "retry_loop": bool(retry_loop),
            "longest_query": (longest or "")[:80],
            "sample_queries": [q[:60] for q in queries[:6]],
            "last_seen": max((e["ts"] for e in evs), default=""),
            "why": (f"{n} searches, {len(submits)} submits"
                    + (", ABANDONED" if abandoned else "")
                    + (f", converging on '{longest[:40]}'" if retry_loop else "")
                    + (f", in-coverage {cat} → should have matched" if in_cov else
                       (f", {cat}" if cat else ""))),
        })
    incidents.sort(key=lambda r: -r["score"])

    client_errors = [{"page": p, "count": c} for p, c in
                     sorted(err_pages.items(), key=lambda kv: -kv[1]) if c >= 3]

    sev_counts = {s: sum(1 for i in incidents if i["severity"] == s) for s in ("HIGH", "MEDIUM", "LOW")}
    snapshot = {
        "kind": "onsite_friction_snapshot", "_id": "latest", "computed_at": NOW.isoformat(),
        "window_days": days,
        "totals": {"sessions_scanned": len(by_sess), "incidents": len(incidents), **sev_counts,
                   "client_error_pages": len(client_errors)},
        "incidents": incidents[:40],
        "client_errors": client_errors[:15],
        "note": ("Onsite FRICTION sensor — surfaces broken/struggling funnel behaviour (search-no-submit, "
                 "retry loops, zero-result searches, JS errors) so a bug like the 2026-07-30 Gleneagles "
                 "address-search failure is caught by a recurring process, not a human glancing at PostHog. "
                 "Read by the onsite cycle; HIGH severity → Telegram + Conductor directive."),
    }
    if not dry_run:
        c = sm[COLL]
        c.replace_one({"_id": "latest"}, snapshot, upsert=True)
        c.insert_one({k: v for k, v in {**snapshot, "snapshot_at": NOW.isoformat()}.items() if k != "_id"})
    return snapshot


def _summary(s):
    t = s["totals"]
    print(f"\n=== ONSITE FRICTION — {t['incidents']} incidents "
          f"(HIGH {t['HIGH']}, MED {t['MEDIUM']}, LOW {t['LOW']}) over {s['window_days']}d, "
          f"{t['sessions_scanned']} sessions ===")
    for i in s["incidents"][:12]:
        print(f"  [{i['severity']:<6} {i['score']:>5}] {i['type']:<18} did={str(i['distinct_id'])[:12]:<12} "
              f"n={i['n_searches']} sub={i['submitted']}  {i['why'][:70]}")
    if s["client_errors"]:
        print("  client errors:", ", ".join(f"{e['page']}×{e['count']}" for e in s["client_errors"][:5]))
    print()


def _telegram_new_high(snapshot, prev_high_ids):
    highs = [i for i in snapshot["incidents"] if i["severity"] == "HIGH"]
    new = [i for i in highs if i["session_id"] not in prev_high_ids]
    if not new:
        return
    try:
        from telegram_notify import send_message
    except Exception:
        return
    lines = [f"⚠️ Onsite friction: {len(new)} new HIGH incident(s) on {KEY_FUNNEL}"]
    for i in new[:5]:
        lines.append(f"• {i['type']}: {i['why']}" + (f" — e.g. \"{i['longest_query']}\"" if i.get("longest_query") else ""))
    lines.append("Likely a broken funnel step (search/submit). Check rl_onsite_friction.")
    send_message("\n".join(lines), parse_mode=None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()

    prev_high = set()
    if args.telegram and not args.dry_run:
        prev = get_client()["system_monitor"][COLL].find_one({"_id": "latest"}) or {}
        prev_high = {i["session_id"] for i in (prev.get("incidents") or []) if i.get("severity") == "HIGH"}

    try:
        from job_status import job_run
    except Exception:
        job_run = None

    def run():
        s = build(days=args.days, dry_run=args.dry_run)
        _summary(s)
        if args.telegram and not args.dry_run:
            _telegram_new_high(s, prev_high)
        return s

    if job_run and not args.dry_run:
        with job_run("rl_onsite_friction", cadence_hours=24, title="General RL — Onsite friction sensor") as beat:
            s = run()
            t = s["totals"]
            beat.detail = f"{t['incidents']} incidents (HIGH {t['HIGH']}, MED {t['MEDIUM']}) / {t['sessions_scanned']} sessions"
            beat.metrics = t
    else:
        s = run()
        if args.dry_run:
            print("(dry-run — nothing written)")


if __name__ == "__main__":
    main()

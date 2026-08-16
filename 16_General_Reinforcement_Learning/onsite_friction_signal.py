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
import urllib.error
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
# 2026-08-13: the sensor was scoped entirely to the address-search funnel — every incident path is
# behind `if not searches: continue`. That page was ~100% Facebook-fed and fell to ~2 users/week when
# ads paused 2026-07-30, so the sensor now watches an empty room: 3 sessions scanned over 7d while
# 545 organic users passed through the site in 28d, 324 of them onto the off-market deck. A deck
# reader who bounces at the hero or rage-clicks produced no incident of any kind. DECK_DEAD_END adds
# that surface. `is_internal` is also now excluded — Will's own testing was scoring as user friction.
MIN_DECK_SESSIONS = 8      # don't call a dead end until the surface has been seen this many times
DECK_ENGAGED_FRAC = 0.6    # >= this share actually reading (sections_read >= 1) = a real audience
DECK_FORWARD_OK_FRAC = 0.05  # forward-CTA clicks above this share of engaged readers = not a dead end
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
    # $exception_message is ALWAYS null on this project — the text lives in $exception_values.
    q = f"""
    SELECT properties.$session_id AS sid, distinct_id, timestamp, event,
           properties.search_query AS q, properties.result_count AS rc,
           properties.$pathname AS path, properties.$exception_values AS exc
    FROM events
    WHERE timestamp >= now() - INTERVAL {int(days)} DAY
      AND ifNull(toString(properties.is_internal), 'false') != 'true'
      AND event IN ('address_search','analyse_home_address_submit','analyse_home_submit_success',
                    'analyse_abandoned','$exception','$rageclick')
    ORDER BY sid, timestamp
    LIMIT 100000
    """
    req = urllib.request.Request(
        f"https://us.posthog.com/api/projects/{pid}/query/",
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": q}}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r).get("results", [])


def _hogql(sql):
    """Run a HogQL query. Raises on failure — see below.

    ⚠ THIS USED TO `except Exception: return []` (fixed 2026-08-16, onsite RL
    cycle). In a SENSOR that is the worst possible handler: `_deck_dead_ends()`
    reads this and a swallowed 400 renders identically to a healthy funnel —
    "0 incidents". A malformed query, a rotated key and a site with no friction
    all printed the same line, and the one that matters is invisible.

    HogQL rejects more than you would expect (`last` is a reserved keyword,
    `toInt32OrNull` does not exist), so a failing query here is a live
    possibility, not a theoretical one. Rule 7b: the run must assert an outcome,
    not merely fail to throw. It now raises; `job_run` records the error and the
    Process Registry shows ERROR rather than a clean nightly zero.
    """
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY") or os.environ.get("POSTHOG_ALL_ACCESS_KEY")
    pid = os.environ.get("POSTHOG_PROJECT_ID", "348370")
    if not key:
        # Distinct from a failure: unconfigured is a known, reportable state and
        # the caller's `if not rows` path already treats it as "no data".
        return []
    req = urllib.request.Request(
        f"https://us.posthog.com/api/projects/{pid}/query/",
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r).get("results", [])
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise RuntimeError(f"HogQL query failed ({e.code}): {detail}\n--- query ---\n{sql}") from e


def _deck_dead_ends(days):
    """DECK_DEAD_END — the off-market deck is the biggest organic surface but had no sensor at all.

    A deck reader is invisible to the search-funnel incident loop above, because that loop is gated
    on an `address_search` event firing at all. Reported per suburb so one dud page does not read as
    a site-wide failure.

    ⚠ The pathology here is NOT bouncing. Measured 2026-08-13 over 25 non-internal v4_report_exit
    users in 28d: only 3 read zero sections, and sections_read runs 1-11. Readers read — 2 to 3
    sections typically — and then leave, with 1 forward_cta_clicked across 183 arm-assigned deck
    users in the same window. So the incident is ENGAGED-BUT-NO-EXIT, and the denominator is readers
    who actually read (sections_read >= 1). Scoring on hero-bounce instead would fire never, which
    is how this surface stayed unmonitored while being the largest organic destination on the site.

    ⚠ Do not use `deepest_section` for this: it reported 'hero' for 13-14 users whose sections_read
    was > 0, i.e. it contradicts sections_read on the same event. Logged as a V4 telemetry defect.

    ⚠ THIS DETECTOR HAD NEVER RUN. From the day it was written until 2026-08-16 the query below
    called `toInt64OrNull`, which HogQL does not have, so every call 400'd — and `_hogql` swallowed
    the error and returned []. The deck therefore had no sensor at all while eight consecutive
    snapshots printed "0 incidents", which is the same sentence a healthy deck produces. Both halves
    are fixed: `_hogql` now raises, and `sections_read` is read as the Float that PostHog stores
    (confirmed against the project's own property types, not guessed — Rule 8).
    """
    rows = _hogql(f"""
      SELECT ifNull(toString(properties.suburb),'?') sub,
             uniq(distinct_id) readers,
             uniqIf(distinct_id, toFloat(properties.sections_read) >= 1) engaged
      FROM events WHERE event = 'v4_report_exit'
        AND timestamp >= now() - INTERVAL {int(days)} DAY
        AND ifNull(toString(properties.is_internal), 'false') != 'true'
      GROUP BY sub ORDER BY readers DESC LIMIT 20""")
    # ⚠ THE FORWARD ACTION IS VERSION-SPECIFIC. This counted only
    # `forward_cta_clicked`, which is emitted by DiscoveryDeck.tsx and
    # OffMarketDeck.tsx — the V3 decks. V4 has been the live default since
    # 2026-08-14 and never emits it (its own events are enumerated in
    # OffMarketPage/v4: report request, claim submit). So the test compared V4
    # readers against a V4-impossible event, which is a guaranteed incident
    # rather than a measurement — it would have reported every suburb as a dead
    # end forever, and its first live run (2026-08-16) duly did.
    # A V4 reader's forward actions are: ask for the written report, or claim an
    # attribute. `forward_cta_clicked` stays in the union for residual V3 traffic.
    fwd = _hogql(f"""
      SELECT uniq(distinct_id) FROM events
        WHERE event IN ('forward_cta_clicked','offmarket_report_requested','offmarket_claim_submitted')
        AND timestamp >= now() - INTERVAL {int(days)} DAY
        AND ifNull(toString(properties.is_internal), 'false') != 'true'""")
    n_forward = (fwd[0][0] if fwd and fwd[0] else 0)

    out = []
    for sub, readers, engaged in rows:
        if not readers or readers < MIN_DECK_SESSIONS:
            continue
        frac = engaged / readers
        # Engaged readers who never take a forward action. If a decent share DID click through,
        # the surface is working and this is not an incident regardless of read depth.
        if frac < DECK_ENGAGED_FRAC or n_forward > max(1, engaged * DECK_FORWARD_OK_FRAC):
            continue
        score = 30 + frac * 20 + (20 if n_forward == 0 else 10)
        out.append({
            "type": "DECK_DEAD_END", "severity": "HIGH" if score >= 55 else "MEDIUM",
            "score": round(score, 1), "session_id": f"deck:{sub}:{days}d", "distinct_id": None,
            "surface": "/off-market", "suburb": sub,
            "n_searches": 0, "submitted": 0, "abandoned": False, "zero_result_hits": 0,
            "address_category": None, "in_coverage": None, "retry_loop": False,
            "longest_query": "", "sample_queries": [],
            "readers": readers, "engaged_readers": engaged, "forward_cta_users": n_forward,
            "last_seen": NOW.isoformat(),
            "why": (f"{engaged}/{readers} deck readers in {sub} read >=1 section ({frac:.0%}) but "
                    f"only {n_forward} user(s) took ANY forward action site-wide over {days}d "
                    f"(report request / attribute claim / V3 forward CTA) — engaged, no exit"),
        })
    return out


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
    incidents.extend(_deck_dead_ends(days))
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

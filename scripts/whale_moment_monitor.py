#!/usr/bin/env python3
"""Whale Moment monitor — is the seasonal overlay firing, and is it harmless?

Full context, including what this can and CANNOT answer, is in
docs/WHALE_MONITOR.md. Read it before changing a threshold here.

The short version: this is a *health* check, not an experiment. Site traffic is
~20-50 people/day, so the question "does the whale lift engagement or return
visits?" is statistically unreachable and is deliberately not attempted. What IS
reachable at this sample size is the operational question — is it firing at all,
is it firing at the RIGHT moment, and is it obviously driving people away.

Three things it watches, each tied to a real defect from 2026-08-05
(fix-history [WHALE-ROUTE-MISFIRE]):

  misfires   whale_shown landing within MISFIRE_WINDOW_S of a pageview in the
             same session. That is the exact signature of the trigger carrying
             scroll state across an SPA navigation and firing on arrival — the
             moment of peak intent. Any at all is a regression.
  silence    zero showings over a week, in season, with real traffic. That is
             the signature of pageIsBusy() vetoing everything again (the closed
             nav drawer used to match [role="dialog"] and suppress every
             trigger sitewide).
  harm       share of dismissals followed by more browsing in the same session.
             Within-person, so it needs no control group and reads usefully at
             n=20 — unlike anything comparing whale-seers to non-seers, which is
             confounded by construction (the trigger SELECTS people who stopped
             reading, so they were always going to leave more often).

Out of season (Oct-Jun AEST) zero showings is correct, not a fault, so the
silence alarm is suppressed — otherwise this row sits red for nine months a year
and stops being read.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_status import job_run  # noqa: E402

AEST = ZoneInfo("Australia/Brisbane")
SEASON_MONTHS = (7, 8, 9)  # must match useWhaleTrigger.ts
DOC_URL = "https://github.com/Will954633/Fields_Orchestrator/blob/main/docs/WHALE_MONITOR.md"

# A showing this soon after a pageview cannot be a disengagement signal — the
# fastest legitimate trigger needs MIN_DWELL_MS (8s) on the page first.
MISFIRE_WINDOW_S = 5.0
# Misfires are only counted from when the fix went live (commit 4c253949).
# The single historical showing IS a misfire — it is what prompted this monitor
# — and without a floor it would hold the row red for a week over a bug that is
# already fixed, which is how a health row stops being read.
FIX_DEPLOYED_AT = datetime(2026, 8, 5, 1, 35, tzinfo=timezone.utc)
# Don't cry silence on a genuinely dead week. ~30 visitors/day is normal, so a
# week clearing this bar means traffic was there and the whale still never fired.
SILENCE_MIN_VISITORS = 50
WINDOW_DAYS = 7


def _load_env() -> None:
    if os.environ.get("COSMOS_CONNECTION_STRING") and os.environ.get("POSTHOG_PERSONAL_API_KEY"):
        return
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    try:
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def in_season(now_aest: datetime) -> bool:
    return now_aest.month in SEASON_MONTHS


def hogql(sql: str) -> list[dict]:
    """Run a HogQL query. Raises on any failure — never returns [] on error.

    That distinction is the whole point: a silently-empty result here would be
    read as "the whale never fired" and would raise a false silence alarm, which
    is precisely how the nightly lead chain lost three nights of leads to a 504.
    """
    key = os.environ["POSTHOG_PERSONAL_API_KEY"]
    proj = os.environ.get("POSTHOG_PROJECT_ID", "348370")
    req = urllib.request.Request(
        f"https://us.posthog.com/api/projects/{proj}/query/",
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    if "results" not in body:
        raise RuntimeError(f"PostHog returned no results key: {list(body)[:6]}")
    cols = body.get("columns", [])
    return [dict(zip(cols, row)) for row in body["results"]]


def main() -> None:
    _load_env()
    now_utc = datetime.now(timezone.utc)
    now_aest = now_utc.astimezone(AEST)
    season = str(now_aest.year)
    since = now_utc - timedelta(days=WINDOW_DAYS)

    with job_run(
        "whale_moment_monitor",
        cadence_hours=24,
        title="Whale Moment (seasonal overlay)",
        doc_url=DOC_URL,
    ) as beat:
        from pymongo import MongoClient

        client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"])
        sm = client["system_monitor"]

        # --- authoritative showing count: server-side, deduped per person+season.
        # PostHog is client-side and lossy, so it must not be what decides
        # "did anyone see it" — that is exactly why whale_moments exists.
        # `?whale=1` previews are logged with trigger='forced' (deliberately — see
        # the whale memory) and must be excluded from every real-user metric.
        # They are QA traffic, they inflate reach, and — because a forced preview
        # fires immediately at mount — they are byte-for-byte identical to the
        # Bug 1 misfire signature. Counting them would make routine QA raise the
        # alarm and would let a single preview mask a real silence.
        all_docs = list(sm["whale_moments"].find({"season": season}))
        season_docs = [d for d in all_docs if d.get("first_trigger") != "forced"]
        forced_docs = [d for d in all_docs if d.get("first_trigger") == "forced"]

        def created(d):
            v = d.get("created_at")
            if isinstance(v, datetime):
                return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None

        recent = [d for d in season_docs if (c := created(d)) and c >= since]
        people_season = len(season_docs)
        people_7d = len(recent)

        # --- PostHog enrichment. Degrade loudly, never silently: if this fails
        # the counts above still stand and the silence alarm still works.
        ph_ok, ph_err = True, ""
        misfires, dismissals, continued, elapsed_ms, audio_playing, visitors_7d = [], [], 0, [], 0, None
        try:
            shown = hogql(f"""
                SELECT $session_id AS sid, timestamp AS ts, properties.surface AS surface,
                       properties.trigger AS trigger
                FROM events WHERE event = 'whale_shown'
                  AND timestamp > now() - INTERVAL {WINDOW_DAYS} DAY
                  AND properties.trigger != 'forced'
            """)
            dism = hogql(f"""
                SELECT $session_id AS sid, timestamp AS ts,
                       properties.elapsed_ms AS elapsed_ms, properties.method AS method,
                       properties.audio_state AS audio_state
                FROM events WHERE event = 'whale_dismissed'
                  AND timestamp > now() - INTERVAL {WINDOW_DAYS} DAY
                  AND properties.trigger != 'forced'
            """)
            traffic = hogql(f"""
                SELECT uniq(person_id) AS people FROM events
                WHERE event = '$pageview' AND timestamp > now() - INTERVAL {WINDOW_DAYS} DAY
            """)
            visitors_7d = int(traffic[0]["people"]) if traffic else 0

            sids = {r["sid"] for r in shown} | {r["sid"] for r in dism}
            views = []
            if sids:
                quoted = ",".join("'" + s.replace("'", "") + "'" for s in sids if s)
                if quoted:
                    views = hogql(f"""
                        SELECT $session_id AS sid, timestamp AS ts FROM events
                        WHERE event = '$pageview' AND $session_id IN ({quoted})
                          AND timestamp > now() - INTERVAL {WINDOW_DAYS + 1} DAY
                    """)

            def parse(t):
                return datetime.fromisoformat(str(t).replace("Z", "+00:00"))

            by_sid: dict[str, list[datetime]] = {}
            for v in views:
                by_sid.setdefault(v["sid"], []).append(parse(v["ts"]))

            # misfire: a showing hard up against a pageview in the same session
            for s in shown:
                ts = parse(s["ts"])
                if ts < FIX_DEPLOYED_AT:
                    continue
                prior = [p for p in by_sid.get(s["sid"], []) if p <= ts]
                if prior and (ts - max(prior)).total_seconds() < MISFIRE_WINDOW_S:
                    misfires.append({"surface": s.get("surface"), "trigger": s.get("trigger"),
                                     "gap_s": round((ts - max(prior)).total_seconds(), 2)})

            # harm: did they keep browsing after dismissing?
            for d in dism:
                ts = parse(d["ts"])
                dismissals.append(d)
                if any(p > ts for p in by_sid.get(d["sid"], [])):
                    continued += 1
                if d.get("elapsed_ms") is not None:
                    try:
                        elapsed_ms.append(int(d["elapsed_ms"]))
                    except (TypeError, ValueError):
                        pass
                if d.get("audio_state") == "playing":
                    audio_playing += 1
        except Exception as e:  # noqa: BLE001 — degraded, not fatal
            ph_ok, ph_err = False, f"{type(e).__name__}: {e}"[:160]

        elapsed_ms.sort()
        median_elapsed = elapsed_ms[len(elapsed_ms) // 2] if elapsed_ms else None
        n_dism = len(dismissals)
        metrics = {
            "people_season": people_season,
            "people_7d": people_7d,
            "forced_previews_season": len(forced_docs),
            "dismissals_7d": n_dism,
            "misfires_7d": len(misfires),
            "misfire_examples": misfires[:5],
            "continued_after_dismiss_pct": round(100 * continued / n_dism) if n_dism else None,
            "audio_playing_pct": round(100 * audio_playing / n_dism) if n_dism else None,
            "median_elapsed_ms": median_elapsed,
            "visitors_7d": visitors_7d,
            "in_season": in_season(now_aest),
            "posthog_ok": ph_ok,
        }

        # Persist history regardless of outcome, so the (underpowered but
        # directional) season review has something to read later.
        sm["whale_monitor_daily"].replace_one(
            {"_id": now_aest.strftime("%Y-%m-%d")},
            {"_id": now_aest.strftime("%Y-%m-%d"), "recorded_at": now_utc,
             "season": season, **metrics},
            upsert=True,
        )
        client.close()
        beat.metrics = metrics

        if misfires:
            raise RuntimeError(
                f"{len(misfires)} whale showing(s) fired <{MISFIRE_WINDOW_S}s after a pageview "
                f"— trigger is firing on arrival again, e.g. {misfires[0]}. See docs."
            )
        if not in_season(now_aest):
            beat.detail = f"out of season (Jul-Sep AEST) — 0 expected, {people_season} this season"
            return
        if people_7d == 0 and (visitors_7d or 0) >= SILENCE_MIN_VISITORS:
            raise RuntimeError(
                f"0 whale showings in {WINDOW_DAYS}d during migration season with "
                f"{visitors_7d} visitors — suspect the pageIsBusy() veto. See docs."
            )

        bits = [f"{people_7d} shown/{WINDOW_DAYS}d", f"{people_season} this season", "0 misfires"]
        if metrics["continued_after_dismiss_pct"] is not None:
            bits.append(f"{metrics['continued_after_dismiss_pct']}% kept browsing")
        if median_elapsed is not None:
            bits.append(f"median {median_elapsed / 1000:.1f}s watched")
        if not ph_ok:
            bits.append(f"DEGRADED: PostHog {ph_err}")
        beat.detail = " · ".join(bits)


if __name__ == "__main__":
    main()

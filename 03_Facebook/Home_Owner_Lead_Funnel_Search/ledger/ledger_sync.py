#!/usr/bin/env python3
"""
*** RETIRED 2026-08-05 (Will) — cron commented out, heartbeat deleted. DO NOT RE-CRON AS-IS. ***

Both halves had stopped being useful:

  FB half   : its only campaign (120251771274010134, "Leads TEST: Home Owner Hooks — SEQ ex-GC v2")
              has been PAUSED since 2026-07-30 with the rest of the Home Owner funnel. The ledger
              froze at data dates 2026-07-28..30 and every hourly run since just re-upserted the
              same 120 ad_stats rows, changing only `updated_at` (~15x/day, reporting success).
  PostHog   : never worked at all. `lab_*` events have NEVER been fired — verified against PostHog
    half      all-time with no filters, while the same query returns real data for other events.
              The EVENT_SPINE below was designed but the instrumentation was never shipped onto the
              landing pages, so funnel_event rows have always been 0.

If the Home Owner funnel is revived, note that reviving THIS script only restores ad-level numbers.
The per-step drop-out analysis it was built for needs the `lab_*` instrumentation to exist first —
check that events are actually arriving in PostHog before trusting the funnel_event side.

See fix-history [HEALTH-BOARD-PAUSED-VS-DEAD] / [MONITOR-FITNESS-PROBES]. Original docs follow.
-----------------------------------------------------------------------------------------------
ledger_sync.py — populate the funnel ledger from its two sources (build 6A).

  FB side  : Graph API ad-level insights (per variant/day) -> ad_stats rows.
  PostHog  : lab_* behavioural events (per person/step)      -> funnel_event rows.

Both writes are idempotent (deterministic _id + upsert), so this runs hourly over
an overlapping look-back window without double-counting. Self-reports via job_run
(CLAUDE.md Rule 7) as `home_owner_funnel_ledger_sync`, cadence 1h — surfaces on the
Systems Health "Process Registry" board (OK / STALE / ERROR).

Cron: 3 8-22 * * *  (a couple of minutes after the hourly checkpoint)
Usage: python3 ledger_sync.py [--hours N] [--no-fb] [--no-posthog]
"""
from __future__ import annotations
import os, sys, json, argparse, urllib.request, urllib.error
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
load_dotenv("/home/fields/Fields_Orchestrator/.env")

from funnel_ledger import Ledger, EVENT_SPINE, CALL_CTA_EVENT
try:
    from job_status import job_run
except Exception:
    job_run = None

FB_API = "https://graph.facebook.com/v21.0"
FB_TOKEN = os.environ.get("FACEBOOK_ADS_TOKEN", "")
POSTHOG_PROJECT_ID = os.environ.get("POSTHOG_PROJECT_ID", "348370")
POSTHOG_QUERY_URL = f"https://us.i.posthog.com/api/projects/{POSTHOG_PROJECT_ID}/query/"

# Which FB campaigns feed the ledger. The out-of-market TEST today; lab campaigns
# get appended here as they are created (kept in one place on purpose).
def _lab_campaigns() -> list[str]:
    cfg = os.path.join(HERE, "lab_campaigns.json")
    ids = ["120251771274010134"]  # out-of-market copy-discovery TEST
    if os.path.exists(cfg):
        try:
            ids = json.load(open(cfg)).get("campaigns", ids)
        except Exception:
            pass
    return ids

# Internal / bot noise filters (reused from crm_sync.py so the ledger stays clean).
INTERNAL_IDS = ["019d03c0-df65-73a0-a156-8e0b18ba42a4",
                "019d102e-5fb2-7818-8e2a-99d81b4b4297",
                "019d24b3-da5e-7a72-9e6a-b34f118e64c7"]
BOT_CITIES = ["Boardman", "Prineville", "Forest City", "Clonee", "Luleå", "Altoona",
              "Gallatin", "Fort Worth", "Des Moines", "Ashburn", "Council Bluffs", "The Dalles"]


# ---------------------------------------------------------------------------
# FB -> ad_stats
# ---------------------------------------------------------------------------
def sync_fb(lg: Ledger) -> dict:
    rows = 0; variants = set()
    for cid in _lab_campaigns():
        r = requests.get(f"{FB_API}/{cid}/insights", params={
            "date_preset": "maximum", "level": "ad", "time_increment": 1, "limit": 500,
            "fields": "ad_name,spend,impressions,clicks,actions,date_start",
            "access_token": FB_TOKEN}, timeout=60).json()
        if "error" in r:
            raise RuntimeError(f"FB insights {cid}: {r['error'].get('message')}")
        for a in r.get("data", []):
            acts = {x["action_type"]: float(x["value"]) for x in a.get("actions", [])}
            leads = int(acts.get("lead", 0) or acts.get("onsite_conversion.lead_grouped", 0))
            lg.record_ad_stats(variant=a["ad_name"], date=a["date_start"],
                               spend=float(a.get("spend", 0)),
                               impressions=int(a.get("impressions", 0)),
                               clicks=int(a.get("clicks", 0)), fb_leads=leads)
            rows += 1; variants.add(a["ad_name"])
    return {"ad_stats_rows": rows, "variants": len(variants)}


# ---------------------------------------------------------------------------
# PostHog -> funnel_event
# ---------------------------------------------------------------------------
def _posthog_query(sql: str) -> list[list]:
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY") or os.environ.get("POSTHOG_API_KEY")
    if not key:
        raise RuntimeError("POSTHOG_PERSONAL_API_KEY not set")
    payload = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    req = urllib.request.Request(POSTHOG_QUERY_URL, data=payload, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read()).get("results", [])
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"PostHog {e.code}: {e.read().decode()[:300]}")


def sync_posthog(lg: Ledger, hours: int) -> dict:
    internal = ", ".join("'" + i + "'" for i in INTERNAL_IDS)
    bots = ", ".join("'" + c + "'" for c in BOT_CITIES)
    all_events = ", ".join("'" + e + "'" for e in (EVENT_SPINE + [CALL_CTA_EVENT]))
    sql = f"""
        SELECT uuid, distinct_id, event, timestamp,
               properties.variant, properties.lab_cid, properties.step,
               properties.field, properties.goal, properties.terminal_type,
               properties.email_domain, properties.selling_intent
        FROM events
        WHERE event IN ({all_events})
          AND timestamp > now() - INTERVAL {int(hours)} HOUR
          AND distinct_id NOT IN ({internal})
          AND properties.$geoip_city_name NOT IN ({bots})
        ORDER BY timestamp
        LIMIT 10000
    """
    rows = _posthog_query(sql)
    n = 0
    for row in rows:
        (uuid, did, event, ts, variant, lab_cid, step, field, goal,
         terminal_type, email_domain, intent) = (list(row) + [None] * 12)[:12]
        if not uuid or not variant:
            continue  # a lab event with no variant is unattributable — skip
        if variant == "unknown" or str(variant).startswith("_"):
            continue  # self-test / misconfigured traffic (e.g. _SELFTEST) — never ledger it
        props = {}
        if email_domain:
            props["email_domain"] = email_domain
        if intent:
            props["selling_intent"] = intent
        lg.record_funnel_event(uuid=str(uuid), distinct_id=str(did or "?"),
                               variant=str(variant), event=str(event),
                               ts=str(ts), lab_cid=str(lab_cid or ""),
                               step=step, field=str(field or ""),
                               goal=str(goal or ""),
                               terminal_type=str(terminal_type or ""),
                               props=props or None)
        n += 1
    return {"funnel_event_rows": n}


def run(hours: int, do_fb: bool, do_ph: bool) -> dict:
    lg = Ledger()
    lg.ensure_indexes()
    summary = {}
    if do_fb:
        summary.update(sync_fb(lg))
    if do_ph:
        summary.update(sync_posthog(lg, hours))
    summary.update(lg.counts())
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48, help="PostHog look-back window")
    ap.add_argument("--no-fb", action="store_true")
    ap.add_argument("--no-posthog", action="store_true")
    args = ap.parse_args()

    def _do():
        return run(args.hours, not args.no_fb, not args.no_posthog)

    if job_run:
        with job_run("home_owner_funnel_ledger_sync", cadence_hours=1,
                     title="Home Owner Funnel — Reward Ledger Sync") as beat:
            summary = _do()
            beat.detail = (f"ad_stats={summary.get('ad_stats')} "
                           f"events={summary.get('funnel_event')} "
                           f"variants={summary.get('variants')}")
            beat.metrics = summary
    else:
        summary = _do()
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()

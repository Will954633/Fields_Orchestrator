#!/usr/bin/env python3
"""
Main-site health check — freshness + completeness audit of every dynamic data point
served by the main website (https://fieldsestate.com.au).

Unlike the mini-site checker (one document per home), the main site reads a fixed
catalogue of shared data sources. This auditor checks those collections directly,
grouped by the PAGE that consumes them, and emits per-data-point status:

  OK | STALE | MISSING | ERROR | UNKNOWN-FRESHNESS | KNOWN-GAP

Writes a per-run snapshot to system_monitor.mainsite_health_snapshots so it can
populate "date last changed" and detect silently frozen feeds.

Source of truth for fields/thresholds: MAIN_SITE_DATA_DICTIONARY.md

Usage:
  python3 scripts/main_site_health_check.py                 # audit, print summary
  python3 scripts/main_site_health_check.py --json out.json # write full results JSON
  python3 scripts/main_site_health_check.py --no-snapshot   # don't persist snapshot
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from pymongo import MongoClient

AEST = ZoneInfo("Australia/Brisbane") if ZoneInfo else timezone(timedelta(hours=10))
NIGHTLY_RUN_HOUR = 20  # pipeline trigger 20:30 AEST
NIGHTLY_RUN_MIN = 30

# ---- status constants ---------------------------------------------------------
OK, STALE, MISSING, ERROR, UNKNOWN, GAP = (
    "OK", "STALE", "MISSING", "ERROR", "UNKNOWN-FRESHNESS", "KNOWN-GAP")
SEVERITY = {ERROR: 4, MISSING: 3, STALE: 2, UNKNOWN: 1, GAP: 0, OK: 0}

# Clock-age thresholds (days) for periodic (Tier-2) sources.
CADENCE_DAYS = {"weekly": 10, "monthly": 40, "macro": 35, "sold": 14, "valuation": 3,
                "scrape": 2}  # per-listing last_updated only bumps on change → 2-day tolerance

# ---- suburb scope -------------------------------------------------------------
SUBS = ["robina", "varsity_lakes", "burleigh_waters", "mudgeeraba", "reedy_creek", "worongary"]
CORE3 = ["robina", "burleigh_waters", "varsity_lakes"]
CHART_TYPES = ["days_on_market", "sales_volume", "turnover_rate", "market_cycle"]

# Page order = Google Sheet tab order
# Business-wide scope added 2026-07-22: this sheet started as "main website
# freshness" only. Process Registry / GitHub Actions / Market Signals Fetch /
# Leads & CRM / Ads & Compliance cover the rest of the business (orchestrator
# cron fleet, off-VM automation, leads pipeline, ad-decision logging) so the
# sheet is one source of truth, not a website-only view.
PAGES = ["Process Registry", "Pipeline Processes", "Sitemap", "GitHub Actions",
         "Market Metrics", "Market Signals Fetch", "For Sale / Sold", "Property Page",
         "Articles", "Leads & CRM", "Ads & Compliance", "Valuation Accuracy", "Known Gaps"]

FIELDS_AUTOMATION_REPO = "Will954633/fields-automation"

# Files the VM's daily sitemap cron (06:15 AEST, regenerate-sitemap.sh) pushes.
# 2026-07-22: that push silently failed every day 07-20 through 07-22
# ("Argument list too long" on the 3.9MB file, gh CLI --field content= arg
# limit) while the script still printed "Done." and exited 0 — Google kept
# crawling a 2-day-stale sitemap and nobody noticed until Will caught a
# published property not showing up in search. This check is the fix for
# that specific silence: track each file's actual last-pushed commit age.
SITEMAP_REPO = "Will954633/Website_Version_Feb_2026"
SITEMAP_FILES = ["public/sitemap.xml", "public/news-sitemap.xml"]


# ---- helpers (mirror minisite_health_check.py) --------------------------------
def get_path(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def as_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        s = v.replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(s)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(v[:19], fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def expected_last_run(now_utc):
    """Most recent 20:30 AEST instant at or before now (as UTC)."""
    now_aest = now_utc.astimezone(AEST)
    run_today = now_aest.replace(hour=NIGHTLY_RUN_HOUR, minute=NIGHTLY_RUN_MIN, second=0, microsecond=0)
    if now_aest < run_today:
        run_today -= timedelta(days=1)
    return run_today.astimezone(timezone.utc)


def value_hash(v):
    try:
        s = json.dumps(v, sort_keys=True, default=str)
    except TypeError:
        s = str(v)
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def suburb_label(s):
    return s.replace("_", " ").title()


def last_commit_for_path(repo, path):
    """Timestamp + SHA of the most recent commit touching `path` on `repo`'s
    default branch, via `gh api` (subprocess — the .env GITHUB_TOKEN is known
    to override/break `gh`'s own auth, so unset it first, matching every other
    gh-api call in this codebase). Returns (datetime|None, sha|None, error|None)."""
    import subprocess
    env = dict(os.environ)
    env.pop("GITHUB_TOKEN", None)
    env.setdefault("GH_CONFIG_DIR", "/home/projects/.config/gh")
    try:
        # NOTE: `gh api` defaults to POST once any -f/-F flag is present unless
        # --method GET is explicit — bit us during testing (silent 404 on this
        # exact call). Query-string form sidesteps the footgun entirely.
        p = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits?path={path}&per_page=1"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        if p.returncode != 0:
            return None, None, (p.stderr or p.stdout or "gh api failed")[:200]
        commits = json.loads(p.stdout)
        if not commits:
            return None, None, "no commits found for this path"
        c = commits[0]
        ts = as_dt(c["commit"]["committer"]["date"])
        return ts, c["sha"][:12], None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"[:200]


def gh_api(path):
    """Generic `gh api <path>` -> (parsed_json|None, error|None). Same env
    handling as last_commit_for_path (GITHUB_TOKEN in .env breaks gh's own
    auth; GH_CONFIG_DIR points at the fine-grained PAT for Will954633)."""
    import subprocess
    env = dict(os.environ)
    env.pop("GITHUB_TOKEN", None)
    env.setdefault("GH_CONFIG_DIR", "/home/projects/.config/gh")
    try:
        p = subprocess.run(["gh", "api", path], env=env, capture_output=True, text=True, timeout=25)
        if p.returncode != 0:
            return None, (p.stderr or p.stdout or "gh api failed")[:200]
        return json.loads(p.stdout), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"[:200]


def systemctl_is_active(unit):
    """('active'|'failed'|'inactive'|..., error|None) for a systemd unit."""
    import subprocess
    try:
        p = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10)
        return p.stdout.strip() or p.stderr.strip(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"[:200]


def log_freshness_check(log_path, cadence_days, error_patterns=("Traceback (most recent call last)",)):
    """For cron scripts whose only observable trace is their redirected log
    file (no DB/Drive/GCS side effect to check instead): mtime vs. cadence,
    plus a tail-grep for failure patterns. Returns (status, detail, mtime).
    Supports a glob pattern (e.g. logs with a date in the filename) — picks
    the newest match."""
    import glob as _glob
    matches = sorted(_glob.glob(log_path), key=os.path.getmtime) if any(c in log_path for c in "*?[") else (
        [log_path] if os.path.exists(log_path) else [])
    if not matches:
        return MISSING, "log file not found", None
    path = matches[-1]
    mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    age_days = (datetime.now(timezone.utc) - mtime).total_seconds() / 86400
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 20000), os.SEEK_SET)
            chunk = f.read().decode("utf-8", errors="ignore")
        # Only the last ~60 lines, not the whole 20KB window — these logs are
        # appended to run after run, so a byte-window alone can still contain
        # an old, since-resolved failure from a prior run and misreport it as
        # current (caught in testing: mongo-allowlist-refresh.log and
        # brain2-nightly-refresh.log both had an old Traceback earlier in the
        # window despite their most recent run completing cleanly).
        tail = "\n".join(chunk.splitlines()[-60:])
    except OSError:
        tail = ""
    hit = next((pat for pat in error_patterns if pat in tail), None)
    if hit:
        return ERROR, f"'{hit}' found in last run's log tail", mtime
    if age_days > cadence_days:
        return STALE, f"log not updated in {age_days:.1f}d (expected every {cadence_days}d)", mtime
    return OK, "", mtime


# ---- freshness judging --------------------------------------------------------
def judge(fresh_ts, cadence, now_utc, last_run):
    """Return (status, detail) for a present source given its freshness ts + cadence."""
    if fresh_ts is None:
        return UNKNOWN, "no freshness timestamp"
    age = (now_utc - fresh_ts).total_seconds() / 86400
    if cadence == "nightly":
        if fresh_ts < last_run:
            return STALE, f"missed nightly run (last {fresh_ts.date()}, {age:.1f}d ago)"
        return OK, ""
    thr = CADENCE_DAYS.get(cadence)
    if thr is None:
        return OK, ""
    if age > thr:
        return STALE, f">{thr}d old ({fresh_ts.date()}, {age:.1f}d ago)"
    return OK, ""


# ---- row builder --------------------------------------------------------------
def mk_row(page, name, scope, value, status, fresh_field, fresh_ts, detail,
           now_utc, prev_map, note=None, info=False):
    key = f"{page}::{name}::{scope}"
    vh = value_hash([value, status])
    prev = prev_map.get(key)
    last_changed = (prev.get("last_changed") if prev and prev.get("value_hash") == vh
                    else now_utc.isoformat())
    return {
        "page": page, "name": name, "scope": scope or "—",
        "value": value, "value_hash": vh, "status": status,
        "fresh_field": fresh_field or "", "detail": detail or "",
        "freshness_ts": fresh_ts.isoformat() if fresh_ts else None,
        "last_changed": last_changed, "note": note, "info": info, "key": key,
    }


# ---- GitHub Actions (off-VM automation, fields-automation repo) ---------------
def collect_github_actions(add):
    """14 scheduled article-generation workflows run on GitHub Actions via a
    self-hosted runner, entirely outside VM cron/systemd — invisible to every
    other check in this file. None of them have a failure-notification step;
    they rely on GitHub's default owner-email, which is easy to miss (a
    2026-07-22 audit found 3 failing silently — one for 5 straight weeks)."""
    PG = "GitHub Actions"
    wf_data, err = gh_api(f"repos/{FIELDS_AUTOMATION_REPO}/actions/workflows?per_page=100")
    if err or not wf_data:
        add(PG, "Workflow list", FIELDS_AUTOMATION_REPO, None, ERROR, "", None,
            f"could not list workflows: {err}")
        return
    runs_data, err2 = gh_api(f"repos/{FIELDS_AUTOMATION_REPO}/actions/runs?per_page=100")
    runs_by_wf = {}
    if runs_data and not err2:
        for r in runs_data.get("workflow_runs", []):
            runs_by_wf.setdefault(r["workflow_id"], r)  # runs are newest-first
    for wf in wf_data.get("workflows", []):
        if wf.get("state") != "active":
            add(PG, wf["name"], "schedule", "disabled", GAP, "", None, "workflow disabled in GitHub", info=True)
            continue
        r = runs_by_wf.get(wf["id"])
        if not r:
            add(PG, wf["name"], "latest run", "no runs yet", UNKNOWN, "", None, "never triggered")
            continue
        ts = as_dt(r.get("run_started_at") or r.get("created_at"))
        if r.get("status") != "completed":
            add(PG, wf["name"], "latest run", r.get("status"), UNKNOWN, "run_started_at", ts, "still running")
            continue
        conclusion = r.get("conclusion")
        st = OK if conclusion == "success" else ERROR
        detail = "" if st == OK else (
            f"last run {conclusion} — no failure-notification step on this workflow, "
            f"relies on GitHub's default owner-email only")
        add(PG, wf["name"], "latest run", conclusion, st, "run_started_at", ts, detail)


# ---- Market Signals Fetch (job-success, not just data-staleness) --------------
def collect_market_signals_fetch(add, sm, now_utc):
    """fetch_abs_market_signals.py / fetch_macro_indicators.py can "succeed"
    (exit 0, write a doc) while every indicator silently defaulted to
    null/NEUTRAL — e.g. the 2026-07-22 DNS failure that ran undetected for
    weeks because the Market Metrics page only checks data staleness, not
    whether the fetch actually resolved real values. These two scripts now
    self-report via job_status.record_job_result(); this reads that record."""
    PG = "Market Signals Fetch"
    for job, cadence_days, min_written in [("fetch_abs_market_signals", 8, 5),
                                            ("fetch_macro_indicators", 8, 5)]:
        d = sm["job_runs"].find_one({"job": job})
        if not d:
            add(PG, job, "job outcome", None, MISSING, "run_at", None,
                "no run recorded yet — instrumentation just added; populates after next weekly run")
            continue
        ts = as_dt(d.get("run_at"))
        age_days = (now_utc - ts).total_seconds() / 86400 if ts else None
        written, total = d.get("indicators_written"), d.get("indicators_total")
        val = f"{written}/{total}" if written is not None else d.get("status")
        if d.get("status") == "error":
            add(PG, job, "job outcome", val, ERROR, "run_at", ts, d.get("detail", "job reported error"))
        elif age_days is not None and age_days > cadence_days:
            add(PG, job, "job outcome", val, STALE, "run_at", ts, f"last run {age_days:.1f}d ago (expected weekly)")
        elif written is not None and written < min_written:
            add(PG, job, "job outcome", val, ERROR, "run_at", ts,
                f"only {written}/{total} indicators resolved — {d.get('detail', '')}")
        else:
            add(PG, job, "job outcome", val, OK, "run_at", ts, d.get("detail", ""))


# ---- Leads & CRM ---------------------------------------------------------------
def collect_leads_crm(add, sm, now_utc, last_run):
    """Nightly leads-tracker syncs write straight to a Google Sheet with no
    health check anywhere today — a failed sync would only be noticed if Will
    happened to open the sheet. Reads each script's own log for a run marker;
    these three already Telegram a summary line, so success/failure text is
    typically in the log tail even though the alert itself isn't breach-gated."""
    PG = "Leads & CRM"
    orch_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name, log_name, cadence_days in [
        ("Live Leads Tracker", "live-leads-sheet.log", 2),
        ("Sold Homes → Sheet", "sold-homes-sheet.log", 2),
        ("Listed Homes → Sheet", "listed-homes-sheet.log", 2),
    ]:
        st, dt, mtime = log_freshness_check(
            os.path.join(orch_dir, "logs", log_name), cadence_days,
            error_patterns=("Traceback (most recent call last)", "pymongo.errors"))
        add(PG, name, "nightly sync", mtime.date().isoformat() if mtime else None, st, "log mtime", mtime, dt)


# ---- Ads & Compliance -----------------------------------------------------------
def collect_ads_compliance(add, sm, now_utc):
    """(a) ad_decisions is CLAUDE.md's mandatory Rule 3 log for every FB/Google
    campaign create/pause/enable/budget-change — enforced by convention only,
    never checked. This is a best-effort freshness signal, not proof every ad
    change got logged (that needs comparing against actual FB/Google campaign
    state, which this doesn't do). (b) Nightly compliance archive/backup
    (PO Act record-keeping) has zero alerting of any kind today."""
    PG = "Ads & Compliance"
    d = sm["ad_decisions"].find_one(sort=[("created_at", -1)])
    n = sm["ad_decisions"].count_documents({})
    if not d:
        add(PG, "Ad decision logging", "all", "0 entries", MISSING, "created_at", None,
            "no ad_decisions ever recorded — best-effort check only, see docstring", info=True)
    else:
        ts = as_dt(d.get("created_at"))
        age_days = (now_utc - ts).total_seconds() / 86400 if ts else None
        st = STALE if (age_days is not None and age_days > 30) else OK
        add(PG, "Ad decision logging", "all", f"{n} entries, newest {ts.date() if ts else '—'}", st,
            "created_at", ts, "best-effort freshness only — doesn't verify every change was logged (Rule 3)")

    orch_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    st, dt, mtime = log_freshness_check(
        os.path.join(orch_dir, "logs", "compliance-nightly.log"), 2,
        error_patterns=("Traceback (most recent call last)", "hash mismatch", "verify failed"))
    add(PG, "Compliance nightly (PO Act K/L/N)", "archive + offsite backup",
        mtime.date().isoformat() if mtime else None, st, "log mtime", mtime, dt)


# ---- Process Registry (every cron job / systemd daemon / off-VM runner) -------
# Declarative inventory from the 2026-07-22 crontab/systemd audit. Most rows
# use the log-freshness fallback (their only observable trace); anything with
# a real DB/Sheet/API side effect checked in detail elsewhere in this file
# just gets a pointer to that tab instead of a second, shallower check.
_REGISTRY_LOG_JOBS = [
    # (name, category, log filename or glob, cadence_days)
    ("Ops context refresh", "Website/Infra", "ops-refresh.log", 1),
    ("Property insights (nightly)", "Website", "/home/fields/logs/insights_*.log", 1),
    ("Schema snapshot", "Infra", "schema_snapshot.log", 1),
    ("Article index builder", "Content", "article-index.log", 1),
    ("Market intelligence extractor", "Content", "market-insights.log", 1),
    ("Search Intent Collector", "SEO", "search-intent.log", 3),
    ("Search Intent Analyser", "SEO", "search-intent-analyser.log", 3),
    ("Google Indexing API submit", "SEO", "google-indexing.log", 1),
    ("FB metrics collector", "Ads", "fb-metrics.log", 1),
    ("Google Ads metrics collector", "Ads", "google-ads-metrics.log", 1),
    ("Marketing stage tracker", "Ads", "marketing-stage.log", 1),
    ("Post performance tracker", "Ads", "performance-tracker.log", 1),
    ("Cost collector", "Ads/Finance", "cost-collector.log", 1),
    ("Brain2: ad creative enrich", "Ads", "brain2-ad-enrich.log", 1),
    ("Brain2: attribution/behaviour/journey", "Ads", "brain2-nightly-refresh.log", 1),
    ("Brain2: SEO landing performance", "SEO", "brain2-seo.log", 1),
    ("Photo inventory sync", "Content", "photo-sync.log", 1),
    ("Five Property Friday batch", "Content", "fpf-send.log", 8),
    ("DOM backfill", "Market Intelligence", "dom-backfill.log", 35),
    ("Market charts precompute (dom/cycle)", "Market Intelligence", "precompute-market-charts.log", 35),
    ("Market charts precompute (volume/turnover)", "Market Intelligence", "precompute-market-charts.log", 35),
    ("Precompute seasonality", "Market Intelligence", "precompute-seasonality.log", 35),
    ("Property timeline refresh (weekly)", "Market Intelligence", "refresh-timelines.log", 9),
    ("Valuation backtest (weekly)", "Valuation", "backtest-weekly.log", 9),
    ("CRM sync (hourly)", "Leads/CRM", "crm-sync.log", 1),
    ("Property report activity feed", "Leads/CRM", "property-reports-refresh.log", 1),
    ("MongoDB backup", "Infra/Backup", "mongodb-backup.log", 1),
    ("Mongo allowlist refresh", "Infra", "mongo-allowlist-refresh.log", 1),
    ("Ops state push", "Infra", "/var/log/blob-backup/ops-state.log", 1),
    ("GCS blob backup (gsutil rsync)", "Infra/Backup", "/var/log/blob-backup/daily-sync.log", 1),
    ("KB Lite ingest (Brain 3)", "Knowledge Base", "kb-lite-ingest.log", 1),
    ("VM resource metrics writer", "Infra", "/tmp/vm_metrics.log", 1),
]
_REGISTRY_ALREADY_COVERED = [
    ("Sitemap regen (daily push)", "Website/SEO", "Sitemap tab"),
    ("SEO indexation readout (weekly)", "SEO", "already Telegram-alerts on breach"),
    ("Weekly SEO pilot review", "SEO", "already Telegram-alerts on breach"),
    ("Precompute indexed price data (monthly)", "Market Intelligence", "Market Metrics tab"),
    ("SQM asking prices (monthly)", "Market Intelligence", "Market Metrics tab (Asking $/sqm)"),
    ("Absorption rate snapshot refresh (monthly)", "Market Intelligence", "Market Metrics tab"),
    ("ABS market signals fetch (weekly)", "Market Intelligence", "Market Signals Fetch tab"),
    ("Macro indicators fetch (weekly)", "Market Intelligence", "Market Signals Fetch tab"),
    ("FB lead ad puller (every 15min)", "Leads/CRM", "already Telegram-alerts always"),
    ("Hot lead responder (every 10min)", "Leads/CRM", "already Telegram-alerts always"),
    ("Live Leads / Sold / Listed → Sheet", "Leads/CRM", "Leads & CRM tab"),
    ("Vertex quota watcher", "Infra", "already Telegram-alerts by design"),
    ("Unpushed-code DR-gap check", "Infra/Backup", "already Telegram-alerts on breach"),
    ("Brain2: lead attribution build", "Leads/CRM", "Leads & CRM tab (adjacent)"),
    ("Compliance nightly", "Compliance", "Ads & Compliance tab"),
    ("API resource health probe", "Infra", "API Health tab (separate, this same sheet)"),
]
_REGISTRY_DISABLED = [
    ("Marketing advisor", "human review required"),
    ("Marketing executor", "human review required"),
    ("FB Content Scheduler (morning/evening)", "2026-04-09 — manual posting now (see facebook_organic_strategy_shift)"),
    ("FB Attribution Builder", "2026-03-19 — replaced by PostHog"),
    ("Website daily metrics collector", "2026-03-19 — replaced by PostHog"),
    ("CEO context export", "2026-04-09 — autonomous agent cleanup"),
    ("CEO Agent launcher", "2026-03-31 — replaced by Worker Agent, then retired"),
    ("Sync-memory-to-codex", "2026-03-31 — Codex agents stopped"),
    ("Todo reminder digest", "2026-04-09 — autonomous agent cleanup"),
    ("Email triage check", "2026-04-09 — autonomous agent cleanup"),
    ("Worker Agent", "2026-04-27 — autonomous Worker Agent retired"),
    ("Samantha nightly", "2026-07-19 — on-demand only"),
    ("Lead-intelligence pipeline", "2026-07-19 — on-demand only, feeds Samantha"),
    ("Mini-Site Health → Sheet (standalone cron)", "merged into Main Site Health's 01:00 run — see Mini-Site tabs"),
]
_REGISTRY_SYSTEMD_UNITS = [
    "fields-orchestrator", "fields-watchdog", "fields-trigger-poller", "fields-valuation-api",
    "fields-valuation-poller", "fields-ceo-telegram", "fields-builder-telegram",
    "fields-ai-analysis-poller", "fields-appraisal-poller", "fields-bridge-sync",
    "fields-offmarket-intel-poller", "fields-offmarket-processor", "fields-property-report-poller",
    "fields-tracking", "fields-voice-agent",
]


def collect_process_registry(add):
    """One row per every cron job / systemd daemon found in the 2026-07-22
    fleet-wide audit — the master 'is every business process accounted for'
    view. Jobs with a real DB/Sheet/API side effect are checked in detail on
    their own tab; this either points there or, for the ~30 log-only jobs
    with no other check anywhere, falls back to log-freshness."""
    PG = "Process Registry"
    orch_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for name, category, log_name, cadence_days in _REGISTRY_LOG_JOBS:
        log_path = log_name if log_name.startswith("/") else os.path.join(orch_dir, "logs", log_name)
        st, dt, mtime = log_freshness_check(log_path, cadence_days)
        add(PG, name, category, mtime.date().isoformat() if mtime else None, st, "log mtime", mtime, dt)

    for name, category, note in _REGISTRY_ALREADY_COVERED:
        add(PG, name, category, "see referenced tab", OK, "", None, note, info=True)

    for name, reason in _REGISTRY_DISABLED:
        add(PG, name, "Disabled", "disabled", GAP, "", None, reason, info=True)

    for unit in _REGISTRY_SYSTEMD_UNITS:
        state, err = systemctl_is_active(unit)
        if err:
            add(PG, unit, "Daemon (systemd)", None, UNKNOWN, "", None, f"could not query systemctl: {err}")
        elif state == "active":
            add(PG, unit, "Daemon (systemd)", "active", OK, "", None, "")
        else:
            add(PG, unit, "Daemon (systemd)", state, ERROR, "", None,
                f"expected always-on, systemctl reports '{state}'")

    # Meta: this checker's own run + the independent watchdog that verifies it.
    # Deliberately NOT a self-referential "this sheet, self-evidently running"
    # row (that was a no-op — if this script crashes before writing anything,
    # that row never gets written either, so it can never actually fire).
    # This reads check_systems_health_ran.py's own log — a SEPARATE script,
    # on a SEPARATE cron (07:00 AEST, 6h after this one), that checks both
    # this job's log AND the Sheet's own Drive modifiedTime, and Telegrams
    # directly on failure without importing anything from this file. If this
    # script itself crashes before reaching this point, THAT alert path is
    # what tells Will — not this row (added 2026-07-22, flagged as a real
    # gap: "does the checker check itself?").
    st, dt, mtime = log_freshness_check(
        os.path.join(orch_dir, "logs", "systems-health-runcheck.log"), 1.5,
        error_patterns=("Traceback (most recent call last)", "FAIL", "FATAL"))
    add(PG, "Fields Systems Health run-check (watchdog)", "Meta",
        mtime.date().isoformat() if mtime else None, st, "log mtime", mtime, dt)

    runner_data, err = gh_api("repos/Will954633/fields-automation/actions/runners")
    if err or runner_data is None:
        add(PG, "GitHub Actions self-hosted runner", "Off-VM automation", None, UNKNOWN, "", None,
            f"could not query runner status: {err}")
    else:
        runners = runner_data.get("runners", [])
        online = [r for r in runners if r.get("status") == "online"]
        if not runners:
            add(PG, "GitHub Actions self-hosted runner", "Off-VM automation", "no runner registered",
                ERROR, "", None, "all 14 GitHub Actions workflows depend on this runner")
        elif not online:
            add(PG, "GitHub Actions self-hosted runner", "Off-VM automation",
                f"{len(runners)} registered, 0 online", ERROR, "", None,
                "all 14 GitHub Actions workflows depend on this runner")
        else:
            add(PG, "GitHub Actions self-hosted runner", "Off-VM automation",
                f"{len(online)}/{len(runners)} online", OK, "", None, "")


# ---- collectors (one per data-point group) ------------------------------------
def collect(client, now_utc, prev_map):
    gc = client["Gold_Coast"]
    sm = client["system_monitor"]
    last_run = expected_last_run(now_utc)
    rows = []

    def add(*a, **k):
        rows.append(mk_row(*a, now_utc=now_utc, prev_map=prev_map, **k))

    # ----- Market Metrics: per-suburb precomputed (nightly) -----
    PG = "Market Metrics"
    for s in SUBS:
        # precompute_indexed_price_data.py runs monthly (1st @ 05:00 AEST), not
        # nightly — judging it against a nightly cadence made this row cry STALE
        # almost every day of the month and couldn't distinguish "ran on
        # schedule" from "actually stuck a quarter behind" (2026-07-22 audit).
        d = gc["precomputed_indexed_prices"].find_one(
            {"_id": s}, {"last_updated": 1, "latest_price": 1, "indexed_series": 1})
        if not d:
            add(PG, "Indexed prices", suburb_label(s), None, MISSING, "last_updated", None, "doc absent")
        else:
            ts = as_dt(d.get("last_updated"))
            st, dt = judge(ts, "monthly", now_utc, last_run)
            add(PG, "Indexed prices", suburb_label(s), f"median ${d.get('latest_price')}", st, "last_updated", ts, dt)

            # Quarter-completeness: does the precomputed series actually contain
            # the latest quarter that raw sold data can support? Catches the
            # exact "stuck at Q1 2026 despite running nightly/monthly" failure
            # mode — a freshness-only check can't tell "ran fine" apart from
            # "ran, but its own quarter-selection logic silently didn't advance."
            series = d.get("indexed_series") or []
            latest_complete_period = series[-1]["period"] if series else None
            # Two quarters back, not one: precompute_indexed_price_data.py sources
            # from property_timeline, which is refreshed by a SEPARATE weekly
            # job (refresh_property_timelines.py). A 2026-07-22 investigation
            # ([INDEXED-PRICE-Q2-LAG]) first assumed this gap was normal Domain
            # publishing lag — WRONG, corrected same day in fix-history
            # [PROPERTY-TIMELINE-REFRESH-DEAD]: the real cause was our own
            # refresh cron never having run once (a crontab `cd` bug) plus the
            # scraper being bot-blocked, both now fixed. Keeping a 2-quarter
            # grace window anyway, for now: property_timeline is only weekly-
            # refreshed and indexed_prices only monthly-precomputed, so a
            # 1-quarter gap can still be legitimate pipeline cadence, not a
            # stall — and the refresh fix above hasn't yet run a full cycle to
            # prove it stays caught up. Revisit narrowing this to 1 quarter
            # once refresh_property_timelines.py has run cleanly for a few
            # weeks (check Process Registry's "Property timeline refresh"
            # row — it was MISSING/never-run until 2026-07-22's fix).
            cy, cq = now_utc.year, (now_utc.month - 1) // 3 + 1
            py, pq = (cy - 1, cq + 2) if cq <= 2 else (cy, cq - 2)
            expected_label = f"Q{pq} {py}"
            q_end_month = pq * 3
            q_end_day = 31 if q_end_month in (3, 12) else 30
            # sold_date is stored as a plain "YYYY-MM-DD" string, not a BSON
            # date (confirmed by direct query — a datetime-range query here
            # silently matched zero documents, which would have made this
            # check permanently unable to detect the exact bug it exists for).
            # ISO-format strings sort lexicographically same as chronologically,
            # so plain string comparison is correct.
            q_start_s = f"{py:04d}-{(pq - 1) * 3 + 1:02d}-01"
            q_end_s = f"{py:04d}-{q_end_month:02d}-{q_end_day:02d}"
            try:
                raw_cnt = gc[s].count_documents(
                    {"listing_status": "sold", "sold_date": {"$gte": q_start_s, "$lte": q_end_s}})
            except Exception:
                raw_cnt = None
            if raw_cnt is not None and raw_cnt >= 3 and latest_complete_period != expected_label:
                add(PG, "Indexed prices — quarter completeness", suburb_label(s),
                    latest_complete_period or "none", ERROR, "indexed_series[-1].period", ts,
                    f"raw sold data has {raw_cnt} sales in {expected_label} but the precomputed "
                    f"series' latest complete quarter is {latest_complete_period or 'none'}")
            elif raw_cnt is not None:
                add(PG, "Indexed prices — quarter completeness", suburb_label(s),
                    latest_complete_period or "none", OK, "indexed_series[-1].period", ts, "")

    for s in SUBS:
        for ct in CHART_TYPES:
            proj = {"last_updated": 1}
            if ct == "sales_volume":
                proj["timeline"] = 1
            d = gc["precomputed_market_charts"].find_one({"_id": f"{s}_{ct}"}, proj)
            label = ct.replace("_", " ")
            if not d:
                add(PG, f"Chart: {label}", suburb_label(s), None, MISSING, "last_updated", None, "doc absent")
            else:
                ts = as_dt(d.get("last_updated"))
                st, dt = judge(ts, "nightly", now_utc, last_run)
                # market_cycle needs ~2yr of House sales; thin non-core suburbs
                # legitimately can't recompute it (producer returns None, leaves the
                # prior doc). Per coverage policy, treat that as a known gap, not STALE.
                if ct == "market_cycle" and s not in CORE3 and st == STALE:
                    st, dt = GAP, "thin-data non-core suburb (market_cycle needs ~2yr House sales)"
                add(PG, f"Chart: {label}", suburb_label(s), str(ts.date()) if ts else "—", st, "last_updated", ts, dt)

            # In-progress-quarter YoY correctness: comparing a 3-week-old partial
            # quarter's sales count to a full prior-year quarter produces a fake
            # "-90% collapse" (the exact failure the 2026-07-22 audit flagged on
            # Q3 2026) unless the current quarter's point is flagged in_progress
            # with yoy_change suppressed. This verifies the flag on the CURRENT
            # stored doc, independent of whether the producer script's own logic
            # (which already looks correct in source) was in place when it ran.
            if ct == "sales_volume" and d:
                cq_key = f"{now_utc.year}-Q{(now_utc.month - 1) // 3 + 1}"
                timeline = d.get("timeline") or []
                cur_point = next((p for p in timeline if p.get("period") == cq_key), None)
                if cur_point is None:
                    add(PG, "Sales volume — in-progress quarter flag", suburb_label(s), "no current-quarter point",
                        GAP, "", None, f"{cq_key} not yet in timeline (expected once any sale lands)")
                elif not cur_point.get("is_in_progress") or cur_point.get("yoy_change") is not None:
                    add(PG, "Sales volume — in-progress quarter flag", suburb_label(s),
                        f"is_in_progress={cur_point.get('is_in_progress')}, yoy={cur_point.get('yoy_change')}",
                        ERROR, "", None,
                        f"{cq_key} should be flagged in-progress with YoY suppressed — as stored it would "
                        f"render a misleading partial-quarter YoY collapse/spike")
                else:
                    add(PG, "Sales volume — in-progress quarter flag", suburb_label(s), "suppressed correctly",
                        OK, "", None, "")

    for s in SUBS:
        d = gc["precomputed_active_listings"].find_one({"_id": s}, {"last_updated": 1, "snapshots": 1})
        if not d:
            add(PG, "Active listings", suburb_label(s), None, MISSING, "last_updated", None, "doc absent")
        else:
            ts = as_dt(d.get("last_updated"))
            snaps = d.get("snapshots") or []
            st, dt = judge(ts, "nightly", now_utc, last_run)
            if not snaps:
                st, dt = MISSING, "no snapshots"
            add(PG, "Active listings", suburb_label(s), f"{len(snaps)} snapshots", st, "last_updated", ts, dt)

    # ----- Market Metrics: periodic feeds -----
    for s in CORE3:
        d = gc["sqm_asking_prices"].find_one({"_id": s}, {"last_updated": 1, "data_points": 1})
        if not d:
            add(PG, "Asking $/sqm", suburb_label(s), None, MISSING, "last_updated", None, "doc absent")
        else:
            ts = as_dt(d.get("last_updated"))
            st, dt = judge(ts, "weekly", now_utc, last_run)
            add(PG, "Asking $/sqm", suburb_label(s), f"{d.get('data_points')} pts", st, "last_updated", ts, dt)

    d = gc["precomputed_macro_indicators"].find_one({"_id": "macro_indicators"}, {"updated_at": 1})
    ts = as_dt(d.get("updated_at")) if d else None
    st, dt = (judge(ts, "macro", now_utc, last_run) if d else (MISSING, "doc absent"))
    add(PG, "Crash-risk macro indicators", "national", str(ts.date()) if ts else "—", st, "updated_at", ts, dt)

    d = sm["market_signals"].find_one({"_id": "market_signals_latest"}, {"updated_at": 1, "latest_quarter_label": 1})
    ts = as_dt(d.get("updated_at")) if d else None
    st, dt = (judge(ts, "weekly", now_utc, last_run) if d else (MISSING, "doc absent"))
    add(PG, "Market signals (wage/retail)", "all", d.get("latest_quarter_label") if d else "—", st, "updated_at", ts, dt)

    for s in CORE3:
        cur = list(sm["market_pulse"].find({"suburb": s}, {"generated_at": 1, "source": 1})
                   .sort("generated_at", -1).limit(1))
        n = sm["market_pulse"].count_documents({"suburb": s})
        if not cur:
            add(PG, "Market pulse narratives", suburb_label(s), None, MISSING, "generated_at", None, "no docs")
        else:
            ts = as_dt(cur[0].get("generated_at"))
            st, dt = judge(ts, "monthly", now_utc, last_run)
            src = cur[0].get("source", "unknown")
            detail = (dt + "; " if dt else "") + f"source={src}"
            add(PG, "Market pulse narratives", suburb_label(s), f"{n} categories ({src})", st,
                "generated_at", ts, detail)

    # Price-reductions correctness: track_price_changes.py writes both the
    # per-listing price_history array (raw) and a system_monitor.price_change_events
    # summary doc (what generate_market_pulse.py's price_reductions_count reads)
    # in the same run. A 2026-07-22 audit found Burleigh Waters/Varsity Lakes
    # showing 0 reduction events in the pulse despite 148/164 raw listings
    # carrying price_history — existence-only checks never caught this because
    # the summary collection still "existed" and was "fresh", just empty for
    # those two suburbs. This compares raw vs. summary directly.
    for s in CORE3:
        ev_cnt = sm["price_change_events"].count_documents(
            {"suburb": {"$regex": s, "$options": "i"}, "direction": "reduction"})
        raw_with_history = gc[s].count_documents({"price_history.1": {"$exists": True}})
        val = f"{ev_cnt} events / {raw_with_history} listings w/ history"
        if raw_with_history > 0 and ev_cnt == 0:
            add(PG, "Price reductions correctness", suburb_label(s), val, ERROR, "", None,
                f"{raw_with_history} listings have price_history entries but 0 reduction events "
                f"recorded — likely a suburb-name mismatch between price_history and price_change_events")
        else:
            add(PG, "Price reductions correctness", suburb_label(s), val, OK, "", None, "")

    for s in CORE3:
        cur = list(sm["absorption_rate_snapshots"].find({"suburb": s}, {"computed_at": 1, "absorption_rate_months": 1})
                   .sort("computed_at", -1).limit(1))
        if not cur:
            add(PG, "Absorption rate", suburb_label(s), None, MISSING, "computed_at", None, "no snapshot")
        else:
            ts = as_dt(cur[0].get("computed_at"))
            st, dt = judge(ts, "weekly", now_utc, last_run)
            add(PG, "Absorption rate", suburb_label(s), f"{cur[0].get('absorption_rate_months')} mo", st, "computed_at", ts, dt)

    # ----- For Sale / Sold -----
    PG = "For Sale / Sold"
    for s in SUBS:
        nf = list(gc[s].find({"listing_status": "for_sale"}, {"last_updated": 1}).sort("last_updated", -1).limit(1))
        cnt = gc[s].count_documents({"listing_status": "for_sale"})
        if cnt == 0:
            add(PG, "Active listings freshness", suburb_label(s), "0 for sale", MISSING, "last_updated", None, "no for_sale docs")
        else:
            ts = as_dt(nf[0].get("last_updated")) if nf else None
            st, dt = judge(ts, "scrape", now_utc, last_run)
            add(PG, "Active listings freshness", suburb_label(s), f"{cnt} listings", st, "last_updated", ts, dt)

    for s in SUBS:
        ns = list(gc[s].find({"listing_status": "sold", "sold_date": {"$exists": True}}, {"sold_date": 1})
                  .sort("sold_date", -1).limit(1))
        cnt = gc[s].count_documents({"listing_status": "sold"})
        if not ns:
            add(PG, "Recently-sold freshness", suburb_label(s), f"{cnt} sold", MISSING, "sold_date", None, "no sold_date")
        else:
            ts = as_dt(ns[0].get("sold_date"))
            st, dt = judge(ts, "sold", now_utc, last_run)
            add(PG, "Recently-sold freshness", suburb_label(s), f"newest {ts.date() if ts else '—'}", st, "sold_date", ts, dt)

    # ----- Property Page -----
    PG = "Property Page"
    for s in SUBS:
        fs = gc[s].count_documents({"listing_status": "for_sale"})
        valc = gc[s].count_documents({"listing_status": "for_sale", "valuation_data.computed_at": {"$exists": True}})
        nv = list(gc[s].find({"listing_status": "for_sale", "valuation_data.computed_at": {"$exists": True}},
                             {"valuation_data.computed_at": 1}).sort("valuation_data.computed_at", -1).limit(1))
        ts = as_dt(get_path(nv[0], "valuation_data.computed_at")) if nv else None
        cov = round(100 * valc / fs) if fs else 0
        if fs == 0:
            add(PG, "Valuation coverage", suburb_label(s), "no for_sale", MISSING, "valuation_data.computed_at", None, "no listings")
        elif valc == 0:
            add(PG, "Valuation coverage", suburb_label(s), f"0/{fs}", MISSING, "valuation_data.computed_at", None, "no valuations")
        else:
            st, dt = judge(ts, "valuation", now_utc, last_run)
            detail = f"{cov}% coverage" + ("; " + dt if dt else "")
            add(PG, "Valuation coverage", suburb_label(s), f"{valc}/{fs} ({cov}%)", st, "valuation_data.computed_at", ts, detail)

    for s in SUBS:
        fs = gc[s].count_documents({"listing_status": "for_sale"})
        if fs == 0:
            continue
        pub = gc[s].count_documents({"listing_status": "for_sale", "ai_analysis.status": "published"})
        ff = gc[s].count_documents({"listing_status": "for_sale", "ai_analysis.status": "failed_factcheck"})
        rej = gc[s].count_documents({"listing_status": "for_sale", "ai_analysis.status": "rejected"})
        nr = gc[s].count_documents({"listing_status": "for_sale", "ai_analysis.status": "needs_review"})
        nv = list(gc[s].find({"listing_status": "for_sale", "ai_analysis.generated_at": {"$exists": True}},
                             {"ai_analysis.generated_at": 1}).sort("ai_analysis.generated_at", -1).limit(1))
        ts = as_dt(get_path(nv[0], "ai_analysis.generated_at")) if nv else None
        # ERROR only on failed_factcheck (a real pipeline defect); rejected is a
        # deliberate human action, surfaced in detail but not an alarm.
        if ff > 0:
            st, dt, info = ERROR, f"{ff} failed_factcheck" + (f", {rej} rejected" if rej else ""), False
        else:
            st, dt, info = OK, (f"{rej} rejected" if rej else ""), True
        val = f"pub {pub} / review {nr} / fail {ff} / rej {rej}"
        add(PG, "AI editorial status", suburb_label(s), val, st, "ai_analysis.generated_at", ts, dt, info=info)

    # live-computed endpoints -> Known Gaps page (below)

    # ----- Articles -----
    PG = "Articles"
    pub_total = sm["content_articles"].count_documents({"status": "published"})
    draft_total = sm["content_articles"].count_documents({"status": "draft"})
    # Generation cadence (newest created_at, any status) is the health signal: articles
    # are created as drafts behind an editorial review gate, so "generation working"
    # — not "publishing" — is what catches CI breakage. Publishing is a manual step.
    ng = list(sm["content_articles"].find({}, {"created_at": 1}).sort("created_at", -1).limit(1))
    ts = as_dt(ng[0].get("created_at")) if ng else None
    if not ng:
        add(PG, "Article generation cadence", "all", "no articles", MISSING, "created_at", None, "empty collection")
    else:
        st, dt = judge(ts, "weekly", now_utc, last_run)
        add(PG, "Article generation cadence", "all", f"newest {ts.date() if ts else '—'}", st, "created_at", ts, dt)
    npb = list(sm["content_articles"].find({"status": "published"}, {"published_at": 1}).sort("published_at", -1).limit(1))
    pts = as_dt(npb[0].get("published_at")) if npb else None
    add(PG, "Newest published", "all", str(pts.date()) if pts else "—", OK, "published_at", pts,
        "manual editorial publish step (info)", info=True)
    add(PG, "Published / draft counts", "all", f"{pub_total} published / {draft_total} draft", OK, "", None,
        "draft backlog awaiting review (info)", info=True)

    # ----- Valuation Accuracy -----
    PG = "Valuation Accuracy"
    d = sm["valuation_accuracy"].find_one({"type": "summary"}, {"run_date": 1, "total_tested": 1})
    ts = as_dt(d.get("run_date")) if d else None
    if not d:
        add(PG, "Backtest summary", "model", None, MISSING, "run_date", None, "no summary doc")
    else:
        st, dt = judge(ts, "monthly", now_utc, last_run)
        add(PG, "Backtest summary", "model", f"{d.get('total_tested')} tested", st, "run_date", ts, dt)

    # ----- Pipeline Processes (orchestrator steps, provider credit, coverage) -----
    # Added 2026-06-11: data-freshness rows alone hid process failures — the
    # June quota outage (steps 105/106/108/117 down 4 nights) and step timeouts
    # (101/103/113) never surfaced on the sheet. This page reads the per-step
    # result.json files from the latest run, probes both vision providers'
    # credit, and mirrors step 109's Domain-vs-DB coverage verdicts.
    PG = "Pipeline Processes"
    runs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "logs", "runs")
    try:
        run_dirs = sorted(d for d in os.listdir(runs_dir)
                          if os.path.isdir(os.path.join(runs_dir, d)) and not d.startswith("."))
    except OSError:
        run_dirs = []

    if not run_dirs:
        add(PG, "Nightly run", "orchestrator", None, MISSING, "", None, "no run logs found")
    else:
        latest = run_dirs[-1]
        run_id, _, run_suffix = latest.rpartition("_")
        run_id = run_id or latest
        try:
            run_start = datetime.strptime(run_id, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=AEST).astimezone(timezone.utc)
        except ValueError:
            run_start = None

        # Recency: the newest run must be from the most recent expected 20:30 trigger.
        if run_start is not None and run_start < last_run - timedelta(minutes=30):
            add(PG, "Nightly run recency", "orchestrator", run_id, ERROR, "run_start", run_start,
                f"no run since expected {last_run.astimezone(AEST):%Y-%m-%d %H:%M} AEST — daemon down?")

        run_dir = os.path.join(runs_dir, latest)
        finished = os.path.exists(os.path.join(run_dir, "run_summary.json"))
        n_ok, failed_steps = 0, []
        for step_dir in sorted(os.listdir(run_dir)):
            rp = os.path.join(run_dir, step_dir, "result.json")
            if not os.path.exists(rp):
                continue
            try:
                with open(rp) as fh:
                    j = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if j.get("success"):
                n_ok += 1
            else:
                failed_steps.append(j)

        run_val = f"{n_ok} ok / {len(failed_steps)} failed" + ("" if finished else " (still running)")
        if failed_steps or run_suffix == "failed":
            run_st, run_dt = ERROR, f"run {run_suffix or 'in progress'}"
        elif not finished:
            run_st, run_dt = UNKNOWN, "run still in progress at audit time"
        else:
            run_st, run_dt = OK, ""
        add(PG, "Nightly run", run_id, run_val, run_st, "run_start", run_start, run_dt)

        for j in failed_steps:
            dur = j.get("duration_seconds") or 0
            err = (j.get("error_message") or "").strip() or "no error message"
            add(PG, f"Step {j.get('step_id')}", j.get("step_name") or "?",
                f"{j.get('attempts')} attempts, {int(dur)}s", ERROR, "end_time",
                as_dt(j.get("end_time")), err[:160])

    # Vision provider credit — Claude is the primary engine for steps
    # 105/106/108/112/117 since 2026-06; OpenAI is a dormant fallback only,
    # so it is reported as info (visible, not alarmed).
    try:
        import api_health_monitor as ahm
        a_st, a_det, _ = ahm.probe_anthropic("ANTHROPIC_API_KEY")
        add(PG, "Vision provider", "Anthropic (primary)", a_st,
            OK if a_st == "OK" else ERROR, "", None,
            a_det if a_st != "OK" else "")
        o_st, o_det, _ = ahm.probe_openai("OPENAI_API_KEY")
        add(PG, "Vision provider", "OpenAI (fallback only)", o_st, OK, "", None,
            (o_det or "") + " — fallback only, not alarmed", info=True)
    except Exception as e:  # probe import/network failure must not kill the audit
        add(PG, "Vision provider", "probe", None, UNKNOWN, "", None, f"probe failed: {e}")

    # Coverage verdicts (step 109: live Domain count vs our DB count, via
    # write-scraper-health). critical = Domain shows listings we don't have.
    latest_check = sm["scraper_health"].find_one(sort=[("checked_at", -1)])
    if not latest_check:
        add(PG, "Coverage check", "all", None, MISSING, "checked_at", None, "no scraper_health docs")
    else:
        batch_ts = latest_check["checked_at"]
        cov_map = {"healthy": OK, "warn": STALE, "critical": ERROR}
        for d in sm["scraper_health"].find({"checked_at": batch_ts}).sort("suburb", 1):
            ts = as_dt(d.get("checked_at"))
            age_h = (now_utc - ts).total_seconds() / 3600 if ts else None
            st = cov_map.get(d.get("status"), UNKNOWN)
            detail = ""
            if st == ERROR:
                detail = "Domain shows listings missing from DB (or scrape stale) — see coverage_check.log"
            elif st == STALE:
                detail = "minor count drift vs Domain"
            if age_h is not None and age_h > 26:
                st = max((st, STALE), key=lambda x: SEVERITY[x])
                detail = (detail + "; " if detail else "") + f"check itself stale ({age_h:.0f}h old)"
            add(PG, "Coverage vs Domain", suburb_label(d.get("suburb", "?")),
                f"{d.get('total_listings', '—')} listings", st, "checked_at", ts, detail)

    # ----- Sitemap: daily VM-cron push actually landing on GitHub -----
    # (regenerate-sitemap.sh runs 06:15 AEST; this only checks the push
    # SUCCEEDED, not whether Google has crawled it — see seo_indexation_check.py
    # for the GSC-side readout, which is a separate weekly job.)
    PG = "Sitemap"
    for path in SITEMAP_FILES:
        ts, sha, err = last_commit_for_path(SITEMAP_REPO, path)
        if err:
            add(PG, "Daily push (VM cron)", path, None, ERROR, "commit date", None,
                f"could not check GitHub: {err}")
            continue
        st, dt = judge(ts, "scrape", now_utc, last_run)
        add(PG, "Daily push (VM cron)", path, f"commit {sha}", st, "commit date", ts, dt)

    # ----- Known Gaps (structural; documented, not alarms) -----
    PG = "Known Gaps"
    for name, scope, note in [
        ("Articles build artifact", "articles.json", "baked at Netlify build; real signal = DB published_at (Articles tab)"),
        ("Decision feed / discover", "/discover, /for-sale-v2", "response last_updated = request time; real signal = suburb scrape (For Sale tab)"),
        ("Property insights", "/property/:id", "computed live per request; real signal = suburb scrape"),
        ("Active competition", "/property/:id", "live query; no freshness signal; real signal = suburb scrape"),
        ("Price forecast JSON", "/data/forecast_*.json", "build artifact; no computed_at in payload"),
        ("Crash-risk narrative", "CrashRiskSection.tsx", "hardcoded claims; manual update (CLAUDE.md monthly check)"),
    ]:
        add(PG, name, scope, "structural gap", GAP, "", None, note, note=note)

    # ----- Business-wide additions (2026-07-22) -----
    # Each wrapped individually: these are the newest, least-battle-tested
    # collectors in this file (gh api subprocess calls, systemctl calls, new
    # Mongo queries) — a bug in any ONE of them must not take down the entire
    # audit and silently produce zero rows for every other page. That would be
    # exactly the failure class this whole system exists to catch, just moved
    # one level up into the checker itself.
    for page_name, fn, fn_args in [
        ("Process Registry", collect_process_registry, (add,)),
        ("GitHub Actions", collect_github_actions, (add,)),
        ("Market Signals Fetch", collect_market_signals_fetch, (add, sm, now_utc)),
        ("Leads & CRM", collect_leads_crm, (add, sm, now_utc, last_run)),
        ("Ads & Compliance", collect_ads_compliance, (add, sm, now_utc)),
    ]:
        try:
            fn(*fn_args)
        except Exception as e:
            add(page_name, "collector crashed", "", None, ERROR, "", None,
                f"{type(e).__name__}: {e}"[:200])

    return rows


# ---- audit assembly -----------------------------------------------------------
def get_mongo_client():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("COSMOS_CONNECTION_STRING="):
                    conn = line.split("=", 1)[1].strip().strip('"')
                    break
    return MongoClient(conn)


def run_audit(client=None, persist=True):
    """Audit all main-site data points. Returns (pages, now_utc, totals).

    pages: list of {page, health_pct, counts, worst_severity, oldest_fresh, rows[]}
    sorted in PAGES order. Shared by the CLI and the Google Sheet builder.
    """
    own = client is None
    if own:
        client = get_mongo_client()
    snaps = client["system_monitor"]["mainsite_health_snapshots"]
    now_utc = datetime.now(timezone.utc)

    prev = snaps.find_one(sort=[("run_at", -1)])
    prev_map = (prev or {}).get("fields", {})

    rows = collect(client, now_utc, prev_map)

    # group by page in PAGES order
    pages = []
    totals = {}
    for pg in PAGES:
        prows = [r for r in rows if r["page"] == pg]
        if not prows:
            continue
        core = [r for r in prows if not r["info"] and r["status"] != GAP]
        counts = {}
        for r in prows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            totals[r["status"]] = totals.get(r["status"], 0) + 1
        ok_core = sum(1 for r in core if r["status"] == OK)
        health = round(100 * ok_core / len(core)) if core else 100
        worst = max((SEVERITY[r["status"]] for r in core), default=0)
        fresh_dates = [r["freshness_ts"] for r in prows if r["freshness_ts"]]
        oldest = min(fresh_dates) if fresh_dates else None
        # sort rows worst-first within the page
        prows.sort(key=lambda r: (-SEVERITY[r["status"]], r["name"], r["scope"]))
        pages.append({"page": pg, "health_pct": health, "counts": counts,
                      "worst_severity": worst, "oldest_fresh": oldest, "rows": prows})

    if persist:
        snaps.insert_one({
            "run_at": now_utc,
            "overall_health_pct": round(100 * totals.get(OK, 0) /
                                        max(1, sum(v for k, v in totals.items() if k != GAP))),
            "counts": totals,
            "pages": {p["page"]: {"health_pct": p["health_pct"], "counts": p["counts"]} for p in pages},
            "fields": {r["key"]: {"value_hash": r["value_hash"], "status": r["status"],
                                  "last_changed": r["last_changed"]} for r in rows},
        })

    if own:
        client.close()
    return pages, now_utc, totals


# ---- CLI ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--no-snapshot", action="store_true")
    args = ap.parse_args()

    pages, now_utc, totals = run_audit(persist=not args.no_snapshot)
    print(f"\nMain-site health — {now_utc.astimezone(AEST):%Y-%m-%d %H:%M AEST}")
    print(f"Expected last nightly run: {expected_last_run(now_utc).astimezone(AEST):%Y-%m-%d %H:%M AEST}\n")
    print(f"{'PAGE':<22} {'HEALTH':>6}  {'ERR':>3} {'MIS':>3} {'STA':>3} {'UNK':>3} {'GAP':>3}")
    for p in pages:
        c = p["counts"]
        print(f"{p['page']:<22} {p['health_pct']:>5}%  {c.get(ERROR,0):>3} {c.get(MISSING,0):>3} "
              f"{c.get(STALE,0):>3} {c.get(UNKNOWN,0):>3} {c.get(GAP,0):>3}")
    print(f"\nTOTALS: " + "  ".join(f"{k}={v}" for k, v in sorted(totals.items())))

    problems = [r for p in pages for r in p["rows"] if r["status"] in (ERROR, MISSING, STALE)]
    if problems:
        print(f"\n--- {len(problems)} non-OK data points (ERROR/MISSING/STALE) ---")
        for r in problems:
            print(f"  [{r['status']:<7}] {r['page']:<18} {r['name']} · {r['scope']}: {r['detail']}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(pages, fh, indent=2, default=str)
        print(f"\nFull results → {args.json}")


if __name__ == "__main__":
    main()

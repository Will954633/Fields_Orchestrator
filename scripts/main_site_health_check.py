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
PAGES = ["Market Metrics", "For Sale / Sold", "Property Page",
         "Articles", "Valuation Accuracy", "Known Gaps"]


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
        d = gc["precomputed_indexed_prices"].find_one({"_id": s}, {"last_updated": 1, "latest_price": 1})
        if not d:
            add(PG, "Indexed prices", suburb_label(s), None, MISSING, "last_updated", None, "doc absent")
        else:
            ts = as_dt(d.get("last_updated"))
            st, dt = judge(ts, "nightly", now_utc, last_run)
            add(PG, "Indexed prices", suburb_label(s), f"median ${d.get('latest_price')}", st, "last_updated", ts, dt)

    for s in SUBS:
        for ct in CHART_TYPES:
            d = gc["precomputed_market_charts"].find_one({"_id": f"{s}_{ct}"}, {"last_updated": 1})
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
        cur = list(sm["market_pulse"].find({"suburb": s}, {"generated_at": 1}).sort("generated_at", -1).limit(1))
        n = sm["market_pulse"].count_documents({"suburb": s})
        if not cur:
            add(PG, "Market pulse narratives", suburb_label(s), None, MISSING, "generated_at", None, "no docs")
        else:
            ts = as_dt(cur[0].get("generated_at"))
            st, dt = judge(ts, "monthly", now_utc, last_run)
            add(PG, "Market pulse narratives", suburb_label(s), f"{n} categories", st, "generated_at", ts, dt)

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

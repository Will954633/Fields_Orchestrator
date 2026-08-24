#!/usr/bin/env python3
"""
update_labour_context.py -- pull QLD/NSW/VIC labour-market figures from the ABS
Data API and write labour_context.json for the owner-subject article's jobs leg.

The article's Q3 ("why is the Gold Coast holding up") leans on three ABS series,
all retrieved live from https://data.api.abs.gov.au (no key, CSV):

  * Unemployment rate, monthly (LF/M13) -- we compute a 3-MONTH ROLLING average
    per state (a single month is too volatile to print) and also carry the ABS
    TREND value, which is already smoothed.
  * Employed persons, monthly (LF/M3) -- year-on-year change = jobs added.
  * Job vacancies, quarterly (JV/M1) -- converted to vacancies per 1,000 employed
    (per-capita), the one labour measure on which Queensland leads BOTH southern
    capitals; absolute counts just track state size and would mislead.

Everything here is real ABS data with its reference period recorded, so the copy
can cite it. Unlike the Cotality macro block (human-maintained), this refreshes
itself from the API.

Self-monitoring (CLAUDE.md Rule 7 + 7b): wrapped in job_run; RAISES if the API
returns nothing for a required series (a silent empty pull must not look healthy).

    python3 update_labour_context.py            # refresh in place
    python3 update_labour_context.py --show
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone

from curl_cffi import requests as cffi

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

OUT_PATH = os.path.join(HERE, "labour_context.json")
API = "https://data.api.abs.gov.au/rest/data"
REGION = {"1": "nsw", "2": "vic", "3": "qld"}     # ABS CL_STATE codes


def _fetch(path: str) -> list[dict]:
    url = f"{API}/{path}"
    r = cffi.get(url, impersonate="chrome120", timeout=60,
                 headers={"Accept": "application/vnd.sdmx.data+csv"})
    if r.status_code == 404:                       # ABS "NoRecordsFound" sentinel
        return []
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def _by_state(rows: list[dict]) -> dict[str, list[tuple[str, float]]]:
    """{state_key: [(period, value), ...] sorted by period}."""
    out: dict[str, list] = {}
    for row in rows:
        # Labour Force / Job Vacancies use REGION; HSI uses STATE — accept either.
        st = REGION.get(row.get("REGION") or row.get("STATE"))
        if not st:
            continue
        try:
            v = float(row["OBS_VALUE"])
        except (ValueError, KeyError, TypeError):
            continue
        out.setdefault(st, []).append((row["TIME_PERIOD"], v))
    for st in out:
        out[st].sort(key=lambda t: t[0])
    return out


def _month_label(p: str) -> str:
    try:
        return datetime.strptime(p, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return p


def _quarter_label(p: str) -> str:
    # ABS JV periods come as "2026-Q2"; the reference month is the middle of the
    # quarter (Feb/May/Aug/Nov survey). Label by quarter, keep it simple.
    return p.replace("-", " ") if "Q" in p else p


def build() -> dict:
    now = datetime.now(timezone.utc)
    y = now.year
    start_m = f"{y-1}-{now.month:02d}"             # ~13 months back (unemployment)
    start_emp = f"{y-1}-01"                         # >=13 months, for YoY jobs added
    start_q = f"{y-1}-Q1"

    # 1) unemployment rate, seasonally adjusted + trend, monthly
    unemp_sa = _by_state(_fetch(f"LF/M13.3.1599.20.1+2+3.M?startPeriod={start_m}"))
    unemp_tr = _by_state(_fetch(f"LF/M13.3.1599.30.1+2+3.M?startPeriod={start_m}"))
    # 2) employed persons ('000), seasonally adjusted, monthly
    emp = _by_state(_fetch(f"LF/M3.3.1599.20.1+2+3.M?startPeriod={start_emp}"))
    # 3) job vacancies ('000), original, quarterly (state only publishes Original)
    vac = _by_state(_fetch(f"JV/M1.7.TOT.10.1+2+3.Q?startPeriod={start_q}"))
    # 4) Wage Price Index — through-the-year % (MEASURE=3), total hourly rates excl
    #    bonuses, all sectors/industries, Original (SA not published at state level),
    #    quarterly. This is the LEADING indicator in Fields' own price analysis.
    wpi = _by_state(_fetch(f"WPI/3.THRPEB.7.TOT.10.1+2+3.Q?startPeriod={start_q}"))
    #    ...and a longer QLD WPI series for the Section 4 chart (~3 years).
    wpi_series = _by_state(_fetch("WPI/3.THRPEB.7.TOT.10.3.Q?startPeriod=2023-Q3"))
    # 5) Monthly Household Spending Indicator — through-the-year % (MEASURE=9), total
    #    (TOT), current prices (CUR), seasonally adjusted (20), QLD (3), monthly. The
    #    ABS successor to Retail Trade (which is frozen at 2025-06); consumer spending
    #    is the strongest gauge in Fields' price analysis.
    hsi_series = _by_state(_fetch("HSI_M/9.TOT.CUR.20.3.M?startPeriod=2023-06"))

    if not unemp_sa or not emp or not vac:
        raise RuntimeError(
            "ABS returned no data for a required series "
            f"(unemp_sa={bool(unemp_sa)}, emp={bool(emp)}, vac={bool(vac)}) -- "
            "the API shape may have changed; do not write a stale labour block")

    states = {}
    for st in ("qld", "nsw", "vic"):
        s = {}
        # 3-month rolling unemployment (avg of last 3 SA months)
        if unemp_sa.get(st):
            last3 = unemp_sa[st][-3:]
            s["unemp_3mo_avg"] = round(sum(v for _, v in last3) / len(last3), 1)
            s["unemp_3mo_from"] = last3[0][0]
            s["unemp_3mo_to"] = last3[-1][0]
        if unemp_tr.get(st):
            s["unemp_trend"] = round(unemp_tr[st][-1][1], 1)
            s["unemp_trend_period"] = unemp_tr[st][-1][0]
        # jobs added year-on-year (employed level now vs ~12 months earlier), persons
        if emp.get(st) and len(emp[st]) >= 13:
            latest_p, latest_v = emp[st][-1]
            yr_ago_v = emp[st][-13][1]
            s["employed_now_k"] = round(latest_v, 1)
            s["jobs_added_yoy"] = int(round((latest_v - yr_ago_v) * 1000))
            s["employed_period"] = latest_p
        # vacancies per 1,000 employed (per-capita labour demand)
        if vac.get(st) and emp.get(st):
            vp, vv = vac[st][-1]
            s["vacancies_k"] = round(vv, 1)
            s["vacancies_period"] = vp
            emp_now = emp[st][-1][1]
            if emp_now:
                s["vacancies_per_1000_employed"] = round(vv / emp_now * 1000, 1)
        # wage price index, through-the-year % (the leading indicator)
        if wpi.get(st):
            wp, wv = wpi[st][-1]
            s["wpi_yoy"] = round(wv, 1)
            s["wpi_period"] = wp
        states[st] = s

    def _series(by_state, n):
        pts = by_state.get("qld") or []
        return [{"period": p, "value": round(v, 1)} for p, v in pts[-n:]]

    hsi_q = hsi_series.get("qld") or []
    leading = {
        "wpi": {
            "title": "Wage growth, Queensland",
            "subtitle": "Wage Price Index, annual growth (%). A leading indicator of "
                        "Gold Coast prices in our analysis.",
            "series": _series(wpi_series, 11),
            "latest": states["qld"].get("wpi_yoy"),
            "period": _quarter_label(states["qld"].get("wpi_period", "")),
            "source": "ABS Wage Price Index",
        },
        "household_spending": {
            "title": "Household spending, Queensland",
            "subtitle": "Monthly Household Spending Indicator, annual growth (%). Our "
                        "strongest gauge of market strength.",
            "series": _series(hsi_series, 14),
            "latest": round(hsi_q[-1][1], 1) if hsi_q else None,
            "period": _month_label(hsi_q[-1][0]) if hsi_q else "",
            "source": "ABS Monthly Household Spending Indicator",
        },
    }

    return {
        "leading_indicators": leading,
        "_comment": "COMPUTED by update_labour_context.py from the ABS Data API. "
                    "Do not hand-edit. Every figure is real ABS data; cite ABS "
                    "Labour Force (6202.0) for unemployment/employment and Job "
                    "Vacancies (6354.0) for vacancies, with the period shown.",
        "retrieved_at": now.isoformat(timespec="seconds"),
        "source": {
            "unemployment": "ABS Labour Force, Australia (cat. 6202.0)",
            "employment": "ABS Labour Force, Australia (cat. 6202.0)",
            "vacancies": "ABS Job Vacancies, Australia (cat. 6354.0)",
            "wages": "ABS Wage Price Index, Australia (cat. 6345.0)",
            "api": "https://data.api.abs.gov.au",
        },
        "labels": {
            "unemp_period": _month_label(states["qld"].get("unemp_3mo_to", "")),
            "unemp_from": _month_label(states["qld"].get("unemp_3mo_from", "")),
            "vacancies_period": _quarter_label(states["qld"].get("vacancies_period", "")),
            "employed_period": _month_label(states["qld"].get("employed_period", "")),
            "wpi_period": _quarter_label(states["qld"].get("wpi_period", "")),
        },
        "states": states,
    }


def run(show: bool = False) -> dict:
    data = build()
    with open(OUT_PATH, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    if show:
        print(json.dumps(data, indent=2))
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--no-heartbeat", action="store_true")
    a = ap.parse_args()

    if a.no_heartbeat:
        d = run(a.show)
        q = d["states"]["qld"]
        print(f"QLD: unemp3mo={q.get('unemp_3mo_avg')} "
              f"vac/1k={q.get('vacancies_per_1000_employed')} "
              f"jobs_yoy={q.get('jobs_added_yoy')}", file=sys.stderr)
        return 0

    try:
        from job_status import job_run
    except Exception:
        run(a.show)
        return 0
    with job_run("owner_article_labour_context", cadence_hours=744,
                 title="Owner-article labour context (ABS)") as beat:
        d = run(a.show)
        q = d["states"]["qld"]
        beat.metrics = {
            "qld_unemp_3mo": q.get("unemp_3mo_avg"),
            "qld_vac_per_1000": q.get("vacancies_per_1000_employed"),
            "qld_jobs_yoy": q.get("jobs_added_yoy"),
        }
        beat.detail = (f"QLD unemp {q.get('unemp_3mo_avg')}%, "
                       f"vac/1k {q.get('vacancies_per_1000_employed')}, "
                       f"+{q.get('jobs_added_yoy')} jobs yoy")
    return 0


if __name__ == "__main__":
    sys.exit(main())

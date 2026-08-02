#!/usr/bin/env python3
"""
homeowner_mindset.py — shared access to the Gold Coast homeowner mindset report.

WHAT THIS IS FOR
The monthly Market Pulse prose must be written for the psychological state of an actual
homeowner in the target market — what they are seeing, worrying about, and being influenced by —
not just for the numbers. That state lives in a researched brief under
`15_Off-Market/Home_Owner_Perspective/`. Other processes (the market update report) draw on the
same brief, so it lives here rather than inside any one script.

WHY THE FRESHNESS GATE EXISTS (2026-08-02)
The first report (30 July 2026) was written while `precomputed_indexed_prices` was being reverted
nightly to raw values, so its `[FIELDS]` layer carried figures that do not exist in the corrected
data — it reported a 16% Burleigh Waters retreat off a peak that was never there, against an
actual 4.9% move on a quarter flagged `reliable: false`. Its central psychological read for that
suburb was built on a data bug. A brief that shapes 21 public summaries has to be checked for age,
and its Fields-sourced numbers have to come from the live database rather than be restated from
memory. See fix-history [UNION-MEDIANS-REVERTED-NIGHTLY].

The report is a STRATEGY BRIEF, NOT PUBLIC CONTENT. It informs which facts are worth surfacing and
how to frame their relevance. It never licenses advice, prediction, or persuasion — the standing
editorial rules (no advice, no forecasts, no single valuation in headlines) override it in all
cases, and the report's own "What we deliberately did NOT conclude" section is binding.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "15_Off-Market", "Home_Owner_Perspective",
)
STALE_AFTER_DAYS = 90
REFRESH_COMMAND = "python3 scripts/refresh_homeowner_mindset.py"

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
DISPLAY_NAMES = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}


def _report_date(path: str):
    """Prefer a date in the document ('· 30 July 2026 ·'), fall back to file mtime."""
    try:
        with open(path, encoding="utf-8") as fh:
            head = fh.read(2000)
        m = re.search(r"·\s*(\d{1,2}\s+\w+\s+20\d\d)\s*·", head)
        if m:
            for fmt in ("%d %B %Y", "%d %b %Y"):
                try:
                    return datetime.strptime(m.group(1), fmt)
                except ValueError:
                    continue
    except OSError:
        pass
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def latest_report():
    """Newest mindset report as {path, date, age_days, is_stale, text} — or None if none exist."""
    if not os.path.isdir(REPORT_DIR):
        return None
    candidates = [
        os.path.join(REPORT_DIR, f)
        for f in os.listdir(REPORT_DIR)
        if f.endswith(".md") and not f.startswith(".")
    ]
    if not candidates:
        return None

    dated = [(p, _report_date(p)) for p in candidates]
    dated = [(p, d) for p, d in dated if d]
    if not dated:
        return None
    path, date = max(dated, key=lambda t: t[1])

    age = (datetime.now() - date).days
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return {
        "path": path,
        "date": date,
        "age_days": age,
        "is_stale": age > STALE_AFTER_DAYS,
        "text": text,
    }


def check_freshness(verbose: bool = True):
    """
    Report status without blocking. Returns (report_or_None, status_string).

    Deliberately non-blocking: a stale brief must not stop the monthly cycle — last month's
    prose staying frozen on the live pages is worse than prose written from a slightly dated
    psychological read. It warns loudly and surfaces the refresh command instead.
    """
    rep = latest_report()
    if rep is None:
        if verbose:
            print("  ⚠️  NO homeowner mindset report found in "
                  f"{os.path.relpath(REPORT_DIR)}")
            print(f"      Prose will be written WITHOUT homeowner-psychology framing.")
            print(f"      Produce one:  {REFRESH_COMMAND}")
        return None, "missing"

    if rep["is_stale"]:
        if verbose:
            print(f"  ⚠️  Homeowner mindset report is STALE — {rep['age_days']} days old "
                  f"(threshold {STALE_AFTER_DAYS})")
            print(f"      {os.path.basename(rep['path'])} ({rep['date']:%d %b %Y})")
            print(f"      Refresh:  {REFRESH_COMMAND}")
        return rep, "stale"

    if verbose:
        print(f"  Homeowner mindset report: {os.path.basename(rep['path'])} "
              f"({rep['age_days']}d old) — OK")
    return rep, "ok"


def fields_data_pack(gc_db) -> str:
    """
    The suburb figures the brief is allowed to cite, straight from the live corrected data.

    The 30 July report invented/restated Fields figures that did not match the database. Any
    process producing or refreshing this brief must be handed this block and told to use it
    verbatim for every Fields-sourced claim. Reliability flags are included because a quarterly
    median flagged `reliable: false` cannot support a quarter-on-quarter narrative — which is
    precisely the mistake the first report made.
    """
    lines = [
        "FIELDS LIVE DATA — use these figures verbatim for any [FIELDS] claim.",
        "Do NOT compute, round, or restate suburb figures from any other source.",
        "",
    ]
    for s in TARGET_SUBURBS:
        doc = gc_db["precomputed_indexed_prices"].find_one({"_id": s})
        if not doc:
            lines.append(f"## {DISPLAY_NAMES.get(s, s)}: NO DATA")
            continue
        lines.append(f"## {DISPLAY_NAMES.get(s, s)}")
        med = doc.get("rolling_12m_median_price")
        if med:
            lines.append(
                f"- 12-month median (THE headline median): ${med:,.0f} "
                f"(90% CI ${doc.get('rolling_12m_ci_low', 0):,.0f}-${doc.get('rolling_12m_ci_high', 0):,.0f}, "
                f"n={doc.get('rolling_12m_median_sample_n')}, source={doc.get('median_source')})"
            )
        if doc.get("rolling_12m_yoy_pct") is not None:
            lines.append(f"- Year-on-year: {doc['rolling_12m_yoy_pct']:+.1f}% "
                         f"(rolling 12 months vs the prior 12 months)")

        recent = [q for q in (doc.get("indexed_series") or [])
                  if str(q.get("period", "")).split()[-1] in ("2025", "2026")]
        if recent:
            lines.append("- Quarterly medians (RELIABLE flag = is the CI narrow enough to "
                         "support a quarter-on-quarter claim at all):")
            for q in recent:
                lines.append(
                    f"    {q.get('period'):8} ${q.get('median_price', 0):>10,.0f}  "
                    f"reliable={q.get('reliable')}  n={q.get('median_sample_n')}"
                )
            unreliable = [q.get("period") for q in recent if q.get("reliable") is False]
            if unreliable:
                lines.append(f"    -> DO NOT narrate a QoQ move from: {', '.join(unreliable)}")

        vol = gc_db["precomputed_market_charts"].find_one({"_id": f"{s}_sales_volume"})
        if vol:
            tl = [t for t in (vol.get("timeline") or []) if not t.get("is_in_progress")][-6:]
            if tl:
                lines.append("- Sales volume (the more reliable signal than any single median):")
                lines.append("    " + ", ".join(
                    f"{t.get('period')} {t.get('sales_count')}" for t in tl))

        dom = gc_db["precomputed_market_charts"].find_one({"_id": f"{s}_days_on_market"})
        if dom:
            tl = dom.get("dom_timeline", dom.get("timeline", []))
            if tl:
                latest = tl[-1]
                lines.append(f"- Days on market: {latest.get('median_days_on_market')} median "
                             f"({latest.get('period')})")
        lines.append("")
    return "\n".join(lines)


def digest_guardrails() -> str:
    """Non-negotiable constraints when the brief is used to shape public content."""
    return (
        "BINDING CONSTRAINTS when using the homeowner mindset brief:\n"
        "- The brief is INTERNAL strategy. Never quote it, never reveal that we profile seller "
        "psychology, never write copy that reads as persuasion.\n"
        "- It informs WHICH facts are worth surfacing and how to frame their relevance. It does "
        "not license advice ('now is a good time'), prediction, or urgency.\n"
        "- The brief's own 'What we deliberately did NOT conclude' list is binding: do not assert "
        "high seller optimism, a single Gold-Coast-wide median, a precise days-on-market figure, "
        "a migration direction, or specific CGT rules.\n"
        "- Claims tagged [INFERRED] in the brief are unverified behavioural reads. They may shape "
        "emphasis. They must never appear as stated fact in public content.\n"
        "- Where the brief and the live data disagree, the LIVE DATA WINS, always.\n"
        "- Where the brief's MESSAGING section and its 'did NOT conclude' section disagree, the "
        "'did NOT conclude' section WINS. The messaging section is written to be persuasive; the "
        "verification section is written to be true. On 2026-08-02 the messaging section proposed "
        "two lines its own verification section ruled out — a volume figure that could not be "
        "published without a lag reconciliation, and an auction/private-treaty split that was "
        "never verified. Follow the verification section and drop the line.\n"
    )

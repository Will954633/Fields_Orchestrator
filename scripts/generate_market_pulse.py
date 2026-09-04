#!/usr/bin/env python3
"""
generate_market_pulse.py — Monthly AI-generated market summaries per category per suburb.

Fetches real market data from MongoDB, sends it to Claude Sonnet with category-specific
prompts, and stores the resulting summaries in system_monitor.market_pulse.

Usage:
    python3 scripts/generate_market_pulse.py                  # all suburbs, monthly guard
    python3 scripts/generate_market_pulse.py --force           # skip monthly guard
    python3 scripts/generate_market_pulse.py --suburb robina   # single suburb
    python3 scripts/generate_market_pulse.py --dry-run         # print prompts, don't call API
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pymongo import MongoClient
import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_series import five_year_growth  # noqa: E402

CLI_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLI_TIMEOUT_S = 120


def _child_env() -> dict:
    # Force Max billing instead of the pay-as-you-go API — same pattern as
    # fetch_policy_research.py's _child_env() (2026-07-23), adopted here after
    # the API key's credit balance ran dry mid-session.
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.pop("CLAUDECODE", None)
    env.setdefault("CI", "true")
    return env


def _call_claude_max(system_prompt: str, user_prompt: str, timeout: int = CLI_TIMEOUT_S) -> str:
    """Invoke the claude CLI (billed to Max, not API credits) and return the raw text response."""
    cmd = [CLI_BIN, "-p", user_prompt, "--system-prompt", system_prompt, "--output-format", "json"]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=_child_env())
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {(proc.stderr or '')[:500]}")
    data = json.loads(proc.stdout)
    if data.get("is_error") or data.get("subtype") != "success":
        raise RuntimeError(f"CLI returned error: {data.get('subtype')}: {str(data.get('result'))[:500]}")
    return data.get("result", "")


POLICY_DIGEST_SYSTEM_PROMPT = """You condense long-form policy research briefs into a compact reference
digest for a real estate copywriter. The copywriter writes 3-4 sentence suburb market summaries and will
select AT MOST ONE fact from your digest per summary, only when it's genuinely relevant — so each fact must
stand alone (don't rely on surrounding sentence context) and be quotable as-is."""

POLICY_DIGEST_USER_PROMPT_TEMPLATE = """Condense the policy brief below into 6-10 short, self-contained
factual bullet points (plain text, one per line, no markdown headers) covering: RBA cash rate level + next
decision date, negative gearing / CGT reform (effective date, who's affected, who's grandfathered),
first-home-buyer schemes (5% Deposit Scheme, Help to Buy, QLD Boost to Buy — caps and dates), QLD stamp
duty / First Home Owner Grant status. Skip AML/CTF and anything not relevant to a buyer/seller/investor
market summary. Keep the whole digest under 900 characters.

Policy brief:
{brief}"""


HOUSE_VOICE = """\
HOUSE VOICE — established 2026-08-02 with Will, binding on every summary.

1. OPEN ON THE HEADLINE THEY HAVE ALREADY SEEN, then place our data against it. The reader
   arrives carrying national coverage ("prices are falling"). Naming it first earns permission;
   leading with our own number reads as a sales position to someone braced for one.
2. THE 12-MONTH MEDIAN IS THE ONLY PRICE HEADLINE — always with its 90% confidence interval,
   its sample size, and a plain-language gloss of what the interval means. Never a bare figure.
3. VOLUME BY DIRECTION, NEVER PERCENTAGE. Our sold capture under-counts the newest quarter by
   31-49% against PropRadar settlements. "Fewer homes changed hands than a year earlier" is
   supportable; a percentage fall is not.
4. STATE PLAINLY WHAT WE WILL NOT CLAIM, AND WHY. If the quarters cannot support a
   quarter-on-quarter move, say so in the summary itself. Every competitor draws the line
   anyway — refusing to is the credential, not a hedge. This is the product.
5. EXTERNAL EXPECTATIONS ARE REPORTED AND ATTRIBUTED, NEVER ADOPTED. "The four major banks
   expect a hold" is reportable. Any version where we hold the view is a forecast.

Bounded by the standing editorial rules, which always win: no advice, no predictions, no single
valuation figure in a headline, no "stunning" / "nestled" / "boasting" / "rare opportunity" /
"robust market", prices written in full ($1,250,000), suburbs capitalised."""


MINDSET_DIGEST_SYSTEM_PROMPT = """\
You condense an internal seller-psychology brief into a short framing note for a writer producing \
public market commentary. You are not writing marketing copy and you are not writing advice."""

MINDSET_DIGEST_USER_PROMPT_TEMPLATE = """\
Condense the brief below into at most 900 words of framing for a writer producing public market \
commentary for homeowners in Robina, Burleigh Waters and Varsity Lakes.

Keep: the dominant tension in the reader's head, their ranked worries, what they actually want to \
know, and the explicit list of things we must NOT assert (the brief's "did NOT conclude" section).

Drop: all suburb figures (the writer has live data and the brief's numbers may be stale), all \
source citations, and anything tagged [INFERRED] unless you mark it clearly as unconfirmed.

Write it as guidance on WHICH facts matter to this reader and WHY, never as instructions to \
persuade. The output will be read by a writer bound by rules that forbid advice, prediction, and \
urgency — do not suggest anything that would breach those.

BRIEF:
{brief}"""


def fetch_mindset_digest() -> str:
    """
    Condense the homeowner mindset brief once per run into framing for every category prompt.

    The brief exists so the monthly prose speaks to what an owner in the target market is actually
    worried about, rather than only to the numbers. It is INTERNAL — the digest carries the brief's
    binding constraints with it so a downstream prompt cannot quietly turn seller psychology into
    persuasion. Deliberately non-fatal: a missing or stale brief warns and degrades to no framing
    rather than blocking the monthly cycle.
    """
    from homeowner_mindset import check_freshness, digest_guardrails

    rep, status = check_freshness()
    if rep is None:
        return ""
    if status == "stale":
        print("      (continuing — stale framing is better than none, but refresh it)")

    try:
        digest = _call_claude_max(
            MINDSET_DIGEST_SYSTEM_PROMPT,
            MINDSET_DIGEST_USER_PROMPT_TEMPLATE.format(brief=rep["text"]),
            timeout=240,
        ).strip()
    except Exception as e:
        print(f"  WARNING: mindset digest condensation failed ({e}) — continuing without it")
        return ""

    print(f"  Mindset digest ({rep['date']:%d %b %Y}, {rep['age_days']}d old): {len(digest)} chars")
    return digest + "\n\n" + digest_guardrails()


def fetch_policy_digest(sm_db) -> str:
    """Fetch the latest monthly policy research brief and condense it into a short digest
    reusable across all suburb/category summary prompts (one Max CLI call per run, not one
    per suburb/category — the full brief is ~9K chars, too long to inject 12x per run)."""
    doc = sm_db["policy_research_briefs"].find_one(sort=[("generated_at", -1)])
    if not doc or not doc.get("brief_text"):
        return ""
    try:
        digest = _call_claude_max(
            POLICY_DIGEST_SYSTEM_PROMPT,
            POLICY_DIGEST_USER_PROMPT_TEMPLATE.format(brief=doc["brief_text"]),
            timeout=180,
        ).strip()
        print(f"  Policy digest ({doc.get('month_label', '?')}): {len(digest)} chars")
        return digest
    except Exception as e:
        print(f"  WARNING: policy digest condensation failed ({e}) — continuing without policy context")
        return ""

# ─── Config ───────────────────────────────────────────────────────────────────

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
DISPLAY_NAMES = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}
MODEL = "claude-sonnet-4-6"
MONTHLY_GUARD_DAYS = 25  # won't re-run within 25 days unless --force

CATEGORIES = [
    {
        "id": "sell-now",
        "title": "Should I Sell Now?",
        "charts": ["median_price", "dom", "sales_volume", "price_adjustments", "vendor_discount", "absorption_rate"],
    },
    {
        "id": "buy",
        "title": "Is Now a Good Time to Buy?",
        "charts": ["median_price", "yoy_growth", "qoq_growth", "active_listings", "new_listings", "asking_prices", "absorption_rate"],
    },
    {
        "id": "crash-risk",
        "title": "Crash Risk",
        "charts": ["market_signals", "yoy_growth", "vendor_discount", "absorption_rate", "capital_gain"],
    },
    {
        "id": "overview",
        "title": "Market Overview",
        "charts": ["median_price", "sales_volume", "turnover_rate", "active_listings", "new_listings", "yoy_growth", "dom"],
    },
    {
        "id": "houses-vs-units",
        "title": "Houses vs Units",
        "charts": ["house_type_race", "asking_prices", "median_price", "capital_gain"],
    },
    {
        "id": "direction",
        "title": "Market Direction",
        "charts": ["forecast", "market_signals", "qoq_growth", "yoy_growth", "suburb_dna"],
    },
    {
        "id": "suburb-compare",
        "title": "Suburb Comparison",
        "charts": ["capital_gain", "suburb_motion", "suburb_dna", "turnover_rate"],
    },
]


# ─── Data Fetching ────────────────────────────────────────────────────────────

def fetch_all_data(gc_db, sm_db, suburb):
    """Fetch all available market data for a suburb, return as a structured dict."""
    data = {}
    display = DISPLAY_NAMES.get(suburb, suburb.replace("_", " ").title())

    # 1. Indexed prices (quarterly medians)
    idx = gc_db["precomputed_indexed_prices"].find_one({"_id": suburb})
    if idx:
        series = idx.get("indexed_series", [])
        recent = series[-8:] if len(series) >= 8 else series
        data["median_price_history"] = [
            {
                "period": q.get("period", ""),
                "median_price": q.get("median_price"),
                "index_value": q.get("index_value"),
                "transaction_count": q.get("transaction_count"),
            }
            for q in recent
        ]
        if len(series) >= 5:
            latest = series[-1].get("median_price", 0)
            year_ago = series[-5].get("median_price", 0) if len(series) >= 5 else 0
            if year_ago and latest:
                data["yoy_growth_pct"] = round((latest - year_ago) / year_ago * 100, 1)
            if len(series) >= 2:
                prev = series[-2].get("median_price", 0)
                # Only publish a quarter-on-quarter change when BOTH quarters are wide enough
                # to support one. precompute_union_prices.py bootstraps a 90% CI per quarter and
                # marks `reliable: false` where it is too wide — Burleigh Waters fails in 5 of
                # its last 6 quarters, Robina in 3 of 4. Narrating a QoQ move off those is
                # reporting sampling noise as a market move; the union's own method note says
                # they "must not narrate a QoQ change from them". Suppressing it here removes
                # the figure from every consumer at once, rather than per component.
                q_now, q_prev = series[-1], series[-2]
                both_reliable = q_now.get("reliable") is not False and q_prev.get("reliable") is not False
                if prev and both_reliable:
                    data["qoq_growth_pct"] = round((latest - prev) / prev * 100, 1)
                elif prev:
                    # OMIT the key rather than setting null. DirectionSection.tsx guards on
                    # `ds.qoq_growth_pct !== undefined`, so a null would pass the check and
                    # render "null%" in the verdict text. Absent is the only safe signal.
                    data.pop("qoq_growth_pct", None)
                    data["qoq_suppressed_reason"] = (
                        f"{q_now.get('period')} vs {q_prev.get('period')}: confidence interval too "
                        f"wide to support a quarter-on-quarter claim (n={q_now.get('median_sample_n')} "
                        f"and n={q_prev.get('median_sample_n')}). Do not state a QoQ change."
                    )
            data["current_median_price"] = latest
        # 10-year journey
        if len(series) >= 40:
            ten_yr_start = series[-40].get("median_price", 0)
            ten_yr_end = series[-1].get("median_price", 0)
            if ten_yr_start and ten_yr_end:
                data["ten_year_growth_pct"] = round((ten_yr_end - ten_yr_start) / ten_yr_start * 100, 1)
                data["ten_year_start_price"] = ten_yr_start
                data["ten_year_end_price"] = ten_yr_end

    # 2. Days on Market
    dom_doc = gc_db["precomputed_market_charts"].find_one({"_id": f"{suburb}_days_on_market"})
    if dom_doc:
        timeline = dom_doc.get("dom_timeline", dom_doc.get("timeline", []))
        # HEADLINE = trailing-12-month median (the chart's stable headline), NOT timeline[-1].
        # timeline[-1] is the IN-PROGRESS quarter (`incomplete: True`) — same trap already
        # fixed for sales volume below. For Robina it put a 22-sale Q3 (median 62) into
        # dom_median, which the sell-now page then rendered as the headline "62 days".
        t12 = (dom_doc.get("trailing_12m") or {})
        if t12.get("median_days_on_market") is not None:
            data["dom_median"] = t12.get("median_days_on_market")
            data["dom_avg"] = t12.get("avg_days_on_market")
            data["dom_quick_sales_pct"] = t12.get("quick_sales_pct")
            we = t12.get("window_end")
            data["dom_period"] = f"12 months to {we}" if we else "trailing 12 months"
        elif timeline:
            # Fall back to the last COMPLETE quarter, never the incomplete tail.
            complete = [q for q in timeline if not q.get("incomplete")] or timeline
            latest_dom = complete[-1]
            data["dom_median"] = latest_dom.get("median_days_on_market")
            data["dom_avg"] = latest_dom.get("avg_days_on_market")
            data["dom_period"] = latest_dom.get("period", "")
            data["dom_quick_sales_pct"] = latest_dom.get("quick_sales_pct")
        # Year-earlier comparison: the same quarter one year back (4 complete quarters
        # before the latest COMPLETE one), so the incomplete tail never shifts the offset.
        complete_q = [q for q in timeline if not q.get("incomplete")]
        if len(complete_q) >= 5:
            data["dom_yoy_prev"] = complete_q[-5].get("median_days_on_market")

    # 3. Sales Volume
    # Complete quarters only. timeline[-1] is the IN-PROGRESS quarter — for Robina that put
    # `sales_volume_latest = 14` (a month-old Q3 2026) next to a full prior quarter, inviting a
    # "sales have collapsed" reading of a quarter that has barely started.
    #
    # Volume is also a SAMPLE: our sold capture lags settlement and under-counts the newest
    # complete quarter. Checked 2026-08-02 against PropRadar settlement records — our Q2 2026 was
    # 31% short for Robina and 49% short for Varsity Lakes. The direction is real and independently
    # corroborated (PRD has Burleigh Heads house sales -15.3% y/y); the magnitude is not publishable.
    # PREFER THE UNION COUNTS. `precomputed_market_charts.{suburb}_sales_volume` is anchored by
    # recalibrate_charts.py to PropRadar's sales_12mo — the same counts that were DEMOTED for the
    # median because they overstate (240 Burleigh Waters houses against realestate.com.au's 195).
    # The two series disagree materially: on the anchored basis Burleigh Waters reads 51 -> 56 -> 73
    # across Q4 2025 to Q2 2026 (a rise), while the union set behind our medians reads 41 -> 44 -> 42
    # (flat). On 2026-08-02 the anchored series put "activity has picked up" into five published
    # summaries — the same "Burleigh Waters is accelerating" artefact 10_Market_Report/
    # HANDOFF_Q2_2026.md records as already published once and retracted.
    #
    # Volume is ONLY comparable from `union_from`; earlier quarters are Domain-only and undercount
    # by 25-55%, so a year-on-year volume comparison crosses two capture bases and must not be made.
    if idx:
        union_counts = [
            {"period": q.get("period"), "sales_count": q.get("median_sample_n")}
            for q in (idx.get("indexed_series") or [])
            if q.get("basis") == "union" and q.get("median_sample_n")
        ]
        if union_counts:
            data["sales_volume_latest"] = union_counts[-1]["sales_count"]
            data["sales_volume_period"] = union_counts[-1]["period"]
            data["sales_volume_series"] = union_counts[-4:]
            data["sales_volume_basis"] = (
                f"union transaction set (Domain u onthehouse), comparable only from "
                f"{idx.get('union_from')}. NO year-on-year comparison is possible. The newest "
                f"quarter is still filling in as settlements register, so it is a floor. Report "
                f"direction across the union window only — never a count, never a percentage."
            )
            if len(union_counts) >= 2:
                data["sales_volume_prev"] = union_counts[-2]["sales_count"]

    sv_doc = gc_db["precomputed_market_charts"].find_one({"_id": f"{suburb}_sales_volume"})
    if sv_doc and "sales_volume_latest" not in data:
        complete = [t for t in (sv_doc.get("timeline") or []) if not t.get("is_in_progress")]
        if complete:
            latest_sv = complete[-1]
            data["sales_volume_latest"] = latest_sv.get("sales_count")
            data["sales_volume_period"] = latest_sv.get("period", "")
            data["sales_volume_basis"] = (
                "last COMPLETE quarter; sample only — under-captures the newest quarter, so "
                "report direction ('fewer sales than a year earlier'), never a percentage fall"
            )
            if len(complete) >= 2:
                data["sales_volume_prev"] = complete[-2].get("sales_count")

            # `sales_volume_yoy_change` is deliberately NOT emitted. It rendered directly as
            # "Sales volume down 52% year-on-year — buyer pool contracting"
            # (DirectionSection.tsx:153, :188; SellNowSection.tsx:112). Against PropRadar
            # settlement records our Q2 2026 was 31% short for Robina and 49% short for Varsity
            # Lakes, so that percentage overstates the fall by a wide margin. The DIRECTION is
            # real and independently corroborated (PRD: Burleigh Heads house sales -15.3% y/y);
            # the magnitude is not publishable until a lag reconciliation exists.
            # Omitted rather than nulled — DirectionSection guards on `!== undefined`.
            yoy_raw = latest_sv.get("yoy_change")
            if yoy_raw is not None:
                data["sales_volume_direction"] = (
                    "lower than the same quarter a year earlier" if yoy_raw < 0
                    else "higher than the same quarter a year earlier" if yoy_raw > 0
                    else "level with the same quarter a year earlier"
                )
                data["sales_volume_yoy_suppressed_reason"] = (
                    f"raw computed change {yoy_raw:+.1f}% withheld — our sold capture "
                    f"under-counts the newest quarter (31-49% short vs PropRadar settlements). "
                    f"State direction only."
                )

    # 4. Turnover Rate
    tr_doc = gc_db["precomputed_market_charts"].find_one({"_id": f"{suburb}_turnover_rate"})
    if tr_doc:
        timeline = tr_doc.get("timeline", [])
        if timeline:
            latest_tr = timeline[-1]
            data["turnover_rate"] = latest_tr.get("turnover_rate")
            data["turnover_year"] = latest_tr.get("year")
            data["turnover_sales"] = latest_tr.get("sales")
        data["total_stock"] = tr_doc.get("total_stock")

    # 5. Active Listings
    al_doc = gc_db["precomputed_active_listings"].find_one({"_id": suburb})
    if al_doc:
        snapshots = al_doc.get("snapshots", [])
        if snapshots:
            latest_al = snapshots[-1]
            data["active_listings"] = latest_al.get("active_listings")
            # Month ago comparison
            if len(snapshots) >= 30:
                month_ago = snapshots[-30]
                old_count = month_ago.get("active_listings", 0)
                new_count = latest_al.get("active_listings", 0)
                if old_count:
                    data["active_listings_mom_pct"] = round((new_count - old_count) / old_count * 100, 1)

    # 6. Absorption Rate (calculated: active listings / monthly sales rate)
    active = gc_db[suburb].count_documents({"listing_status": "for_sale"})
    ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    sold_90d = gc_db[suburb].count_documents({
        "listing_status": "sold",
        "sold_date": {"$gte": ninety_days_ago}
    })
    monthly_sales = sold_90d / 3.0 if sold_90d > 0 else 0
    if monthly_sales > 0:
        data["absorption_rate_months"] = round(active / monthly_sales, 1)
        data["absorption_monthly_sales"] = round(monthly_sales, 1)
    data["absorption_active"] = active

    # 7. Price Change Events
    events = list(sm_db["price_change_events"].find(
        {"suburb": {"$regex": suburb, "$options": "i"}},
        {"direction": 1, "change_pct": 1, "days_on_market": 1, "_id": 0}
    ).limit(100))
    if events:
        reductions = [e for e in events if e.get("direction") == "reduction"]
        increases = [e for e in events if e.get("direction") == "increase"]
        data["price_reductions_count"] = len(reductions)
        data["price_increases_count"] = len(increases)
        data["price_total_adjustments"] = len(events)

    # 8. Vendor Discount
    pipeline = [
        {"$match": {"listing_status": "sold", "vendor_discount_pct": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": None,
            "avg_discount": {"$avg": "$vendor_discount_pct"},
            "median_discount": {"$avg": "$vendor_discount_pct"},  # approx
            "count": {"$sum": 1}
        }}
    ]
    try:
        vd_result = list(gc_db[suburb].aggregate(pipeline))
        if vd_result:
            data["vendor_discount_avg_pct"] = round(vd_result[0].get("avg_discount", 0), 1)
            data["vendor_discount_count"] = vd_result[0].get("count", 0)
    except Exception:
        pass

    # 9. SQM Asking Prices
    sqm = gc_db["sqm_asking_prices"].find_one({"suburb": {"$regex": display, "$options": "i"}})
    if sqm:
        series = sqm.get("series", [])
        if series:
            latest_sqm = series[-1]
            data["asking_price_houses"] = latest_sqm.get("houses_all")
            data["asking_price_units"] = latest_sqm.get("units_all")
            data["asking_price_combined"] = latest_sqm.get("combined")
            data["asking_price_date"] = latest_sqm.get("date")
            # 3-month trend
            if len(series) >= 13:
                three_months_ago = series[-13]
                old_combined = three_months_ago.get("combined", 0)
                if old_combined:
                    data["asking_price_3m_change_pct"] = round(
                        (latest_sqm.get("combined", 0) - old_combined) / old_combined * 100, 1
                    )

    # 10. Market Signals
    signals_doc = sm_db["market_signals"].find_one({"_id": "market_signals_latest"})
    if signals_doc:
        suburbs_data = signals_doc.get("suburbs", {})
        suburb_signals = suburbs_data.get(suburb, {})
        if suburb_signals:
            data["overall_sentiment"] = suburb_signals.get("overallSentiment")
            signals = suburb_signals.get("signals", [])
            data["market_signals"] = [
                {
                    "indicator": s.get("displayName"),
                    "value": s.get("currentValue"),
                    "trend": s.get("trend"),
                    "signal": s.get("signal"),
                }
                for s in signals
            ]

    # 11. Capital gain comparison (indexed prices for all target suburbs)
    #
    # Two separate measures, deliberately named so they cannot be conflated:
    #   *_index_since_<baseline>  = cumulative % growth since the 2016 baseline (an index LEVEL,
    #                               comparable across suburbs only because they share a baseline)
    #   five_year_growth_pct      = actual % change in median over the last 5 years (a RATE)
    # The old field was called "five_year_index" but held the index LEVEL as at ~5 years ago.
    # Summaries read it as a five-year growth rate and ranked suburbs on the difference between
    # two index levels — which is a percentage-POINT gap on a 2016 base, not five-year growth.
    # That inverted the Aug-2026 suburb-compare ranking (index deltas put Burleigh Waters top;
    # true 5yr median growth puts it last). See fix-history [PULSE-FIVE-YEAR-INDEX-MISLABEL].
    #
    # Growth is computed off rolling_12m_median_series (12-month rolling medians), not the raw
    # quarterly series, because single quarters here are thin enough to swing the answer. The
    # rolling series is SPARSE after the union merge, so the five-year point is matched on the
    # period label, never on position — see scripts/market_series.py.
    capital_gains = {}
    for s in TARGET_SUBURBS:
        s_idx = gc_db["precomputed_indexed_prices"].find_one({"_id": s})
        if not s_idx:
            continue
        s_series = s_idx.get("indexed_series", [])
        if not s_series:
            continue

        name = DISPLAY_NAMES.get(s, s)
        entry = {
            "latest_period": s_series[-1].get("period"),
            "latest_median": s_series[-1].get("median_price"),
            "index_since_baseline": s_series[-1].get("index_value"),
            "index_baseline_period": s_idx.get("baseline_period"),
        }

        growth = five_year_growth(s_idx)
        if growth:
            entry["five_year_growth_pct"] = growth["growth_pct"]
            entry["five_year_from_period"] = growth["from_period"]
            entry["five_year_from_median"] = growth["from_median"]
            entry["five_year_basis"] = growth["basis"]
        else:
            entry["five_year_growth_pct"] = None
            entry["five_year_note"] = (
                "no 12-month rolling median recorded for the same quarter five years earlier — "
                "do not substitute a nearby quarter"
            )

        capital_gains[name] = entry
    data["capital_gains_comparison"] = capital_gains

    # 12. Asking prices houses vs units divergence
    if "asking_price_houses" in data and "asking_price_units" in data:
        data["asking_house_unit_spread"] = round(
            data["asking_price_houses"] - data["asking_price_units"], 0
        )

    data["suburb_display"] = display
    data["data_date"] = datetime.now().strftime("%Y-%m-%d")

    # --- Authoritative headline median: the Domain ∪ onthehouse union ---
    # Until 2026-08-01 this block overrode the median and 1-year growth with PropRadar's,
    # because our own quarterly series is an under-captured, premium-skewed sample. That
    # anchor was then REMOVED from the chart pipeline (recalibrate_charts.py
    # RECALIBRATE_MEDIAN = False) after it was found to substitute a median computed over a
    # DIFFERENT dwelling population — and PropRadar's Burleigh Waters median_price is now
    # null outright. PropRadar remains authoritative for VOLUME only.
    #
    # The median therefore comes from precompute_union_prices.py, same as the charts, so the
    # prose and the page cannot disagree. It carries a 90% CI and a sample size, both exposed
    # here so summaries can state the limitation rather than assert a bare figure.
    if idx:
        # `current_median_price` is read by every tab section (Overview, SellNow, Buy,
        # CrashRisk, Direction, SuburbCompare) for their headline figure, their FAQ text AND
        # their FAQPage JSON-LD. It used to be the latest complete QUARTER while
        # `yoy_growth_pct` just below was a 12-MONTH rolling figure — so the same sentence
        # mixed two bases ("median is $X, a +Y% change over the trailing 12 months"), and the
        # page carried a different median in the hero, the tabs and the prose.
        #
        # Where the union median exists it becomes THE median, so one label means one number.
        # It is also the only one with a published CI and sample size. Suburbs outside the
        # union (76 of 79 — it runs for the 3 core suburbs only) keep the quarterly figure,
        # which is what they showed before.
        if idx.get("median_source") == "domain_union_onthehouse" and idx.get("rolling_12m_median_price"):
            # Capture the quarterly figure before it is replaced as the headline.
            data["latest_quarter_median_price"] = data.get("current_median_price")
            data["current_median_price"] = idx["rolling_12m_median_price"]
            data["current_median_price_basis"] = "12-month rolling median (Domain ∪ onthehouse)"
            data["median_12m"] = idx["rolling_12m_median_price"]
            data["median_12m_ci_low"] = idx.get("rolling_12m_ci_low")
            data["median_12m_ci_high"] = idx.get("rolling_12m_ci_high")
            data["median_12m_margin_pct"] = idx.get("rolling_12m_ci_margin_pct")
            data["median_12m_sample_n"] = idx.get("rolling_12m_median_sample_n")
            data["median_source"] = idx.get("median_source")
            data["median_computed_at"] = idx.get("median_computed_at")
            data["latest_quarter_median_price_basis"] = (
                "latest complete quarter — name it as a quarterly figure wherever it appears, "
                "never as 'the median house price'"
            )
        else:
            data["current_median_price_basis"] = "latest complete quarter"

        # YoY off the 12-month rolling series, not a single thin quarter. Paired with a
        # 12-month median above, so both halves of the sentence are now the same basis.
        if idx.get("rolling_12m_yoy_pct") is not None:
            data["yoy_growth_pct"] = idx["rolling_12m_yoy_pct"]
            data["yoy_growth_basis"] = "rolling 12 months vs the prior 12 months"
        if idx.get("union_from"):
            data["volume_comparable_from"] = idx["union_from"]

    # --- PropRadar: volume-side stats only ---
    try:
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "propradar"))
        from suburb_stats import house_headline
        _prs = house_headline(gc_db, suburb)
    except Exception as _e:
        _prs = None
        print(f"  (propradar_suburb_stats unavailable for {suburb}: {_e})")
    if _prs:
        _used = []
        if _prs.get("inventory_months") is not None:
            data["absorption_rate_months"] = _prs["inventory_months"]
            _used.append("inventory_months")
        if _prs.get("sales_12mo") is not None:
            data["sales_12mo_house"] = _prs["sales_12mo"]
            _used.append("sales_12mo")
        # Only claim PropRadar as a source if something actually came from it — the old code
        # stamped headline_stats_source="propradar" even when every field it read was null.
        if _used:
            data["propradar_fields_used"] = _used
            data["propradar_as_of"] = _prs.get("as_of")
    data["headline_stats_source"] = data.get("median_source") or "fields_quarterly_series"

    return data


# ─── Prompt Templates ────────────────────────────────────────────────────────

CATEGORY_PROMPTS = {
    "sell-now": """You are writing a market summary for a homeowner in {suburb} who is considering selling their property.
They are anxious about timing — they don't want to sell too early (miss further gains) or too late (catch a downturn).

Here is the current market data for {suburb}:
{data}

Current AU/QLD housing policy context (use AT MOST ONE fact from this list, only if it genuinely
strengthens the analysis — do not force a policy mention into every summary):
{policy}

Who you are writing for (INTERNAL framing — never quote this, never reveal that we profile
seller psychology, never write persuasion. It tells you WHICH facts matter to this reader and
WHY; it does not license advice, prediction or urgency, and the live data always wins):
{mindset}

{house_voice}

Write a 3-4 sentence market summary that:
1. Opens with "Should you sell your house in {suburb} now?"
2. Gives a direct verdict: conditions currently favour sellers / market is balanced / conditions favour buyers
3. Cites the 2-3 most telling data points (DOM, absorption rate, price adjustments, volume, vendor discount)
4. Ends with one forward-looking sentence — what signal to watch that could change the verdict
5. Format numbers as: $1,250,000 (not "$1.25m"), percentages to 1 decimal

Also return a structured verdict as one of: "strong_sellers_market", "sellers_advantage", "balanced", "buyers_advantage", "strong_buyers_market"
And return 2-3 key_signals as JSON objects with metric, value, and interpretation.

Return your response as JSON:
{{
  "summary": "your 3-4 sentence summary here",
  "verdict": "one of the verdict strings",
  "key_signals": [
    {{"metric": "absorption_rate", "value": "3.2 months", "interpretation": "Below 4 months = seller's market"}}
  ]
}}""",

    "buy": """You are writing for someone considering buying a home in {suburb}.
They want to know: is now a smart time to enter the market, or should they wait?

Here is the current market data for {suburb}:
{data}

Current AU/QLD housing policy context (use AT MOST ONE fact from this list, only if it genuinely
strengthens the analysis — do not force a policy mention into every summary). First-home-buyer scheme
facts (5% Deposit Scheme, Help to Buy, stamp duty/FHOG) are usually most relevant here:
{policy}

Who you are writing for (INTERNAL framing — never quote this, never reveal that we profile
seller psychology, never write persuasion. It tells you WHICH facts matter to this reader and
WHY; it does not license advice, prediction or urgency, and the live data always wins):
{mindset}

{house_voice}

Write a 3-4 sentence summary that:
1. Opens with "Is now a good time to buy a house in {suburb}?"
2. Gives a direct assessment of buyer conditions (strong/moderate/limited negotiating power)
3. References price growth momentum, listing supply, and absorption rate
4. Ends with practical context — what the data suggests about price direction

Also return a verdict: "strong_buyer_conditions", "moderate_buyer_conditions", "neutral", "limited_buyer_power", "very_limited_buyer_power"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "crash-risk": """You are writing for someone worried the Gold Coast property market might crash.
They may be an anxious homeowner or a hesitant buyer. They need honest, data-backed reassurance — not dismissal of their fears. If warning signs exist, say so.

IMPORTANT CONTEXT — Our proprietary analysis of 27 economic datasets across 8 Gold Coast suburbs (2015-2025) found that:
- The #1 real-time indicator of market strength is Queensland HOUSEHOLD SPENDING (r=0.914 correlation with house prices)
- The best LEADING indicator is the WAGE PRICE INDEX for QLD — it leads house prices by 3-4 months (r=0.940)
- INTEREST RATES LAG prices by 12 months (r=0.791) — the RBA is reactive, not predictive
- CREDIT/LENDING GROWTH lags prices by 3.5 months (r=0.948) — it confirms what already happened
- The most crash-sensitive suburb is Burleigh Waters (highest economic correlation); Worongary is most insulated

ACADEMIC VALIDATION — Peer-reviewed research (Abelson et al. 2005, The Economic Record) on 33 years of Australian national data confirms:
- Real disposable income has a LONG-RUN ELASTICITY of 1.71 — a 1% income rise produces a 1.71% house price rise (amplification effect)
- Australian house prices are ASYMMETRIC: when rising, the market adjusts to equilibrium in ~4 quarters. When FALLING, it takes ~6 quarters (50% slower). This means sharp crashes are structurally unlikely — prices stagnate rather than collapse.
- Housing SUPPLY per capita has the largest single coefficient (-3.6 elasticity). Rising supply is the biggest structural risk factor.

Your crash risk assessment should primarily reference these leading indicators (wages, household spending) rather than backward-looking metrics. If wages are rising and household spending is up, a crash is unlikely regardless of what interest rates are doing. If wages are plateauing or falling, that IS a genuine warning sign. Also mention the asymmetric adjustment finding — Australian house prices historically fall slowly (6 quarters to adjust), making sudden crashes structurally unlikely.

Here is the current market data for {suburb}:
{data}

Current AU/QLD housing policy context (use AT MOST ONE fact from this list, only if it genuinely
strengthens the analysis — do not force a policy mention into every summary). The RBA cash rate/next
decision date and negative gearing/CGT reform are usually most relevant here:
{policy}

Who you are writing for (INTERNAL framing — never quote this, never reveal that we profile
seller psychology, never write persuasion. It tells you WHICH facts matter to this reader and
WHY; it does not license advice, prediction or urgency, and the live data always wins):
{mindset}

{house_voice}

Write a 3-4 sentence summary that:
1. Opens with "Is the Gold Coast property market going to crash?"
2. Acknowledges the concern honestly, then assesses crash risk based on the LEADING indicators (wage growth trend, household spending, lending)
3. References the current market signals data and what they mean for crash probability
4. If bearish signals exist, name them honestly. If bullish, explain which leading indicators support continued strength
5. DO NOT reference "10-year resilience" or "long-term price history" — focus on forward-looking indicators

Verdict: "very_low_risk", "low_risk", "moderate_risk", "elevated_risk", "high_risk"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "overview": """You are writing a market overview for {suburb} aimed at someone unfamiliar with the area — perhaps an interstate investor or first-time researcher.

Here is the current market data for {suburb}:
{data}

Current AU/QLD housing policy context (use AT MOST ONE fact from this list, only if it genuinely
strengthens the analysis — do not force a policy mention into every summary):
{policy}

Who you are writing for (INTERNAL framing — never quote this, never reveal that we profile
seller psychology, never write persuasion. It tells you WHICH facts matter to this reader and
WHY; it does not license advice, prediction or urgency, and the live data always wins):
{mindset}

{house_voice}

Write a 3-4 sentence overview that:
1. Opens with "What is the {suburb} property market doing?"
2. Covers the headline numbers: median price, recent sales volume, DOM, active listings
3. Gives context on whether the market is accelerating, stable, or cooling
4. Keeps a neutral, analytical tone

Verdict: "strong_growth", "moderate_growth", "stable", "cooling", "declining"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "houses-vs-units": """You are writing for an investor or buyer in {suburb} deciding between a house and a unit.

Here is the current market data for {suburb}:
{data}

Current AU/QLD housing policy context (use AT MOST ONE fact from this list, only if it genuinely
strengthens the analysis — do not force a policy mention into every summary):
{policy}

Who you are writing for (INTERNAL framing — never quote this, never reveal that we profile
seller psychology, never write persuasion. It tells you WHICH facts matter to this reader and
WHY; it does not license advice, prediction or urgency, and the live data always wins):
{mindset}

{house_voice}

Write a 3-4 sentence summary that:
1. Opens with "Are houses or units a better investment in {suburb}?"
2. Compares asking prices for houses vs units (the spread)
3. References any divergence in price trends between the two types
4. Gives a direct observation on which type is showing stronger momentum

Verdict: "houses_strongly_outperforming", "houses_outperforming", "similar_performance", "units_outperforming", "units_strongly_outperforming"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "direction": """You are writing for someone who wants to know which way the {suburb} property market is heading — they're timing a major buy or sell decision.

IMPORTANT CONTEXT — Research shows:
- Queensland wage growth LEADS house prices by 3-4 months (r=0.940). Current wage trend is the best predictor of where prices are heading.
- Income has an AMPLIFICATION effect on house prices: peer-reviewed research (Abelson et al. 2005) found a 1% rise in real income produces a 1.71% rise in house prices. Even moderate wage growth drives outsized price gains.
- Household spending is the strongest real-time indicator (r=0.914).
- Interest rates LAG by 12 months — don't reference rate expectations as a leading signal.

Here is the current market data for {suburb}:
{data}

Current AU/QLD housing policy context (use AT MOST ONE fact from this list, only if it genuinely
strengthens the analysis — do not force a policy mention into every summary):
{policy}

Who you are writing for (INTERNAL framing — never quote this, never reveal that we profile
seller psychology, never write persuasion. It tells you WHICH facts matter to this reader and
WHY; it does not license advice, prediction or urgency, and the live data always wins):
{mindset}

{house_voice}

Write a 3-4 sentence summary that:
1. Opens with "Which way is the {suburb} property market moving?"
2. References QoQ and YoY growth momentum and whether it's accelerating or decelerating
3. Cites the LEADING indicators (wage growth trend, household spending) — these predict direction, not interest rates
4. Gives a forward-looking sentence grounded in the leading indicator data, noting that income changes amplify into larger price movements (1.71x elasticity)

Verdict: "strongly_rising", "rising", "plateauing", "softening", "declining"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",

    "suburb-compare": """You are writing for someone comparing {suburb} against other Gold Coast suburbs (Robina, Burleigh Waters, Varsity Lakes).

Here is the current market data including cross-suburb comparisons:
{data}

Current AU/QLD housing policy context (use AT MOST ONE fact from this list, only if it genuinely
strengthens the analysis — do not force a policy mention into every summary; often not relevant here):
{policy}

Who you are writing for (INTERNAL framing — never quote this, never reveal that we profile
seller psychology, never write persuasion. It tells you WHICH facts matter to this reader and
WHY; it does not license advice, prediction or urgency, and the live data always wins):
{mindset}

{house_voice}

Write a 3-4 sentence summary that:
1. Opens with "How does {suburb} compare to nearby suburbs?"
2. References the capital gain comparison across the three suburbs. Two DIFFERENT measures are
   supplied and must not be mixed: `index_since_baseline` is cumulative growth since the
   `index_baseline_period` baseline (a level, not a recent rate), while `five_year_growth_pct`
   is the actual change in median over the last five years. If you rank the suburbs, say which
   measure you are ranking on — they do not produce the same order. Never describe a difference
   between two `index_since_baseline` values as a growth rate; it is a percentage-point gap.
3. Notes any standout differences in median price, turnover, or growth rate
4. Helps the reader understand {suburb}'s positioning (value suburb, premium suburb, growth suburb)

Verdict: "top_performer", "above_average", "mid_pack", "below_average", "underperformer"

Return as JSON:
{{
  "summary": "...",
  "verdict": "...",
  "key_signals": [{{"metric": "...", "value": "...", "interpretation": "..."}}]
}}""",
}

SYSTEM_PROMPT = """You are a property market analyst for Fields Estate, a data-driven real estate intelligence platform on the Gold Coast, Australia.

Rules:
- Be authoritative but not salesy — like a trusted analyst, not an agent
- Use exact numbers: $1,250,000 not "$1.25m"
- Suburbs always capitalised: "Robina" not "robina"
- Never use: "stunning", "nestled", "boasting", "rare opportunity", "robust market"
- Always ground claims in specific data points from the provided data
- If data is missing or sparse, say so — don't fabricate numbers
- Keep summaries to exactly 3-4 sentences
- Return valid JSON only, no markdown code fences"""


# ─── Claude API Call ──────────────────────────────────────────────────────────

def generate_summary(client, category_id, suburb_display, data_dict, policy_digest="",
                     mindset_digest="", dry_run=False):
    """Call Claude Sonnet to generate a category summary."""
    prompt_template = CATEGORY_PROMPTS.get(category_id)
    if not prompt_template:
        return None

    # Format data as readable text for the prompt
    data_text = json.dumps(data_dict, indent=2, default=str)
    prompt = prompt_template.format(
        suburb=suburb_display,
        data=data_text,
        policy=policy_digest or "(no current policy brief available)",
        mindset=mindset_digest or "(no homeowner mindset brief available)",
        house_voice=HOUSE_VOICE,
    )

    if dry_run:
        print(f"\n{'='*60}")
        print(f"CATEGORY: {category_id} | SUBURB: {suburb_display}")
        print(f"{'='*60}")
        print(f"Prompt length: {len(prompt)} chars")
        print(f"Data keys: {list(data_dict.keys())}")
        return None

    input_tokens = None
    output_tokens = None
    if client == "max_cli":
        text = _call_claude_max(SYSTEM_PROMPT, prompt).strip()
    else:
        response = client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

    # Parse JSON response (handle truncation and code fences)
    try:
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage truncated JSON by extracting fields with regex
        import re
        summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        verdict_match = re.search(r'"verdict"\s*:\s*"([^"]+)"', text)
        summary = summary_match.group(1) if summary_match else text
        verdict = verdict_match.group(1) if verdict_match else "unknown"
        # Clean up escaped chars
        summary = summary.replace('\\"', '"').replace('\\n', ' ')
        result = {"summary": summary, "verdict": verdict, "key_signals": []}

    return {
        "summary": result.get("summary", ""),
        "verdict": result.get("verdict", "unknown"),
        "key_signals": result.get("key_signals", []),
        "model": MODEL if client != "max_cli" else f"{MODEL}-via-max-cli",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate monthly market pulse summaries")
    parser.add_argument("--force", action="store_true", help="Skip monthly guard")
    parser.add_argument("--suburb", type=str, help="Single suburb (e.g. robina)")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling API")
    parser.add_argument("--category", type=str, help="Single category (e.g. sell-now)")
    parser.add_argument("--use-api", action="store_true", help="Use the pay-as-you-go Anthropic API instead of the Claude Max CLI (default)")
    args = parser.parse_args()

    # Connect to MongoDB
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client_db = MongoClient(conn_str)
    gc_db = client_db["Gold_Coast"]
    sm_db = client_db["system_monitor"]
    pulse_coll = sm_db["market_pulse"]

    # Monthly guard
    if not args.force and not args.dry_run:
        latest = pulse_coll.find_one(
            {"generated_at": {"$exists": True}},
            sort=[("generated_at", -1)]
        )
        if latest:
            last_gen = latest.get("generated_at")
            if isinstance(last_gen, str):
                last_gen = datetime.fromisoformat(last_gen)
            if last_gen and (datetime.now() - last_gen).days < MONTHLY_GUARD_DAYS:
                days_ago = (datetime.now() - last_gen).days
                print(f"Last pulse generated {days_ago} days ago (guard: {MONTHLY_GUARD_DAYS} days). Use --force to override.")
                sys.exit(0)

    # Init Claude client — Max CLI by default (zero API-credit cost); --use-api
    # falls back to the pay-as-you-go SDK client (kept for dry-run parity / if
    # Max is ever unavailable). Switched to Max default 2026-07-23 after the
    # API key's credit balance ran dry mid-regeneration.
    claude_client = None
    if not args.dry_run:
        if args.use_api:
            api_key = os.environ.get("ANTHROPIC_SONNET_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                print("ERROR: No Anthropic API key found")
                sys.exit(1)
            claude_client = anthropic.Anthropic(api_key=api_key)
        else:
            claude_client = "max_cli"

    # Determine suburbs
    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
    categories = [c for c in CATEGORIES if not args.category or c["id"] == args.category]

    # Fetch + condense the latest policy research brief ONCE per run (not once per
    # suburb/category — the full brief is ~9K chars, condensing it 12x per run would
    # be wasteful). Reused across every generate_summary() call below.
    policy_digest = ""
    mindset_digest = ""
    if not args.dry_run:
        policy_digest = fetch_policy_digest(sm_db)
        # Homeowner psychology framing — same once-per-run pattern, same non-fatal degrade.
        mindset_digest = fetch_mindset_digest()

    total_input_tokens = 0
    total_output_tokens = 0
    generated_count = 0

    for suburb in suburbs:
        display = DISPLAY_NAMES.get(suburb, suburb.replace("_", " ").title())
        print(f"\n{'─'*60}")
        print(f"Fetching data for {display}...")

        data = fetch_all_data(gc_db, sm_db, suburb)
        print(f"  Data points: {len(data)} fields")

        for cat in categories:
            cat_id = cat["id"]

            # Skip if a manual update exists for this month (unless --force)
            if not args.force and not args.dry_run:
                month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                existing = pulse_coll.find_one({
                    "suburb": suburb,
                    "category": cat_id,
                    "source": "manual",
                    "generated_at": {"$gte": month_start},
                })
                if existing:
                    print(f"\n  Skipping: {cat['title']} ({cat_id}) — manual update exists this month")
                    continue

            print(f"\n  Generating: {cat['title']} ({cat_id})...")

            result = generate_summary(claude_client, cat_id, display, data,
                                      policy_digest=policy_digest,
                                      mindset_digest=mindset_digest,
                                      dry_run=args.dry_run)

            if result is None:
                continue

            # Build document
            doc = {
                "suburb": suburb,
                "suburb_display": display,
                "category": cat_id,
                "category_title": cat["title"],
                "summary": result["summary"],
                "verdict": result["verdict"],
                "key_signals": result["key_signals"],
                "source": "auto",
                "data_snapshot": data,
                "generated_at": datetime.now(),
                "model": result["model"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            }

            # Upsert (one doc per suburb+category)
            pulse_coll.update_one(
                {"suburb": suburb, "category": cat_id},
                {"$set": doc},
                upsert=True,
            )

            total_input_tokens += result["input_tokens"] or 0
            total_output_tokens += result["output_tokens"] or 0
            generated_count += 1

            token_note = f"{result['input_tokens']}+{result['output_tokens']} tokens" if result["input_tokens"] is not None else "billed to Claude Max"
            print(f"    ✅ {result['verdict']} ({token_note})")
            print(f"    {result['summary'][:120]}...")

    if not args.dry_run:
        print(f"\n{'='*60}")
        print(f"Done. Generated {generated_count} summaries.")
        if total_input_tokens or total_output_tokens:
            # Rough cost estimate (Sonnet pricing: $3/M input, $15/M output) — API-billed calls only
            cost = (total_input_tokens * 3 + total_output_tokens * 15) / 1_000_000
            print(f"Tokens: {total_input_tokens} input + {total_output_tokens} output")
            print(f"Estimated cost: ${cost:.3f}")
        else:
            print("All generations billed to Claude Max (no API credit consumed).")


if __name__ == "__main__":
    main()

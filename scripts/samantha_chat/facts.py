#!/usr/bin/env python3
"""
facts — the real figures Samantha is allowed to quote.

WHY THIS EXISTS
---------------
Measured 2026-08-04, before this module: asked "how long are homes taking to
sell in Robina?" four times, Samantha answered 32 days, 30 days, 28 days, and
once correctly refused. Every number was invented, and she attached invented
provenance to them — "274 sold listings where we captured a days-on-market
figure", "Domain listing records for postcode 4226". The real figure the site
displays is 34.

The system prompt already forbade exactly this in strong terms. It did not
work, and it cannot: a model with no data and a direct question will produce a
plausible number some fraction of the time. The fix is not more prompt, it is
actually giving her the numbers.

THE OTHER HALF OF THE PROBLEM
-----------------------------
Feeding her raw collections would trade fabrication for contradiction — she
would quote figures that disagree with the chart on the page the visitor is
looking at. So every figure here is read from the SAME precomputed documents
the live Netlify functions render from:

    precomputed_indexed_prices     median, YoY, CI, long-run growth
    precomputed_market_charts      days on market
    propradar_suburb_stats         volume + months of supply (see below)

WHAT IS DELIBERATELY WITHHELD
-----------------------------
Domain's sold-side capture is ~53-66% of actual settlements (measured, see
fix-history 2026-07-30). That makes SALES VOLUME and MONTHS OF SUPPLY /
ABSORPTION wrong by roughly 2x in a direction that manufactures a false
"oversupply" story. Those are never emitted as numbers here. Where volume is
genuinely needed it comes from PropRadar, which counts settlements.

Per-quarter medians additionally carry `reliable: false` when their 90% CI is
wider than +/-7%. The rolling 12-month median is the safe headline and is what
this returns; single-quarter medians and QoQ changes are not emitted at all.
"""
from __future__ import annotations

import sys
import threading
import time

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

from shared.db import get_gold_coast_db, normalize_suburb   # noqa: E402

SUBURBS = {"robina", "varsity_lakes", "burleigh_waters"}

# Facts move at most daily (the precompute runs nightly). A cache keeps the
# added latency off a turn that is already 6-15s.
_TTL = 1800
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _money(n) -> str | None:
    """$1,250,000 — never '$1.25m'. Australian convention, CLAUDE.md rule 5."""
    if not isinstance(n, (int, float)):
        return None
    return f"${int(round(n)):,}"


def _dom_change(n) -> str | None:
    """'9.5 days longer' / '8 days quicker' — direction stated, not inferred."""
    if not isinstance(n, (int, float)):
        return None
    d = abs(n)
    d = int(d) if float(d).is_integer() else d
    if n == 0:
        return "unchanged from a year ago"
    return f"{d} days {'longer' if n > 0 else 'quicker'} than a year ago"


def suburb_facts(suburb: str) -> dict | None:
    """Safe-to-quote figures for one suburb, or None if we do not cover it."""
    key = normalize_suburb(suburb or "")
    if key not in SUBURBS:
        return None

    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < _TTL:
            return hit[1]

    db = get_gold_coast_db()
    idx = db["precomputed_indexed_prices"].find_one({"_id": key}) or {}
    dom = db["precomputed_market_charts"].find_one({"_id": f"{key}_days_on_market"}) or {}
    pr = db["propradar_suburb_stats"].find_one({"_id": key}) or {}

    # A blind replace_one from a manual precompute run silently reverts the
    # union medians to Domain-only — Burleigh Waters read $2,115,000 instead of
    # $1,925,000 for ~29 days out of 30 before this was caught. If the marker is
    # missing the median is not trustworthy, so it is withheld rather than
    # quoted with a caveat nobody reads.
    union_ok = idx.get("median_source") == "domain_union_onthehouse"

    md = pr.get("market_dynamics") or {}
    f: dict = {
        "suburb": (pr.get("suburb") or key.replace("_", " ").title()),
        "median_house_price": _money(idx.get("rolling_12m_median_price")) if union_ok else None,
        # Vendor names never leave this module. They were previously written
        # into the basis line and she repeated them verbatim to visitors —
        # "drawn from Domain and onthehouse sales combined". Which suppliers
        # sit behind the database is commercial information; the visitor-facing
        # answer is the Fields internal database, and nothing below it.
        "median_basis": ("rolling 12-month median house price, from the Fields "
                         "internal database") if union_ok else None,
        # Say what the interval IS, not just its endpoints. Labelled
        # `median_range`, she described a statistical confidence interval as
        # "the middle range of sales" — a different and wrong claim. Same
        # failure as the days/percent mix-up: an ambiguous key gets interpreted,
        # and the output guard cannot catch it because both numbers are real.
        "median_confidence_range": (
            f'the true median is very likely between '
            f'{_money(idx.get("rolling_12m_ci_low"))} and '
            f'{_money(idx.get("rolling_12m_ci_high"))} — this is the statistical '
            f'confidence range around the median, NOT the range of sale prices')
            if union_ok and idx.get("rolling_12m_ci_low") else None,
        # Units go IN the value, never implied by the key. Labelled
        # `days_on_market_change_vs_year_ago: 9.5`, the model read a change
        # measured in DAYS as "up 9.5 percent" — a materially different claim,
        # and one the output guard cannot catch because 9.5 is a real figure
        # we supplied. Self-describing values are the only reliable fix.
        "median_year_on_year": (f'{idx["rolling_12m_yoy_pct"]}% higher than a year ago'
                                if union_ok and idx.get("rolling_12m_yoy_pct") is not None else None),
        "days_on_market_median": (f'{dom["latest_quarter_median"]} days'
                                  if dom.get("latest_quarter_median") is not None else None),
        "days_on_market_basis": "median days on market, most recent quarter",
        "days_on_market_change_vs_year_ago": _dom_change(dom.get("yoy_change_days")),
        # This one is a settlement count rather than a listings-derived figure,
        # which is why it is safe to state as a number at all — but the supplier
        # behind it is not named to the visitor.
        "house_sales_last_12_months": md.get("house_sales_12mo"),
        "house_sales_basis": ("settled house sales in the last 12 months, "
                              "from the Fields internal database"),
        "as_of": str(pr.get("as_of") or idx.get("median_computed_at") or "")[:10],
    }
    f = {k: v for k, v in f.items() if v is not None}

    with _lock:
        _cache[key] = (time.time(), f)
    return f


def facts_block(context: dict) -> tuple[str, list[str]]:
    """Render the FACTS the model may quote, plus the list of quotable numbers.

    The second return value is what the output guard checks against — a reply
    containing a figure that is not in it did not come from our data.
    """
    wanted: list[str] = []
    key = (context or {}).get("key")
    readout = (context or {}).get("readout") or ""

    for s in SUBURBS:
        pretty = s.replace("_", " ")
        if pretty in readout.lower() or s in readout.lower():
            wanted.append(s)
    # Nothing identifiable on the page: give her all three. It is three cheap
    # cached reads and it means a visitor asking about any covered suburb from
    # the home page still gets real figures instead of a refusal.
    if not wanted:
        wanted = sorted(SUBURBS)

    blocks, quotable = [], []
    for s in wanted:
        f = suburb_facts(s)
        if not f:
            continue
        lines = [f"### {f['suburb']}"]
        for label, val in f.items():
            if label in ("suburb",):
                continue
            lines.append(f"- {label.replace('_', ' ')}: {val}")
            if isinstance(val, (int, float)) or (isinstance(val, str) and any(c.isdigit() for c in val)):
                quotable.append(str(val))
        blocks.append("\n".join(lines))

    if not blocks:
        return "", []

    body = "\n\n".join(blocks)
    return (
        "\n\n---\n\n## FACTS — the only figures you may state\n\n"
        "These are read live from the same precomputed data the public charts on "
        "this site render from, so quoting them keeps you consistent with the page "
        "the visitor is looking at.\n\n"
        f"{body}\n\n"
        "**Rules for these figures, without exception:**\n"
        "- State a number ONLY if it appears above. Copy it exactly — do not round, "
        "re-derive, average, convert to a different period, or adjust it.\n"
        "- Give the basis line with the figure. It says what the number actually "
        "measures and over what period.\n"
        "- If they ask for something not listed above — a unit median, a street, a "
        "forecast, sales volume for a quarter, months of supply, absorption, a "
        "single property's value — you do NOT have it. Say so plainly and say where "
        "it can be found on the site. Do not estimate it and do not construct it "
        "from the figures above.\n"
        "- Never invent a sample size, a source name, or a date range. If you did "
        "not get it above, you do not know it.\n"
        "- Attribution is ALWAYS 'the Fields internal database' and never anything "
        "else. Do not name a portal, provider, vendor, platform or government "
        "dataset — not even to confirm or deny one the visitor names first. If "
        "asked where the data comes from: it is compiled in the Fields internal "
        "database from commercial sources, and that is the whole answer.\n",
        quotable,
    )

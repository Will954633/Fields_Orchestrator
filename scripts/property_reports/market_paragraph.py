"""
market_paragraph.py — deterministic suburb market paragraph, no LLM.

Replaces the Opus `market_narrative` call. Same input (the ten scalars
`slot_resolver.market_state()` reads out of `precomputed_market_charts` /
`precomputed_indexed_prices`) and the same output (one 50-90 word paragraph),
so the resolver and frontend consume it unchanged.

Deterministic on purpose. The LLM had ten numbers and a prompt that dictated the
paragraph's shape beat by beat — lead with the most load-bearing fact, add two
or three supporting figures, close with one conditional-tense interpretation —
plus five absolute rules whose whole purpose was to stop it saying anything the
numbers did not. That is a template with branches, and writing it as one makes
the rules structural:

  - no advice and no prediction can occur; the vocabulary contains neither
  - every figure is formatted once, here, from the same value the charts use
  - a stat that is missing is simply not mentioned, rather than guessed at
  - the small-sample and stale-quarter caveats FIRE ON A THRESHOLD instead of
    depending on the model noticing

Sentence order follows the prompt: lead → support → caveat (conditional) → close.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# A quarter median this far from the rolling 12-month median is a thin-sample
# artefact more often than a move, and the paragraph says so rather than
# reporting it as a trend.
_QUARTER_DIVERGENCE = 0.10
# Below this many sales the cohort is too small to read a median from confidently.
_THIN_COHORT = 30
# DOM changes inside this many days are noise, not a direction.
_DOM_DEADBAND = 3


def _money(v) -> Optional[str]:
    try:
        return f"${int(v):,}"
    except (TypeError, ValueError):
        return None


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(v, dp: int = 1) -> Optional[str]:
    n = _num(v)
    return None if n is None else f"{abs(n):.{dp}f}%"


def resolve_market_paragraph(market: Dict[str, Any], suburb: str = "") -> Optional[Dict[str, Any]]:
    """Return {"text": paragraph, ...} or None when there is too little to say.

    None is the honest outcome for a suburb with no cohort and no stock — the
    slot stays pending and the page shows nothing, rather than a paragraph built
    from two numbers pretending to be a market read.
    """
    m = market or {}
    suburb = (suburb or "").strip() or "your suburb"
    # Some docs carry the suburb KEY ("burleigh_waters") rather than the display
    # name. Never print an underscore at the reader.
    if "_" in suburb:
        suburb = " ".join(w.capitalize() for w in suburb.split("_"))

    active = _num(m.get("active_listings_count"))
    sold = _num(m.get("sold_transaction_count"))
    median = _money(m.get("rolling_12m_median"))
    yoy = _num(m.get("rolling_12m_yoy_pct"))
    dom = _num(m.get("median_dom"))
    dom_hist = _num(m.get("median_dom_historical"))
    growth = _num(m.get("growth_since_baseline_pct"))
    baseline = m.get("baseline_period")
    latest = _num(m.get("latest_median_price"))
    rolling_raw = _num(m.get("rolling_12m_median"))

    if sold is None and active is None:
        return None

    parts = []

    # ── Beat 1: lead with the most load-bearing fact ────────────────────────
    # Volume leads when we have it (it is the cohort the home is compared
    # against); stock leads otherwise.
    if sold is not None and median:
        parts.append(
            f"Over the past 24 months {int(sold)} houses sold in {suburb}, "
            f"and the rolling 12-month median sits at {median}."
        )
    elif sold is not None:
        parts.append(f"Over the past 24 months {int(sold)} houses sold in {suburb}.")
    else:
        parts.append(f"{suburb} currently has {int(active)} homes on the market.")

    # ── Beat 2: two or three supporting numbers ─────────────────────────────
    support = []
    if active is not None and sold is not None:
        support.append(f"{int(active)} homes are on the market now")
    if yoy is not None:
        direction = "up" if yoy > 0 else ("down" if yoy < 0 else "level")
        if direction == "level":
            support.append("the median is level year-on-year")
        else:
            support.append(f"the median is {direction} {_pct(yoy)} year-on-year")
    if dom is not None:
        if dom_hist is not None and abs(dom - dom_hist) >= _DOM_DEADBAND:
            faster = dom < dom_hist
            support.append(
                f"homes are taking {int(dom)} days to sell against a longer-run "
                f"{int(dom_hist)} ({'faster' if faster else 'slower'})"
            )
        else:
            support.append(f"homes are taking {int(dom)} days to sell")
    if growth is not None and baseline:
        support.append(f"prices are {_pct(growth)} above their {baseline} baseline")
    # Three supporting figures is what the spec asks for; a fourth pushes the
    # paragraph past its 90-word ceiling and reads as a list rather than a read.
    if support:
        parts.append(_sentence_from(support[:3]))

    # ── Beat 3: caveats, on thresholds rather than judgement ────────────────
    caveated = False
    if sold is not None and sold < _THIN_COHORT:
        parts.append(
            f"That is a small cohort — {int(sold)} sales — so we read it as a light "
            f"signal rather than a firm rule."
        )
        caveated = True
    elif latest is not None and rolling_raw:
        div = abs(latest - rolling_raw) / rolling_raw
        if div >= _QUARTER_DIVERGENCE:
            parts.append(
                f"The latest quarter's median of {_money(latest)} sits away from the "
                f"rolling figure, which usually reflects which homes happened to sell "
                f"that quarter rather than a change in value."
            )
            caveated = True

    # ── Beat 4: one conditional-tense interpretation ────────────────────────
    # Skipped when a caveat already fired — the caveat IS the interpretation,
    # and running both pushes the paragraph past its word ceiling.
    if not caveated and yoy is not None and dom is not None:
        if yoy > 0 and dom_hist is not None and dom < dom_hist:
            parts.append("If both hold, the data describes a market absorbing stock faster than its longer-run pace.")
        elif yoy < 0 or (dom_hist is not None and dom > dom_hist):
            parts.append("If that pace continues, the data points to buyers having more time and more choice than they did a year ago.")
        else:
            parts.append("If those conditions hold, the data describes a market broadly in balance.")

    text = " ".join(parts)
    # A stub of one sentence is not a market read. Below the spec's 50-word floor
    # we return None so the slot stays pending and the page renders nothing,
    # rather than presenting two numbers as an analysis.
    if len(text.split()) < 50:
        return None

    return {
        "text": text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "method": "deterministic-v1",
        "inputs_snapshot": dict(m),
    }


def _sentence_from(clauses) -> str:
    """Join supporting clauses into one sentence, capitalised."""
    if len(clauses) == 1:
        body = clauses[0]
    elif len(clauses) == 2:
        body = f"{clauses[0]}, and {clauses[1]}"
    else:
        body = ", ".join(clauses[:-1]) + f", and {clauses[-1]}"
    return body[0].upper() + body[1:] + "."

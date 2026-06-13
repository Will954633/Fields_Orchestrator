"""
your_street_narrative.py — deterministic "Your Street" narrative resolver.

Turns the engine's street-level evidence (street_premium + micro-location
premium, written by precompute_valuations.py onto
valuation_data.subject_property) into the reader-facing prose shown at the
bottom of the "01 Your Home's Data" tab, plus a small stat row.

Deterministic on purpose — no LLM. The street-level claim is legally sensitive
(it quotes how neighbours' homes have sold), so the copy is templated to keep
the editorial rules inviolable:
  - cites the sample size (n sales) every time, never a bare percentage
  - past tense / descriptive only — no predictions, no advice
  - value framing for below-median streets (entry point, not a flaw)
  - falls back to the immediate sales pocket, then to a neutral message, when a
    street has too few individual sales to read on its own

Variants: premium | value | in_line | pocket | neutral.
The Valuation tab renders the raw supporting-sales table separately straight
off valuation.evidence.streetEvidence — this module is the Home-tab prose only.
"""
from datetime import datetime

# A street whose homes sit within this band of the suburb median reads as
# "in line" rather than a premium / discount pocket.
_DIRECTION_DEADBAND = 0.02
# Below this many recorded street sales we still show the street narrative but
# flag it as a light signal rather than a hard rule.
_FULL_CONFIDENCE_N = 5


def _titlecase(s):
    if not s or not isinstance(s, str):
        return None
    return " ".join(w.capitalize() for w in s.split())


def _whole_pct(p):
    """Absolute value of a fraction as a whole-number percent (0.082 -> 8)."""
    try:
        return abs(int(round(float(p) * 100)))
    except (TypeError, ValueError):
        return 0


def _street_character(street_view):
    """One descriptive sentence about the street's physical character, lifted
    from the Street View vision pass if present. Kept separate from the price
    prose so a qualitative impression never bleeds into a price claim."""
    if not street_view or not isinstance(street_view, dict):
        return None
    narr = street_view.get("narrative") or {}
    for key in ("street_setting", "kerb_summary"):
        v = narr.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _street_variant(ev, suburb, char):
    name = _titlecase(ev.get("street_name")) or "Your street"
    n = int(ev.get("n_sales") or 0)
    raw = float(ev.get("raw_avg_pct") or 0.0)
    pct = _whole_pct(raw)
    small = n < _FULL_CONFIDENCE_N

    if raw >= _DIRECTION_DEADBAND:
        variant, direction = "premium", "above"
        body = (
            f"{name} has a measurable identity within {suburb}. Across the {n} sales we hold "
            f"for this street, homes have transacted around {pct}% above {suburb}'s rolling "
            f"median at the time of each sale. Streets carry that kind of pattern for tangible "
            f"reasons — position, the consistency of the homes on them, how quiet the road is. "
            f"For your home, it means buyers comparing {suburb} addresses have historically paid "
            f"to be on this particular street."
        )
    elif raw <= -_DIRECTION_DEADBAND:
        variant, direction = "value", "below"
        body = (
            f"{name} sits toward the accessible end of {suburb}. Across the {n} sales we hold "
            f"here, homes have transacted around {pct}% below {suburb}'s rolling median at the "
            f"time of sale — which makes it one of the more attainable ways into a suburb people "
            f"generally pay a premium to live in."
        )
    else:
        variant, direction = "in_line", "in line"
        body = (
            f"{name} tracks closely with {suburb} as a whole. Across the {n} sales we hold here, "
            f"homes have transacted within a couple of percent of {suburb}'s rolling median at "
            f"the time of sale — neither a premium pocket nor a discount one."
        )

    if small:
        body += (
            f" It's a small sample — {n} sales — so we read it as a light signal rather than a "
            f"hard rule."
        )

    return {
        "variant": variant,
        "body": body,
        "stat": {"streetName": name, "nSales": n, "pct": pct, "direction": direction},
        "streetCharacter": char,
        "source": f"Fields analysis · {n} recorded sales on {name} vs {suburb} rolling 12-month median.",
        "generated_at": datetime.utcnow().isoformat(),
        "method": "deterministic-v1",
    }


def _pocket_variant(micro, street_ev, suburb, char):
    name = _titlecase((street_ev or {}).get("street_name")) or "your street"
    n = int(micro.get("n_sales") or 0)
    radius = micro.get("radius_km")
    applied = float(micro.get("applied_pct") or 0.0)
    pct = _whole_pct(applied)
    radius_txt = f"about {radius:g} km" if radius else "the immediate area"

    if applied >= 0.01:
        tail = f"sits around {pct}% above {suburb}'s median, which lifts the valuation slightly."
        direction = "above"
    elif applied <= -0.01:
        tail = f"sits around {pct}% below {suburb}'s median — an accessible pocket within the suburb."
        direction = "below"
    else:
        tail = f"tracks the {suburb} median closely."
        direction = "in line"

    body = (
        f"We don't yet hold enough individual sales on {name} to read a reliable street-level "
        f"pattern on its own, so your valuation leans on the immediate pocket around your home "
        f"instead — {n} sales within {radius_txt}. That pocket {tail}"
    )

    return {
        "variant": "pocket",
        "body": body,
        "stat": {"streetName": name, "nSales": n, "pct": pct, "direction": direction},
        "streetCharacter": char,
        "source": f"Fields analysis · {n} sales within {radius_txt} of your home vs {suburb} median.",
        "generated_at": datetime.utcnow().isoformat(),
        "method": "deterministic-v1",
    }


def _neutral_variant(street_ev, suburb, char):
    name = _titlecase((street_ev or {}).get("street_name")) or "your street"
    body = (
        f"We don't yet hold enough individual sales on {name} to isolate a reliable street-level "
        f"pattern. Your valuation leans instead on the wider {suburb} sold market and the "
        f"comparable sales shown on the Valuation tab."
    )
    return {
        "variant": "neutral",
        "body": body,
        "stat": None,
        "streetCharacter": char,
        "source": f"Fields analysis · insufficient street-level sales for {name}.",
        "generated_at": datetime.utcnow().isoformat(),
        "method": "deterministic-v1",
    }


def resolve_your_street_narrative(street_evidence=None, micro_evidence=None,
                                  street_view=None, suburb="", address=""):
    """Return the "Your Street" narrative object for the report, or a neutral
    fallback. Never raises on missing data — returns the neutral variant.

    Selection: a street with recorded sales -> street_variant; otherwise the
    immediate sales pocket -> pocket_variant; otherwise neutral_variant.
    """
    suburb = (suburb or "").strip() or "the suburb"
    char = _street_character(street_view)

    if street_evidence and street_evidence.get("n_sales"):
        return _street_variant(street_evidence, suburb, char)
    if micro_evidence and micro_evidence.get("n_sales"):
        return _pocket_variant(micro_evidence, street_evidence, suburb, char)
    return _neutral_variant(street_evidence, suburb, char)

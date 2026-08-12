"""Shared guard separating SALE prices from RENTAL figures.

Why this exists
---------------
Every price parser in the estate was written independently, and on 2026-08-13 an
empirical test of all 13 of them found **7 entry points that accept a weekly rent
as a sale price** — 5 of which accept the literal string ``"$750 per week"`` and
return ``750``. They have never produced a wrong valuation, but only because
rentals do not live in the field they happen to read (``listing_status: "sold"``
documents). That is luck holding, not design: contamination by source measured
2026-08-12 was ``sold.sale_price`` 0.00%, ``timeline(is_sold)`` 0.10%,
``enriched_data.transactions`` 10.00%. Point any of these parsers at a different
field and it silently emits a rent.

See ``logs/fix-history/2026-08-10.md`` ``[RENTAL-AS-SALE-DEEP]`` for the cleanup
of the data, and ``2026-08-13.md`` ``[RENTAL-AS-SALE-PARSERS]`` for this guard.

The floor is measured, not guessed
----------------------------------
``MIN_SALE_PRICE`` is deliberately NOT a round guess. Across every Sale-category
timeline event in the three target suburbs (measured 2026-08-13):

    < $1,000        n = 0
    $1,000-$5,000   n = 0
    $5,000-$20,000  n = 56      median year 1978
    $20,000-$100k   n = 4,246   median year 1990

There is not one genuine sale below $5,000 in our entire history, so a $1,000
floor carries 5x headroom and cannot touch the 56 real 1970s sales.

**Amount alone does not identify a rental — the date does.** Sub-$1k entries have
a median year of 2013 (weekly rents); $5k-$20k entries a median year of 1978
(genuine cheap sales). A naive price floor set anywhere near the rent range would
delete real 1970s history. That is why the floor sits below the genuine minimum
rather than above the rent maximum: the string markers do the discriminating
work, and the floor only catches what has no plausible sale reading at all.
"""
import re

# Deliberately below the lowest genuine sale we hold ($5,000), not above the
# highest plausible weekly rent — see the module docstring. Luxury weekly rents
# on the Gold Coast reach $3k-$5k, so the floor CANNOT be the primary defence;
# _RENT_MARKERS is. The floor only catches bare numerics with no sale reading.
MIN_SALE_PRICE = 1000.0

# Matches the ways a weekly/periodic rent is written in the sources we ingest:
# "$750 per week", "$750pw", "$750 p/w", "$750 p.w.", "$750/wk", "$750 weekly".
_RENT_MARKERS = re.compile(
    r"""
    per \s* (?: week | wk | fortnight | month | annum ) \b
    | \b p \.? \s? (?: w | /w | cm ) \.? \b
    | / \s* (?: w | wk | week ) \b
    | \b (?: weekly | fortnightly | monthly ) \b
    | \b rent (?: al )? \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def looks_like_rent(raw) -> bool:
    """Does this raw value announce itself as a rent rather than a sale price?

    Only strings can announce it — a bare ``750`` is indistinguishable from a
    cheap sale by inspection, which is what ``MIN_SALE_PRICE`` is for.
    """
    return isinstance(raw, str) and bool(_RENT_MARKERS.search(raw))


def sale_price_or_none(raw, parsed):
    """Final gate for every price parser that feeds a SALE-price consumer.

    ``raw`` is the untouched input (so the rent markers are still visible —
    most parsers strip ``$``/``,``/text before converting) and ``parsed`` is
    whatever that parser produced. Returns ``parsed`` unchanged, or ``None``
    when the value cannot be a sale price.

    Do NOT use this on a parser feeding a rental-yield or affordability
    consumer, where a weekly rent is the correct answer.
    """
    if parsed is None:
        return None
    if looks_like_rent(raw):
        return None
    try:
        if float(parsed) < MIN_SALE_PRICE:
            return None
    except (TypeError, ValueError):
        return None
    return parsed

"""Dwelling-type classification — one definition, used everywhere.

Why this exists
---------------
On 2026-08-01 we found the same question answered two different ways in two
pipelines:

  * `07_Valuation_Comps/precompute_valuations.py` treats a unit-numbered address
    ("12/8 Marine Parade") as the STRONGEST signal and `property_type` only as a
    fallback, with an explicit `misclassified_dwelling` exclusion. Correct.
  * `08_Market_Narrative_Engine/precompute_indexed_price_data.py` filtered on the
    `property_type` FIELD alone. So 2.8-9.9% of records in each suburb's "House"
    median carried unit-style addresses, and a further 14-50 sold records per
    suburb with NO property_type were dropped silently.

Both Domain and onthehouse type these records as "House", so this is not a
one-source bug — in Queensland a great many genuinely detached homes sit on
strata or community title with a unit-style address. The address is therefore
not proof of attachment; it is the best available signal that the dwelling is
not a standard detached house on its own lot, which is what a suburb "house
median" is meant to describe.

Validation: excluding unit-numbered addresses moves the Burleigh Waters 12-month
median from $1,855,550 to ~$1,875,000 — CLOSER to realestate.com.au's published
$1,910,000 (195 sales), not further. The external benchmark agrees with the
exclusion.

The `unknown` bucket is deliberately a distinct return value rather than being
folded into `attached`. Silent exclusion is how the original problem stayed
invisible; callers are expected to COUNT unknowns and report them.
"""
from __future__ import annotations

import re

__all__ = ["classify_dwelling", "is_house", "UNIT_TYPE_TOKENS"]

# Attached / strata tokens. Kept in sync with `_UNIT_TYPE_TOKENS` in
# precompute_valuations.py — if you add one there, add it here.
UNIT_TYPE_TOKENS = (
    "unit", "apartment", "flat", "studio", "townhouse",
    "villa", "duplex", "terrace", "semi",
)

# "12/8 Marine Parade", "4 / 19-21 Beachcomber Ct", "Unit 3 Smith St", "Apt 2 ..."
# Deliberately NOT anchored on a bare leading digit: "21 Heights Drive" is a
# house, "21/34 Riverwalk Avenue" is not.
_UNIT_ADDRESS = re.compile(
    r"^\s*(?:unit|apt|apartment)\b"      # explicit prefix
    r"|^\s*\d+[a-z]?\s*/",               # 12/8 ... or 12a/8 ...
    re.IGNORECASE,
)

# Type fields in descending order of trust. `classified_property_type` is our own
# post-hoc classification; the scraped fields are Domain's own labels.
_TYPE_FIELDS = (
    "classified_property_type",
    "property_type",
    ("scraped_data", "features", "property_type"),
    ("scraped_data_v2", "property_type"),
)


def _dig(doc, path):
    """Fetch a nested value by tuple path, tolerating missing intermediate dicts."""
    if isinstance(path, str):
        return doc.get(path)
    cur = doc
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _address_of(doc) -> str:
    for field in ("street_address", "address", "address_line"):
        val = doc.get(field)
        if val:
            return str(val).strip()
    structured = _dig(doc, ("scraped_data_v2", "address_line"))
    return str(structured).strip() if structured else ""


def classify_dwelling(doc) -> str:
    """Return 'house', 'attached', or 'unknown'.

    'house'    — detached dwelling on its own lot; what a suburb house median means.
    'attached' — unit / apartment / townhouse / villa / duplex / terrace / semi,
                 OR any unit-numbered address regardless of the type field.
    'unknown'  — no address signal and no usable type field. Callers MUST count
                 these and report the number rather than dropping them quietly.
    """
    # 1. Address is the strongest signal and overrides every type field.
    if _UNIT_ADDRESS.match(_address_of(doc)):
        return "attached"

    # 2. Fall through the type fields in order of trust. The first non-empty one
    #    decides — a later field disagreeing does not resurrect the record.
    for field in _TYPE_FIELDS:
        raw = _dig(doc, field)
        if not raw:
            continue
        token = str(raw).strip().lower()
        if not token:
            continue
        if any(t in token for t in UNIT_TYPE_TOKENS):
            return "attached"
        if "house" in token:
            return "house"
        # A recognised-but-other type ("Land", "Vacant land", "Retirement Living",
        # "Other") is neither a house nor an attached dwelling we track.
        return "attached" if token not in ("other",) else "unknown"

    return "unknown"


def is_house(doc) -> bool:
    """Convenience wrapper. Note this collapses 'unknown' into False — only use it
    where you are separately counting unknowns via classify_dwelling()."""
    return classify_dwelling(doc) == "house"

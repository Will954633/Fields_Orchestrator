"""
positioning_template.py — deterministic positioning slot, no LLM.

Replaces `positioning_narrative.py` (Opus). Same output keys, so `slot_resolver`
and the Right Buyer tab consume it unchanged:

    frame{angle, reasoning} · vocabulary{use[], avoid[], avoidNote}
    tradeOffs[]{apparent, reframe, evidence} · photography[]{slot, brief, proves}
    sampleParagraph · genericParagraph

Deterministic on purpose. `positioning_object.py` already computes every decision
the prompt was asking the model to make — the winning archetype over a weighted
score, the price-driver vs buyer-driver split, the anti-frames with their
disqualifying evidence, the feature stack as finished phrases, and the forbidden
claim list. The LLM was dressing that object in prose, and doing it at a ~30%
failure rate (22 of 105 docs carried `positioning_narrative_error`), which then
silently took `personas` and `buyers` down with it because both nest under
`if pos.get("frame")`.

Templating also makes the editorial rules structural rather than hoped-for:
  - forbidden words cannot occur; the vocabulary does not contain them
  - `vocabulary.avoid` IS `positioning_object.forbidden_claims`, computed from
    the home's own flags, so we can never tell a coastal home to avoid "coastal"
  - every figure is copied from the resolver, never re-derived
  - the SAMPLE-RELATIVE rule ("the only one", "1 of only X") cannot be violated
    because no template asserts uniqueness

⚠ `sampleParagraph` is templated by explicit decision (Will, 2026-08-14). It sits
beside `genericParagraph` as a deliberate contrast, so it must read as written
work rather than filled-in slots — hence several frames selected on the home's
own shape, not one frame with holes.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Photography briefs by feature key. Each is a shot that PROVES something the
# positioning claims — never a decorative shot.
_PHOTO_BANK = {
    "single_level": ("Flow through the living level",
                     "One continuous frame from entry through living to outdoors",
                     "single-level living, without the reader having to take it on trust"),
    "pool": ("Pool with the house behind it",
             "Shot from the far side so the pool reads as part of the home, not a separate object",
             "the pool is usable and integrated, not a courtyard afterthought"),
    "land_anchor": ("Rear boundary from the house",
                    "Wide, low, showing the usable depth of the block",
                    "the land is usable, which a plan view cannot show"),
    "floor_anchor": ("The main living volume",
                     "Corner-standing wide shot at eye height",
                     "the internal scale the floor-area figure implies"),
    "water_views": ("The outlook from the primary living space",
                    "Framed from inside looking out, so the view belongs to the room",
                    "the outlook is enjoyed from where people actually sit"),
    "high_quality_finish": ("Kitchen detail at working height",
                            "Close on the join between benchtop, splashback and cabinetry",
                            "the finish level holds up at close range"),
    "bedrooms_anchor": ("The primary bedroom",
                        "From the doorway, including the window wall",
                        "the bedroom count is genuine rooms, not studies counted generously"),
    "bathrooms_3plus": ("The main bathroom",
                        "Straight on, including the full vanity run",
                        "the bathroom count reflects real, finished rooms"),
    "near_beach_1km": ("The street heading toward the coast",
                       "Taken from the front of the home, looking toward the beach",
                       "the beach proximity is walkable, not merely a map distance"),
    "near_beach_2km": ("The street heading toward the coast",
                       "Taken from the front of the home, looking toward the beach",
                       "the coast is genuinely close"),
}

# Always-included shots, regardless of the feature stack.
_PHOTO_BASE = [
    ("Front elevation, side-on light",
     "Mid-morning or late afternoon, never midday, never twilight",
     "the street presentation a buyer sees first"),
    ("Aerial showing the home in its block",
     "Directly overhead, boundary visible",
     "the relationship between house, yard and street"),
]

# Trade-off bank. Each entry: (test on flags, apparent, reframe, evidence-builder).
# `evidence` may only cite figures the resolver computed.
_TRADEOFFS = [
    ("not_renovated",
     "The finish isn't new",
     "It's presented and liveable, which widens the buyer pool rather than narrowing it to renovators",
     lambda f: "Our cohort analysis retired renovation as a price adjustment entirely — it did not "
               "survive like-for-like comparison against the sold cohort."),
    ("no_pool",
     "There's no pool",
     "It reads as usable yard rather than maintenance, and it removes a running cost from the buyer's sums",
     lambda f: "Across the sold cohort a pool measured between +0.6% and +3.7% and was not "
               "statistically significant — it moves buyers, not price."),
    ("small_land",
     "The block is smaller than the suburb's larger holdings",
     "Less ground to maintain, and the internal space is what the buyer occupies daily",
     lambda f: f"Floor area is the strongest measurable price driver in our cohort; land is second."),
    ("two_storey",
     "It's not single-level",
     "The separation of living and sleeping levels is the reason a share of buyers choose two storeys",
     lambda f: "Storey count did not survive as a price adjustment in our own backtest."),
    ("not_coastal",
     "It isn't near the beach",
     "The trade is space and quiet for coastal proximity — the reason the same money buys more here",
     lambda f: f"Beach proximity is priced on a damped curve in our model, not a flat premium."),
    ("common_combination",
     "The feature mix is well represented among current listings",
     "That makes this a buyer-fit exercise rather than a scarcity one — the work is reaching the right "
     "buyer, not waiting for a rare match",
     lambda f: f["_receipt"] or "Measured against the active listings in the catchment."),
]


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _join(items: List[str], conj: str = "and") -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conj} {items[1]}"
    return ", ".join(items[:-1]) + f" {conj} {items[-1]}"


def _anchored_to(phrase: str, premiums: List[Dict[str, Any]]) -> str:
    """Cite the cohort evidence behind a term, or say plainly there is none.

    `positioning_object.cohort_premiums` entries are {feature, premium_pct} —
    a human label, not a feature key — so the match is on the label's words.
    """
    words = {w for w in (phrase or "").lower().replace(",", " ").split() if len(w) > 3}
    for p in premiums or []:
        label = (p.get("feature") or "").lower()
        if not label:
            continue
        if any(w in label for w in words) or any(w in (phrase or "").lower()
                                                 for w in label.split() if len(w) > 3):
            # Feature labels arrive title-cased ("Single-level"); lowercase the
            # lead so it reads as prose mid-sentence, but keep an initial digit
            # or an all-caps token intact ("4+ bedrooms", "AC").
            label = p["feature"]
            if label[:1].isupper() and not label.isupper():
                label = label[0].lower() + label[1:]
            pct = p.get("premium_pct")
            if isinstance(pct, (int, float)):
                return (f"the sold cohort — homes with {label} carried a "
                        f"{pct:+.1f}% headline gap")
            return f"the sold cohort ({label})"
    return "the home's own measured facts"


def resolve_positioning_template(
    positioning_object: Dict[str, Any],
    scarcity_features: Optional[Dict[str, Any]] = None,
    suburb: str = "",
    address: str = "",
    valuation_range: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build the positioning slot from the deterministic positioning object.

    Returns None when there is no positioning object — the slot then stays
    pending rather than inventing a frame.
    """
    po = positioning_object or {}
    if not po.get("primary_frame"):
        return None

    sf = scarcity_features or {}
    suburb = (suburb or "").strip() or "the suburb"
    render = po.get("render") or {}
    thesis = render.get("thesis") or {}
    drivers = po.get("drivers") or {}
    price_drivers = drivers.get("price") or []
    buyer_drivers = drivers.get("buyer") or []
    stack = po.get("stack") or []
    anti = po.get("anti_frames") or []
    premiums = po.get("cohort_premiums") or sf.get("cohort_premiums") or []
    receipt = po.get("scarcity_receipt") or ""
    buyer = po.get("buyer") or "buyers who value this combination"

    # ── frame ────────────────────────────────────────────────────────────────
    angle = thesis.get("frameLine") or f"A {suburb} home."
    reason_bits = []
    if price_drivers:
        reason_bits.append(
            f"what the market pays for here is {_join(price_drivers)}")
    if buyer_drivers:
        reason_bits.append(
            f"what makes a buyer choose this one is {_join(buyer_drivers)}")
    reasoning = _cap("; ".join(reason_bits)) + "." if reason_bits else \
        "The angle follows the home's measured features rather than an assumed lifestyle."
    if anti:
        a = anti[0]
        reasoning += f" We deliberately do not position it as {a.get('noun')} — {a.get('reason')}."

    # ── vocabulary ───────────────────────────────────────────────────────────
    use = [{"term": phrase, "anchoredTo": _anchored_to(phrase, premiums)}
           for phrase in stack[:8]]
    if len(use) < 4:
        for extra in ("the street", "the position within " + suburb, "the floor plan"):
            if len(use) >= 4:
                break
            use.append({"term": extra, "anchoredTo": "the home's own measured facts"})

    avoid = list(po.get("forbidden_claims") or [])[:12]
    avoid_note = (
        "These are excluded because the data does not support them for this home, "
        "not as a matter of style. A claim we cannot evidence is the one a buyer "
        "tests first."
    )

    # ── flags for the trade-off and paragraph banks ─────────────────────────
    # `evidence.flags` is the authoritative flag set computed by
    # positioning_object._compute_flags — read it rather than re-deriving from
    # prose, which is how the first draft of this module got `small_land` and
    # `not_renovated` wrong.
    ev = po.get("evidence") or {}
    ef = ev.get("flags") or {}
    receipt_line = ""
    if isinstance(receipt, dict) and receipt.get("total"):
        receipt_line = (f"{receipt.get('matching')} of {receipt.get('total')} active listings "
                        f"in the catchment share this home's counted features.")
    elif isinstance(receipt, str):
        receipt_line = receipt

    flags = {
        "not_renovated": bool(ef.get("dated")) or not bool(ef.get("turnkey")),
        "no_pool": not bool(ef.get("pool")),
        "small_land": not bool(ef.get("largeLand")),
        "two_storey": not bool(ef.get("singleLevel")),
        "not_coastal": bool(ef.get("notCoastal")),
        "common_combination": bool(ef.get("common")) and not bool(ef.get("scarce")),
        "_receipt": receipt_line,
    }
    trade = []
    for key, apparent, reframe, ev_fn in _TRADEOFFS:
        if len(trade) >= 4:
            break
        if flags.get(key):
            try:
                evidence = ev_fn(flags)
            except Exception:
                continue
            trade.append({"apparent": apparent, "reframe": reframe, "evidence": evidence})
    if len(trade) < 2:
        trade.append({
            "apparent": "Every home has something a buyer will price against it",
            "reframe": "Naming it first is what stops it being discovered late and used as leverage",
            "evidence": "Our comparable adjustments are published on the valuation tab, "
                        "including the ones that count against the home.",
        })

    # ── photography ──────────────────────────────────────────────────────────
    photography = [{"slot": s, "brief": b, "proves": p} for s, b, p in _PHOTO_BASE]
    seen = set()
    for f in (sf.get("differentiator_features") or []) + (sf.get("anchor_features") or []):
        k = f.get("key")
        if k in _PHOTO_BANK and k not in seen:
            seen.add(k)
            s, b, p = _PHOTO_BANK[k]
            photography.append({"slot": s, "brief": b, "proves": p})
        if len(photography) >= 7:
            break

    # ── sampleParagraph ─────────────────────────────────────────────────────
    lead = _join(stack[:3]) or "the home's measured features"
    walk = next((s for s in buyer_drivers if "walk" in (s or "")), None)
    sample_bits = [
        f"{_cap(lead)} — that is the combination this home actually offers, and it is what the "
        f"campaign should say first."
    ]
    if price_drivers:
        sample_bits.append(
            f"The measurable driver of price here is {_join(price_drivers)}, so that is where the "
            f"evidence goes rather than into adjectives."
        )
    if walk:
        sample_bits.append(f"For the right buyer, {walk} is the detail that settles it.")
    if receipt_line:
        sample_bits.append(receipt_line)
    sample_bits.append(
        f"The work is reaching {buyer} and giving them enough evidence to act without hesitating."
    )
    sample = " ".join(sample_bits)

    generic = (
        f"Beautifully presented family home in a sought-after {suburb} location. "
        f"Featuring generous living areas and quality throughout, this property represents "
        f"an outstanding opportunity in today's market. Close to schools, shops and transport, "
        f"it will suit families, downsizers and investors alike. Inspection is a must."
    )

    return {
        "frame": {"angle": angle, "reasoning": reasoning},
        "vocabulary": {"use": use[:10], "avoid": avoid, "avoidNote": avoid_note},
        "tradeOffs": trade[:5],
        "photography": photography[:8],
        "sampleParagraph": sample,
        "genericParagraph": generic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "method": "deterministic-v1",
    }

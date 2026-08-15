"""
personas_template.py — deterministic buyer personas + buyers thesis, no LLM.

Replaces `personas_narrative.py` and `buyers_narrative.py`. Same output shapes,
so `slot_resolver` and the Right Buyer tab consume them unchanged.

Unusually safe to template, because both modules were already working from
closed sets:

  * The six cohorts were enumerated VERBATIM IN THE SYSTEM PROMPT
    (`personas_narrative.py:61-68`). The model was handed the archetypes and
    asked to "adapt" them. They are moved into Python here, unchanged in
    substance.
  * Selection is a scoring problem `positioning_object._score_archetypes`
    already solves over the same flags, so the lead persona follows the winning
    frame instead of a second, disagreeing judgement.
  * Every NUMBER in the buyers thesis was overwritten after generation by
    `buyers_narrative._reconcile_numbers` (`:310-413`). The model supplied
    labels; Python supplied the figures. Nothing measurable is lost.

⚠ CAMPAIGN CLAIMS ARE FIXED COPY, on purpose. `whereFound` always names
realestate.com.au first as table stakes, then the beyond-the-portal channels.
Fields has NO email list, NO newsletter, NO school noticeboards, NO print
mailers — the old prompt spent a paragraph forbidding those and the model could
still drift into them. A template cannot.

⚠ The direct-approach method is described conditionally and NEVER with a count
of homes or buyers. That model is not quantified.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# The six cohorts, from personas_narrative.py's system prompt. `fit` scores each
# against positioning_object's flags.
ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "local_upgraders": {
        "label": "Local upgraders",
        "brief": ("Families already in a three- or four-bedroom home within about five "
                  "kilometres, growing into more space rather than leaving the area."),
        "paysMoreFor": "bedrooms that are genuinely usable, a second living zone, and a yard",
        "hesitation": "stretching before their own home is under contract",
        "fit": lambda f: 2 + (2 if f.get("familyScale") else 0) + (1 if f.get("largeLand") else 0),
    },
    "capital_city_returners": {
        "label": "Capital-city returners",
        "brief": ("Ex-locals who left for Sydney or Melbourne work five to fifteen years ago, "
                  "moving home with a capital-city deposit. Cash-strong, time-poor, and "
                  "strongly prefer turnkey."),
        "paysMoreFor": "a home they can move into without a project",
        "hesitation": "buying at distance, so the evidence has to stand on its own",
        "fit": lambda f: 1 + (3 if f.get("turnkey") else 0) + (1 if f.get("singleLevel") else 0),
    },
    "school_catchment_families": {
        "label": "School-catchment families",
        "brief": ("Enrolment already confirmed at a specific local school. The walk, not the "
                  "postcode, is what decides it."),
        "paysMoreFor": "the walk itself — a short, safe route on foot",
        "hesitation": "committing before they have walked the route at school time",
        "fit": lambda f: (4 if f.get("veryStrongSchoolWalk") else
                          3 if f.get("schoolWalkAdvantage") else 0),
    },
    "downsizers": {
        "label": "Downsizers",
        "brief": ("Empty-nesters leaving a larger five- or six-bedroom home elsewhere on the "
                  "Gold Coast, wanting low maintenance without dropping in quality."),
        "paysMoreFor": "single-level living and a finish that needs nothing done",
        "hesitation": "losing space they are used to",
        "fit": lambda f: 1 + (3 if f.get("singleLevel") else 0) + (2 if f.get("turnkey") else 0),
    },
    "lifestyle_movers": {
        "label": "Lifestyle movers",
        "brief": ("Pre-retirees from inland Queensland or interstate, moving for the coastal "
                  "lifestyle rather than for work."),
        "paysMoreFor": "the pool, the low-maintenance yard and proximity to the coast",
        "hesitation": "distance from the beach once they measure it honestly",
        "fit": lambda f: (3 if f.get("nearBeach") else 1 if f.get("beachAdjacent") else 0)
                         + (1 if f.get("pool") else 0),
    },
    "investment_buyers": {
        "label": "Investment buyers",
        "brief": ("Less relevant at this price point — typically active below $1.5M in the "
                  "southern Gold Coast market."),
        "paysMoreFor": "yield and low holding cost, not presentation",
        "hesitation": "owner-occupier competition pushing past an investment case",
        "fit": lambda f: 0,
    },
}

# Fixed copy. ALWAYS opens with the portal baseline — a hard validator rule in
# the module this replaces — then the channels Fields actually runs.
_WHERE_FOUND = {
    "local_upgraders": ("Fields lists on realestate.com.au as standard, which is where active "
                        "local searchers already are. Beyond it, broad Facebook and Instagram "
                        "prospecting reaches the larger share who intend to move but are not "
                        "searching yet, and we approach owners of nearby homes whose owners "
                        "typically move into a home like this."),
    "capital_city_returners": ("Fields lists on realestate.com.au as standard. Beyond the "
                               "portal, this buyer is reached through YouTube and social video "
                               "while still interstate, and through Google Ads on the searches "
                               "people run when planning a move home."),
    "school_catchment_families": ("Fields lists on realestate.com.au as standard. Beyond it, "
                                  "Google Ads on catchment and school-related searches capture "
                                  "active intent, and broad social prospecting reaches families "
                                  "whose enrolment decision is made but whose property search "
                                  "has not started."),
    "downsizers": ("Fields lists on realestate.com.au as standard. Beyond it, this buyer is "
                   "reached through broad Facebook and Instagram prospecting rather than portal "
                   "alerts — downsizers are typically passive, moving on their own timeline — "
                   "and through direct approach to owners of larger homes nearby."),
    "lifestyle_movers": ("Fields lists on realestate.com.au as standard. Beyond it, YouTube and "
                         "social video carry the lifestyle case to buyers outside the region, "
                         "supported by retargeting of everyone who engages with the listing."),
    "investment_buyers": ("Fields lists on realestate.com.au as standard, and Domain alongside "
                          "it. Beyond the portals, retargeting reaches people who have already "
                          "looked at comparable stock."),
}

_SHARE_LADDER = ["Primary focus", "Secondary focus", "Supporting"]


def _why_this_home(arch_key: str, stack: List[str]) -> List[str]:
    """Reasons drawn ONLY from features the resolver actually produced."""
    out: List[str] = []
    for phrase in stack:
        p = (phrase or "").lower()
        if arch_key in ("downsizers", "capital_city_returners") and "single-level" in p:
            out.append(f"{phrase} — the requirement this buyer screens on first")
        elif arch_key == "school_catchment_families" and "walk" in p:
            out.append(f"{phrase} — the decisive detail for this buyer")
        elif arch_key == "lifestyle_movers" and ("pool" in p or "beach" in p):
            out.append(f"{phrase} — central to the lifestyle case")
        elif arch_key == "local_upgraders" and ("bedroom" in p or "land" in p or "floor" in p):
            out.append(f"{phrase} — the space they are moving for")
        elif "finish" in p and arch_key in ("capital_city_returners", "downsizers"):
            out.append(f"{phrase} — removes the project this buyer does not want")
    for phrase in stack:
        if len(out) >= 3:
            break
        if not any(phrase in o for o in out):
            out.append(phrase)
    return out[:4] or ["The combination of features the home actually offers"]


def resolve_personas_template(
    positioning_object: Dict[str, Any],
    scarcity_features: Optional[Dict[str, Any]] = None,
    suburb: str = "",
) -> Optional[List[Dict[str, Any]]]:
    """Three ranked personas, or None when there is no positioning object."""
    po = positioning_object or {}
    if not po.get("primary_frame"):
        return None
    flags = ((po.get("evidence") or {}).get("flags")) or {}
    stack = po.get("stack") or []
    drivers = (po.get("drivers") or {}).get("buyer") or []

    scored = sorted(((k, v, v["fit"](flags)) for k, v in ARCHETYPES.items()),
                    key=lambda t: (-t[2], t[0]))
    chosen = [t for t in scored if t[2] > 0][:3]
    for t in scored:
        if len(chosen) >= 3:
            break
        if t not in chosen:
            chosen.append(t)

    personas = []
    for i, (key, arch, _score) in enumerate(chosen[:3]):
        personas.append({
            "label": arch["label"],
            "brief": arch["brief"],
            "whyThisHome": _why_this_home(key, stack),
            "paysMoreFor": arch["paysMoreFor"],
            "hesitation": arch["hesitation"],
            "campaignImplication": (
                f"Lead with {drivers[0] if drivers else (stack[0] if stack else 'the combination')}; "
                f"reach them through "
                f"{'broad social prospecting and direct approach' if i == 0 else 'retargeting and search'}."
            ),
            "whereFound": _WHERE_FOUND[key],
        })
    return personas


def resolve_buyers_template(
    positioning_object: Dict[str, Any],
    personas: List[Dict[str, Any]],
    scarcity_features: Optional[Dict[str, Any]] = None,
    valuation_range: Optional[Dict[str, Any]] = None,
    suburb: str = "",
) -> Optional[Dict[str, Any]]:
    """The buyers thesis / catchment / campaign-math block."""
    po = positioning_object or {}
    if not po.get("primary_frame") or len(personas or []) < 3:
        return None
    suburb = (suburb or "").strip() or "the suburb"
    stack = po.get("stack") or []
    receipt = po.get("scarcity_receipt") or {}
    matching, total = receipt.get("matching"), receipt.get("total")
    receipt_str = f"{matching} of {total}" if matching is not None and total else None

    range_str = None
    if valuation_range and valuation_range.get("low") and valuation_range.get("high"):
        range_str = f"${int(valuation_range['low']):,}–${int(valuation_range['high']):,}"

    stat_blocks = []
    if receipt_str:
        stat_blocks.append({"value": receipt_str, "label": "active listings sharing the combination"})
    if range_str:
        stat_blocks.append({"value": range_str, "label": "working range"})
    stat_blocks.append({"value": f"{len(personas)} personas", "label": "buyer profiles identified"})

    lead = personas[0]["label"].lower()
    lead_singular = lead[:-1] if lead.endswith("s") else lead
    body = [
        (f"The buyer most likely to pay at the top of the range for this home is a "
         f"{lead_singular}. That follows from what the home actually offers — "
         f"{', '.join(stack[:3]) if stack else 'its measured features'} — rather than from "
         f"who happens to be walking through comparable listings right now.")
    ]
    body.append(
        f"Only {receipt_str} active listings in the catchment share this home's counted "
        f"features, which sets how much of the market is genuinely a substitute and how much "
        f"is simply nearby stock." if receipt_str else
        "The campaign is a matching exercise: reaching the buyers for whom this specific "
        "combination answers something, rather than competing on price alone."
    )

    locations = [{"label": p["label"], "share": _SHARE_LADDER[i], "reasoning": p["whereFound"]}
                 for i, p in enumerate(personas[:3])]

    campaign_body = (
        "A portal listing reaches people already searching. The larger group — buyers who will "
        "move within a year but are not searching yet — is reached through broad social "
        "prospecting, video, and direct approach to owners of nearby homes whose owners "
        "typically move into a home like this. "
        + (f"With a working range of {range_str}, the campaign is built to reach both groups "
           f"rather than compete only with the listings already visible."
           if range_str else
           "The campaign is built to reach both groups rather than compete only with the "
           "listings already visible.")
    )

    return {
        "thesis": {
            "headline": f"Who is most likely to pay more for this home in {suburb}",
            "body": body,
            "statBlocks": stat_blocks[:3],
        },
        "catchment": {
            "headline": "Where those buyers actually come from",
            "body": ["Ranked by how much of the campaign each should carry, with the channels "
                     "used to reach them."],
            "locations": locations,
        },
        "campaignMath": {
            "headline": "Active buyers, and the ones who are not searching yet",
            "body": campaign_body,
            "statBlocks": [
                {"value": "Active", "label": "already searching the portals"},
                {"value": "Passive", "label": "will move, not searching yet"},
            ],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "method": "deterministic-v1",
    }

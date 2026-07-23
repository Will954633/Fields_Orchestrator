"""
Personas narrative resolver — Opus 4.7 identifies the three buyer personas
most likely to pay top of the range for the subject property, anchored to
its specific feature stack and cohort context.

Output is one array of 3 personas matching the frontend `Persona` shape
in homeFixture.ts. Used by both PositioningTab (as a companion section)
and BuyersTab (as the persona cards).

Schema per persona:
  {
    "label": "string — 3-6 word title, e.g. 'Southern Gold Coast upgraders'",
    "brief": "string — 1-2 sentence demographic + life-stage description",
    "whyThisHome": ["string", "string", ...]  // 3-5 reasons specific to subject
    "whereFound": "string — 2-3 sentence channel/location for outreach"
  }

The resolver does NOT hardcode persona archetypes — it lets Opus reason
from the property's notable features + cohort premiums + catchment to
identify which 3 buyer profiles are most defensible.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scripts.property_reports.valuation_format import display_range
from scripts.property_reports.cohort_premiums import premium_prompt_lines

logger = logging.getLogger(__name__)


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 12]
MODEL = "claude-opus-4-7"
MAX_TOKENS = 2200

# Reach channels Fields does NOT operate. The model used to be handed these as a
# menu ("best reached via school newsletters / custom audiences / LinkedIn / print
# mailers…") and dutifully repeated them on live seller-facing pages. They are now
# banned: any of these strings in the generated prose triggers regeneration.
# Allowed (our real direct-approach method): "direct approach", "letterbox",
# "direct mail", "approach them directly" — none appear below.
FORBIDDEN_CHANNELS = [
    "newsletter", "noticeboard", "flyer", "school gate", "school-gate",
    "word of mouth", "word-of-mouth", "mailer", "mailing list", "newspaper",
    "real-estate-section", "real estate section", "linkedin",
    "custom audience", "open-home register", "open home register",
    "subscriber",  # Fields has NO subscriber/newsletter list (owned audience = retargeting only)
]


SYSTEM_PROMPT = """You identify the three buyer personas most likely to pay top of the range for a specific southern Gold Coast property.

# CONTEXT

The southern Gold Coast premium market (Robina, Burleigh Waters, Varsity Lakes, Mudgeeraba, Reedy Creek, Worongary, Merrimac, Burleigh Heads, Carrara) draws from these buyer cohorts:

  - LOCAL UPGRADERS: families currently in a 3-4 bed within ~5km, growing into more bedrooms / dual living / pool / school catchment.
  - CAPITAL CITY RETURNERS: ex-locals who left for Sydney/Melbourne work 5-15 years ago, moving home with a capital-city deposit. Cash-strong, time-poor, prefer turnkey.
  - SCHOOL-CATCHMENT FAMILIES: enrolment already confirmed at a specific local school (All Saints Anglican, Star of the Sea Catholic, Marymount, King's Christian). Walk-to-school is decisive.
  - DOWNSIZERS: empty-nesters from larger 5-6 bed homes elsewhere in the Gold Coast wanting a low-maintenance single-storey premium home.
  - LIFESTYLE MOVERS: pre-retirees from inland QLD / interstate seeking coastal lifestyle. Pool, low maintenance, beach proximity matter.
  - INVESTMENT BUYERS: less relevant for owner-occupier-priced premium homes; typically below $1.5M for the southern GC market.

# HOW FIELDS REACHES BUYERS — the `whereFound` and `campaignImplication` fields MUST use ONLY these

Every buyer search starts with the portals — realestate.com.au is the dominant one, and nearly all ACTIVE buyers (people already searching right now) use it. Fields lists there as standard, the same as any agent — that is table stakes, not a differentiator, and whereFound MUST say so explicitly rather than skip straight to what's different. But active buyers are only part of the market: a meaningful share of buyers are PASSIVE — they intend to move eventually but aren't searching yet (they're scrolling social media, watching video, not setting portal alerts). A portal listing alone never reaches that passive share. Fields' point of difference is reaching BEYOND the portal into that passive pool, using:
  - Conversion-optimised paid campaigns on Facebook and Instagram — BROAD prospecting (Fields' own performance data shows broad targeting outperforms narrow / "custom" audiences), plus retargeting people who have already engaged with Fields content or the listing. This is what reaches passive buyers who aren't actively searching.
  - YouTube video reach into the local market — another passive-buyer channel.
  - Google Ads on active search intent (e.g. "<suburb> family home", school-catchment queries) — captures active searchers beyond the portal itself.
  - DIRECT APPROACH (the strongest point of difference): Fields identifies the nearby homes whose owners typically move up into a home like this — by house type, ownership tenure and life-stage pattern — and contacts them directly, reaching buyers who are not searching anywhere yet, portal included. Describe this as METHOD, conditionally ("homes whose owners typically move into a home like this"). Do NOT state a count of homes or buyers — that model is not yet quantified.

STRUCTURE OF whereFound: open by naming realestate.com.au as the baseline every buyer search starts with (one clause is enough — "Fields lists on realestate.com.au as standard" or equivalent), then pivot explicitly to what Fields does BEYOND the portal to reach buyers who aren't actively searching it. Never omit the portal acknowledgment and jump straight to the differentiator channels — the seller should see Fields does what every agent does, then genuinely more, not read it as a replacement for the portal.

NEVER mention these — Fields does NOT have/do them: an email subscriber base, newsletter list, or "subscribers" (Fields has NONE — the only owned audience is Meta retargeting of site visitors / ad engagers, already covered above); school newsletters, school noticeboards, school-gate word-of-mouth, print mailers, flyers, newspaper or real-estate-section ads, LinkedIn outreach, "Will's network", premium-property mailing lists, "custom audiences" as a prospecting lever, or any open-home register or buyer-origin dataset. Domain may be named alongside realestate.com.au as a secondary portal, but never in place of it.

# YOUR TASK

Pick the THREE personas most defensible given the property's notable features, cohort premiums, and catchment. Adapt the canonical archetypes — don't just regurgitate them. For each persona produce a label, 1-2 sentence demographic brief, 3-5 specific reasons THIS home suits them (anchored to the property's actual features, not generic), and 2-3 sentences on where/how to reach them.

# OUTPUT FORMAT

Return ONLY a valid JSON array of exactly 3 objects. No markdown, no preamble:

[
  {
    "label": "string — 3-6 words, the persona's identifying title",
    "brief": "string — 1-2 sentences (20-50 words) demographic + life-stage",
    "whyThisHome": ["string", "string", "string"],
    "paysMoreFor": "string — 1 sentence (15-35 words): the SPECIFIC value lever this buyer pays a premium for in THIS home (not a generic 'space/location'). Conditional language only.",
    "hesitation": "string — 1 sentence (15-35 words): this buyer's most likely objection, and the fact/feature the campaign would answer it with. Honest, not dismissive.",
    "campaignImplication": "string — 1 sentence (20-45 words): the PRACTICAL campaign move this persona implies, in the form 'lead with X; reach via Y'. X = the value drivers to foreground; Y = one or more of Fields' REAL channels (HOW FIELDS REACHES BUYERS), never a forbidden channel.",
    "whereFound": "string — 2-3 sentences (40-80 words): how Fields would reach THIS cohort, using ONLY the channels in HOW FIELDS REACHES BUYERS, tied to the persona. Frame the direct-approach method conditionally, with no invented numbers."
  },
  ...
]

# ABSOLUTE RULES — violation triggers regeneration

1. EXACTLY 3 personas. Not 2, not 4.
2. EACH whyThisHome must have 3-5 items. Each item references a SPECIFIC feature from the input (bedroom count, land size, internal floor, pool presence, walking distances, beach proximity, suburb, build year, renovation level).
3. NO ADVICE TO THE SELLER. The personas describe buyers, not what the seller should do.
4. NO PREDICTIONS. No "this buyer will pay X". Use conditional language for buyer behaviour ("households in this band typically", "buyers with these constraints often").
5. NO FORBIDDEN WORDS in prose: stunning, nestled, boasting, rare opportunity, robust market, hot market, breathtaking, magnificent, must-see, dream home, executive.
6. PERSONAS MUST BE DISTINCT. No overlap. Each one reaches the home for a different reason — not three flavours of the same buyer.
7. label MUST identify a real demographic / life-stage, not a generic descriptor like "Premium buyers".
8. If the property's feature stack is COMMON in the cohort, say so honestly in at least one persona's reasoning — premium-buyer talk doesn't fit a 4-bed/2-bath home with no special features.
9. CHANNELS: whereFound and campaignImplication may reference ONLY the channels in HOW FIELDS REACHES BUYERS. Any forbidden channel — or any claimed buyer-origin dataset, register, or reach percentage — triggers regeneration. Never invent a count for the direct-approach method.
10. PORTAL FIRST: whereFound MUST explicitly name realestate.com.au (mentioning "the portal" alone is not enough) before pivoting to the passive-buyer / direct-approach channels. A whereFound that jumps straight to Facebook/YouTube/direct-approach without acknowledging the portal baseline is incomplete and triggers regeneration.

# VOICE

Plain, declarative. Match the V4 PDF tone. Address the seller's report indirectly — these are the buyers we'd target. No selling language."""


def _format_inputs(
    address: str,
    suburb: str,
    features_basic: Dict[str, Any],
    notable_features: List[Dict[str, str]],
    matching_full_stack: int,
    active_listings_total: int,
    cohort_premiums: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    valuation_range: Optional[Dict[str, Any]] = None,
    strategic_frame: Optional[str] = None,
) -> str:
    lines = [
        f"SUBJECT: {address} ({suburb})",
        "",
        "PROPERTY FACTS:",
    ]
    for k, label in [
        ("bedrooms", "Bedrooms"),
        ("bathrooms", "Bathrooms"),
        ("car_spaces", "Car spaces"),
        ("land_size_sqm", "Land (m²)"),
        ("floor_area_sqm", "Internal floor (m²)"),
        ("approximate_build_year", "Approximate build year"),
        ("number_of_stories", "Stories"),
        ("pool_present", "Pool"),
        ("water_views", "Water views"),
        ("beach_distance_km", "Beach distance (km)"),
        ("renovation_level_raw", "Renovation level"),
    ]:
        v = features_basic.get(k)
        if v is not None:
            lines.append(f"  - {label}: {v}")

    lines.append("")
    lines.append("NOTABLE FEATURES (the stack):")
    for f in notable_features or []:
        lines.append(f"  - {f['label']} ({f['value']})")
    if not notable_features:
        lines.append("  (none — feature stack is standard)")

    lines.append("")
    lines.append(
        f"COMBINATORIAL MATCH: {matching_full_stack} of {active_listings_total} "
        f"active listings in the southern Gold Coast catchment carry this full feature stack."
    )

    lines.append("")
    lines.extend(premium_prompt_lines(cohort_premiums))

    lines.append("")
    lines.append("WALKING DISTANCES:")
    for poi in pois or []:
        lines.append(f"  - {poi['name']} ({poi['category']}): {poi['walkMetres']} metres")
    if not pois:
        lines.append("  (none computed)")

    _dr = display_range(valuation_range)
    if _dr:
        lines.append("")
        lines.append(
            f"WORKING VALUATION RANGE: ${_dr[0]:,} – ${_dr[1]:,} "
            f"(rounded to the nearest $100k for display)"
        )

    if strategic_frame:
        lines.append("")
        lines.append(f"STRATEGIC FRAME ALREADY CHOSEN FOR THIS PROPERTY: {strategic_frame}")
        lines.append(
            "  Your FIRST persona must clearly fit this frame — do not contradict it. "
            "(e.g. if the frame leads with proximity to a specific school, persona 1 must be a "
            "family/school-driven buyer, not an empty-nester/downsizer whose defining need — dropping "
            "stairs and maintenance — has nothing to do with a school walk.) Personas 2 and 3 may cover "
            "different angles on the SAME property, but none may undermine or contradict the chosen frame."
        )

    return "\n".join(lines)


def _validate_output(parsed: Any) -> Optional[str]:
    if not isinstance(parsed, list):
        return "not a list"
    if len(parsed) != 3:
        return f"expected exactly 3 personas, got {len(parsed)}"

    labels_seen = set()
    for i, p in enumerate(parsed):
        if not isinstance(p, dict):
            return f"persona {i} not a dict"
        for key in ("label", "brief", "whyThisHome", "paysMoreFor", "hesitation", "campaignImplication", "whereFound"):
            if key not in p:
                return f"persona {i} missing key: {key}"

        label = (p.get("label") or "").strip()
        if not label or len(label) < 4 or len(label) > 60:
            return f"persona {i} label length out of range"
        if label.lower() in labels_seen:
            return f"duplicate persona label: {label}"
        labels_seen.add(label.lower())

        brief = (p.get("brief") or "").strip()
        if len(brief) < 30 or len(brief) > 300:
            return f"persona {i} brief length {len(brief)} out of 30-300"

        why = p.get("whyThisHome")
        if not isinstance(why, list) or not (3 <= len(why) <= 6):
            return f"persona {i} whyThisHome should be 3-6 items, got {len(why) if isinstance(why, list) else 'n/a'}"
        for j, item in enumerate(why):
            if not isinstance(item, str) or len(item.strip()) < 15:
                return f"persona {i} whyThisHome[{j}] too short"

        where = (p.get("whereFound") or "").strip()
        if len(where) < 40 or len(where) > 600:
            return f"persona {i} whereFound length {len(where)} out of 40-600"
        # Rule 10 (2026-07-23, Will's feedback): whereFound must acknowledge
        # the realestate.com.au baseline before pivoting to the passive-buyer/
        # direct-approach channels — a prior prompt version treated the
        # portal as unstated "table stakes" and the model never mentioned it,
        # reading as if Fields skipped the portal entirely rather than doing
        # that AND more.
        if "realestate.com.au" not in where.lower():
            return f"persona {i} whereFound missing realestate.com.au portal acknowledgment"

    # Editorial guardrails across all prose
    prose = " ".join(
        " ".join([
            p["label"], p["brief"], " ".join(p["whyThisHome"]),
            p.get("paysMoreFor") or "", p.get("hesitation") or "",
            p.get("campaignImplication") or "", p["whereFound"],
        ])
        for p in parsed
    ).lower()

    forbidden = [
        "stunning", "nestled", "boasting", "rare opportunity", "robust market",
        "hot market", "breathtaking", "magnificent", "must-see", "dream home",
    ]
    hit = [w for w in forbidden if w in prose]
    if hit:
        return f"forbidden word(s) in prose: {hit}"

    advice = ["you should", "we recommend", "now is a good time", "now is the time"]
    advice_hit = [p for p in advice if p in prose]
    if advice_hit:
        return f"advice pattern(s): {advice_hit}"

    # Channels Fields does NOT operate — fabricating them is the bug this guard exists for.
    # NB: "direct approach" / "letterbox" / "direct mail" are allowed (our real method);
    # only the borrowed-tactic terms below are banned.
    ch_hit = [w for w in FORBIDDEN_CHANNELS if w in prose]
    if ch_hit:
        return f"forbidden channel(s) in prose: {ch_hit}"

    return None


def resolve_personas_narrative(
    address: str,
    suburb: str,
    features_basic: Dict[str, Any],
    notable_features: List[Dict[str, str]],
    matching_full_stack: int,
    active_listings_total: int,
    cohort_premiums: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    valuation_range: Optional[Dict[str, Any]] = None,
    strategic_frame: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """strategic_frame (optional): a short description of the positioning
    frame ALREADY chosen for this property (e.g. positioning_object.py's
    frameLine + leadLine) — when supplied, persona 1 is required to align
    with it rather than being picked independently, so a downstream reader
    never sees two cards arguing for contradictory buyer profiles (found
    2026-07-23: a 'downsizer' persona alongside a 'walk to school' frame on
    the same property, in Will's words 'the cards' intent is incongruent')."""
    from scripts.property_reports._claude_backend import get_client_and_model
    client, model = get_client_and_model(MODEL)
    if not client:
        logger.warning("No Claude backend available — skipping personas")
        return None
    user_prompt = _format_inputs(
        address, suburb, features_basic or {}, notable_features or [],
        matching_full_stack or 0, active_listings_total or 0,
        cohort_premiums or [], pois or [], valuation_range, strategic_frame,
    )

    last_error: Optional[str] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as e:
            last_error = f"API error attempt {attempt}: {e}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        try:
            raw = "".join(
                getattr(b, "text", "") for b in response.content
                if getattr(b, "type", None) == "text"
            ).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                if raw.startswith("json\n"):
                    raw = raw[5:].strip()
            parsed = json.loads(raw)
        except (json.JSONDecodeError, KeyError, AttributeError, IndexError) as e:
            last_error = f"parse error attempt {attempt}: {e}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        validation_err = _validate_output(parsed)
        if validation_err:
            last_error = f"validation failed attempt {attempt}: {validation_err}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        return {
            "personas": parsed,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "attempt": attempt,
        }

    logger.error(f"personas: all {MAX_RETRIES} attempts failed — last_error={last_error}")
    return {"error": last_error, "attempts": MAX_RETRIES}

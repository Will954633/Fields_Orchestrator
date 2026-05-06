"""
Editorial review gate for Fields Appraisal Report editorial JSON.

Implements the checklist from 09_Appraisals/04_content_modules.md §G.
Validates the AI-generated editorial JSON against the rules that were established
to prevent the May 6 content regression and similar future drift.

Designed to be:
  - Importable from generate_appraisal_report.py (validate_editorial(dict) -> Result)
  - Runnable standalone against a saved editorial JSON file
  - Used in CI / pre-render gates without external dependencies (stdlib only)

Run modes:
    python3 scripts/editorial_review.py editorial.json
    python3 scripts/editorial_review.py editorial.json --strict   # exit 1 on any FAIL
    python3 scripts/editorial_review.py editorial.json --json     # machine-readable

Author: Fields Estate · 2026-05-06.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

FORBIDDEN_WORDS = [
    # Per CLAUDE.md "Editorial Content Rules" + 04_content_modules.md §G
    "stunning",
    "nestled",
    "boasting",
    "rare opportunity",
    "robust market",
    # Common real-estate fluency we want to avoid (extending the official list)
    "must-see",
    "dream home",
    "won't last",
    "act fast",
    "don't miss",
    # NB. "perfect for" was previously blocked as a real-estate cliché but it slipped through
    # repeatedly in legitimate balanced-judgement contexts ("perfect for some, excessive for
    # others"). Keep the stronger clichés below; allow "perfect for" so Will's manual review
    # filters cliché vs legitimate use.
    "exquisite",
    "tranquil oasis",
]

ADVICE_PATTERNS = [
    # "You should" framing — forbidden by feedback_no_advice_data_only.md.
    # Restricted to seller-directed framing only; "buyers move quickly" is fine to describe.
    # NB. Do NOT add bare patterns like \bact now\b or \bmove quickly\b — they false-positive
    # when the prose describes buyer behaviour, not seller advice.
    r"\byou should\b",
    r"\byou must\b",
    r"\byou need to\b",
    r"\byou ought to\b",
    r"\byou'd better\b",
    r"\byou had better\b",
    # Seller-directed urgency (specifically prefixed with "you" or imperative-at-sentence-start)
    r"(?:^|[.!?]\s+)(?:Act now|List immediately|Move quickly|Sell now)\b",
    r"\byou (?:must|need to|should) (?:act|list|sell|move) (?:now|quickly|immediately|today)\b",
]

PREDICTION_PATTERNS = [
    # Forecast language — forbidden by feedback_editorial_voice.md
    r"\bprices will (rise|fall|climb|drop)\b",
    r"\bthe market will\b",
    r"\bguaranteed (sale|return|price)\b",
    r"\bwill achieve\b",
    r"\bwill exceed\b",
    r"\bguaranteed to\b",
]

# Round-number formats forbidden in BODY copy (not in headline framing).
# Allowed contexts (NOT flagged): "$3 million" (full word), "$3m+" (price-tier),
# "$3m threshold/market/tier/bracket/segment/range/band/category/level/territory/space/sector/class"
# (semantic price-tier references — these aren't precise valuations, they're conceptual segments).
ROUND_DOLLAR_PATTERN = re.compile(
    r"\$\d+(?:\.\d+)?\s*[mM]"
    r"(?!illion|\+|\s+(?:threshold|market|tier|bracket|segment|range|band|"
    r"category|level|territory|space|sector|class|club|cohort|stock))"
)

# Precise dollar pattern — what we WANT to see
PRECISE_DOLLAR_PATTERN = re.compile(r"\$[\d,]{6,}(?!\d)")  # $1,250,000 etc.

# A simple address heuristic (Number + StreetName + StreetType)
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,4}[A-Za-z]?\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+"
    r"(?:Court|Drive|Street|Road|Avenue|Place|Lane|Crescent|Boulevard|Way|Close|Parade|Terrace|Highway|Walk|Esplanade|CT|DR|ST|RD|AVE|PL|LN|CR|BLVD|WAY|CL|PDE|TER|HWY|WLK|ESP)\b",
    re.IGNORECASE,
)

REQUIRED_KEYS = [
    "headline",
    "sub_headline",
    "verdict",
    "strengths",
    "trade_off",
    "value_equations",
    "buyer_profiles",
    "scarcity_count",
    "scarcity_statement",
    "lifestyle_narrative",
    "pricing_cards",
    "feature_positioning",
    "campaign_structure",
    "photography_strategy",
    "open_home_strategy",
]

# Expected counts per 04_content_modules.md
EXPECTED_COUNTS = {
    "strengths": (3, 4),               # 3-4
    "value_equations": (5, 5),         # exactly 5 (was 5-7 — tightened to fit page layout)
    "buyer_profiles": (3, 3),          # exactly 3
    "pricing_cards": (4, 4),           # exactly 4
    "feature_positioning": (5, 6),     # 5-6
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "fail"   # "fail" blocks render; "warn" surfaces but doesn't block


@dataclass
class ReviewResult:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def fails(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "fail"]

    @property
    def warns(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "warn"]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "fail_count": len(self.fails),
            "warn_count": len(self.warns),
            "checks": [
                {"name": c.name, "passed": c.passed, "severity": c.severity, "detail": c.detail}
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gather_prose(editorial: dict) -> str:
    """Concatenate every text field that should be reviewed for prose-level rules."""
    parts = []
    for key in ["headline", "sub_headline", "verdict", "trade_off",
                "lifestyle_narrative", "campaign_structure",
                "photography_strategy", "open_home_strategy",
                "scarcity_statement"]:
        v = editorial.get(key)
        if isinstance(v, str):
            parts.append(v)
    for s in editorial.get("strengths", []) or []:
        if isinstance(s, str):
            parts.append(s)
    for ve in editorial.get("value_equations", []) or []:
        if isinstance(ve, dict):
            parts.extend([str(ve.get("title", "")), str(ve.get("body", "")), str(ve.get("reframe", ""))])
    for bp in editorial.get("buyer_profiles", []) or []:
        if isinstance(bp, dict):
            parts.extend([str(bp.get("name", "")), str(bp.get("description", ""))])
    for pc in editorial.get("pricing_cards", []) or []:
        if isinstance(pc, dict):
            parts.extend([str(pc.get("label", "")), str(pc.get("range", "")), str(pc.get("rationale", ""))])
    for fp in editorial.get("feature_positioning", []) or []:
        if isinstance(fp, dict):
            parts.extend([str(fp.get("feature", "")), str(fp.get("impact", "")), str(fp.get("strategy", ""))])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_required_keys(editorial: dict) -> CheckResult:
    missing = [k for k in REQUIRED_KEYS if k not in editorial or editorial.get(k) in (None, "")]
    if missing:
        return CheckResult("required_keys", False,
                           f"Missing or empty: {', '.join(missing)}")
    return CheckResult("required_keys", True)


def check_counts(editorial: dict) -> CheckResult:
    issues = []
    for key, (lo, hi) in EXPECTED_COUNTS.items():
        items = editorial.get(key) or []
        n = len(items)
        if n < lo or n > hi:
            issues.append(f"{key}: got {n}, expected {lo}-{hi}")
    if issues:
        return CheckResult("expected_counts", False, "; ".join(issues))
    return CheckResult("expected_counts", True)


def check_forbidden_words(editorial: dict) -> CheckResult:
    prose = _gather_prose(editorial).lower()
    found = [w for w in FORBIDDEN_WORDS if w in prose]
    if found:
        return CheckResult("forbidden_words", False,
                           f"Found: {', '.join(found)}")
    return CheckResult("forbidden_words", True)


def check_no_advice(editorial: dict) -> CheckResult:
    prose = _gather_prose(editorial)
    matches = []
    for pat in ADVICE_PATTERNS:
        if re.search(pat, prose, re.IGNORECASE):
            matches.append(pat)
    if matches:
        return CheckResult("no_advice", False,
                           f"Advice patterns matched: {', '.join(matches)}")
    return CheckResult("no_advice", True)


def check_no_predictions(editorial: dict) -> CheckResult:
    prose = _gather_prose(editorial)
    matches = []
    for pat in PREDICTION_PATTERNS:
        if re.search(pat, prose, re.IGNORECASE):
            matches.append(pat)
    if matches:
        return CheckResult("no_predictions", False,
                           f"Prediction patterns matched: {', '.join(matches)}")
    return CheckResult("no_predictions", True)


def check_round_dollars(editorial: dict) -> CheckResult:
    """Body copy must use precise dollar figures, not $1.5M / $2m."""
    prose = _gather_prose(editorial)
    matches = ROUND_DOLLAR_PATTERN.findall(prose)
    if matches:
        return CheckResult("precise_dollars", False,
                           f"Round figures found: {', '.join(set(matches))}",
                           severity="warn")  # warn — pricing_cards.range often uses ranges that we accept
    return CheckResult("precise_dollars", True)


def check_verdict_quality(editorial: dict) -> CheckResult:
    """Verdict must contain ≥ 2 comp addresses and at least 1 precise dollar figure."""
    verdict = editorial.get("verdict", "") or ""
    addresses = ADDRESS_PATTERN.findall(verdict)
    dollars = PRECISE_DOLLAR_PATTERN.findall(verdict)
    issues = []
    if len(addresses) < 2:
        issues.append(f"only {len(addresses)} comp address(es) cited (≥2 required)")
    if len(dollars) < 1:
        issues.append("no precise dollar figure in verdict")
    if not verdict.lower().startswith(("based on", "drawn from", "supported by")):
        issues.append("verdict should open with 'Based on N adjusted comparable sales…'")
    if issues:
        return CheckResult("verdict_quality", False, "; ".join(issues))
    return CheckResult("verdict_quality", True)


def check_headline_anchor(editorial: dict) -> CheckResult:
    """Headline must contain a specific numerical anchor (digit OR word-form number)."""
    headline = editorial.get("headline", "") or ""
    word_numbers = r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen)\b"
    has_number = bool(re.search(r"\d", headline) or re.search(word_numbers, headline, re.IGNORECASE))
    if not has_number:
        return CheckResult("headline_anchor", False,
                           "headline contains no numerical anchor (digit or word-form)")
    return CheckResult("headline_anchor", True)


def check_strengths_quality(editorial: dict) -> CheckResult:
    """Strengths must each contain a precise dollar figure or specific measurement."""
    strengths = editorial.get("strengths", []) or []
    weak = []
    placeholder_re = re.compile(
        r"^\s*(?:Land area|Internal floor area|Bedrooms|Bathrooms|Car spaces|"
        r"Time adjustment to today|Pool|Condition|Renovation level|Storeys|"
        r"Air conditioning|Wetland reserve|Water views|Golf course frontage)\s*:\s*"
        r"[+\-−]?\$[\d,]+\s*adjustment\s+vs\s+",
        re.IGNORECASE,
    )
    for s in strengths:
        if not isinstance(s, str):
            weak.append(f"non-string strength: {type(s).__name__}")
            continue
        if placeholder_re.match(s):
            # This is the May 6 fallback skeleton signature.
            weak.append(f"strength looks like _minimal_editorial fallback: {s[:60]}…")
            continue
        has_dollar = bool(re.search(r"\$[\d,]+", s))
        has_measurement = bool(re.search(r"\d+\s*(m²|sqm|m2|/10|metres|m\b|km\b|kilometres|ha\b)", s, re.IGNORECASE))
        # Count-with-unit (e.g. "5 sold in 12 months", "1 had a pool", "3 bedrooms")
        has_count = bool(re.search(
            r"\b\d+\s*(sold|listed|sales|months?|years?|days?|weeks?|"
            r"bedrooms?|bathrooms?|cars?|properties|homes?|metres?|points?|"
            r"premium|segment|catchment|inspections?|enquiries|enquiry)\b",
            s, re.IGNORECASE,
        ))
        # Percentage anchor (e.g. "15% buyer premium", "32% faster sales")
        has_pct = bool(re.search(r"\d+(?:\.\d+)?\s*%", s))
        if not (has_dollar or has_measurement or has_count or has_pct):
            weak.append(f"strength lacks dollar/measurement/count/%: {s[:60]}…")
    if weak:
        return CheckResult("strengths_quality", False, "; ".join(weak))
    return CheckResult("strengths_quality", True)


def check_trade_off_specificity(editorial: dict) -> CheckResult:
    """Trade-off must contain measurements or a comp comparison, not be a placeholder."""
    trade_off = (editorial.get("trade_off") or "").strip()
    if not trade_off:
        return CheckResult("trade_off_specificity", False, "trade_off is empty")
    placeholder_signatures = [
        "refer to the detailed comparable adjustment",
        "see the comparable adjustment",
        "see the detailed analysis",
    ]
    if any(sig in trade_off.lower() for sig in placeholder_signatures):
        return CheckResult("trade_off_specificity", False,
                           "trade_off is a fallback placeholder")
    has_measurement = bool(re.search(r"\d+\s*(m²|sqm|m2|/10|metres|m\b|sqm)", trade_off, re.IGNORECASE))
    has_dollar = bool(re.search(r"\$[\d,]+", trade_off))
    has_comp_signal = bool(ADDRESS_PATTERN.search(trade_off)) or "comparable" in trade_off.lower()
    if not (has_measurement or has_dollar or has_comp_signal):
        return CheckResult("trade_off_specificity", False,
                           "trade_off lacks specific measurement/dollar/comp reference")
    return CheckResult("trade_off_specificity", True)


def check_inoculation(editorial: dict) -> CheckResult:
    """At least 2 value_equations should be inoculation panels — name a weakness then reframe."""
    ves = editorial.get("value_equations", []) or []
    inoculation_count = 0
    for ve in ves:
        if not isinstance(ve, dict):
            continue
        if ve.get("positive") is False:
            inoculation_count += 1
            continue
        body = (ve.get("body") or "").lower()
        # Inoculation signal: contains a "but/though/however/while" pivot AND at least one comp address
        if re.search(r"\b(but|though|however|while|despite|even though)\b", body):
            inoculation_count += 1
    if inoculation_count < 2:
        return CheckResult("inoculation_panels", False,
                           f"only {inoculation_count} inoculation panel(s); ≥2 required",
                           severity="warn")
    return CheckResult("inoculation_panels", True)


def check_value_equation_quality(editorial: dict) -> CheckResult:
    """Each value equation needs body + reframe; body should cite a comp address or dollar figure."""
    ves = editorial.get("value_equations", []) or []
    weak = []
    for i, ve in enumerate(ves):
        if not isinstance(ve, dict):
            weak.append(f"#{i+1} not a dict")
            continue
        title = ve.get("title", "")
        body = ve.get("body", "")
        reframe = ve.get("reframe", "")
        if not body or len(body) < 80:
            weak.append(f"#{i+1} '{title[:30]}': body too short")
            continue
        if not reframe or len(reframe) < 15:
            weak.append(f"#{i+1} '{title[:30]}': reframe missing/too short")
            continue
        has_specific = bool(
            re.search(r"\$[\d,]+", body)                                # dollar
            or ADDRESS_PATTERN.search(body)                              # comp address
            or re.search(r"\d+\s*(m²|sqm|m2|/10)", body, re.IGNORECASE)  # measurement
            or re.search(r"\d+(?:\.\d+)?\s*%", body)                     # percentage
            or re.search(r"\d+\s+of\s+\d+", body, re.IGNORECASE)         # count-of-N ("2 of 117")
            or re.search(r"\d+[-–]\d+\s*(?:months?|years?|weeks?|days?)\b", body, re.IGNORECASE)  # time period
        )
        if not has_specific:
            weak.append(f"#{i+1} '{title[:30]}': body lacks specific anchor")
    if weak:
        return CheckResult("value_equation_quality", False, "; ".join(weak[:5]))
    return CheckResult("value_equation_quality", True)


def check_buyer_profile_specificity(editorial: dict) -> CheckResult:
    """Each buyer profile description should reference a specific feature or POI."""
    bps = editorial.get("buyer_profiles", []) or []
    weak = []
    for i, bp in enumerate(bps):
        desc = (bp.get("description") if isinstance(bp, dict) else "") or ""
        if len(desc) < 50:
            weak.append(f"profile #{i+1} description too short")
    if weak:
        return CheckResult("buyer_profile_quality", False, "; ".join(weak), severity="warn")
    return CheckResult("buyer_profile_quality", True)


def check_limits_of_evidence(editorial: dict) -> CheckResult:
    """M6 — Limits of Our Evidence. Optional in older cached editorials (warn if missing)."""
    loe = editorial.get("limits_of_evidence")
    if not loe:
        return CheckResult("limits_of_evidence", False,
                           "missing — Phase 1 module M6 not generated (older editorial?)",
                           severity="warn")
    if not isinstance(loe, dict):
        return CheckResult("limits_of_evidence", False, "not a dict")
    items = loe.get("items") or []
    if len(items) != 4:
        return CheckResult("limits_of_evidence", False,
                           f"got {len(items)} items, expected exactly 4")
    intro = (loe.get("intro") or "").strip()
    closing = (loe.get("closing") or "").strip()
    if len(intro) < 25:
        return CheckResult("limits_of_evidence", False, "intro missing or too short (< 25 chars)")
    if len(closing) < 25:
        return CheckResult("limits_of_evidence", False, "closing missing or too short (< 25 chars)")
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            return CheckResult("limits_of_evidence", False, f"item {i+1} not a dict")
        title = (item.get("title") or "").strip()
        body = (item.get("body") or "").strip()
        if not title or len(body) < 60:
            return CheckResult("limits_of_evidence", False,
                               f"item {i+1} missing title or body too short (< 60 chars)")
    return CheckResult("limits_of_evidence", True)


def check_morning_narrative(editorial: dict) -> CheckResult:
    """M11 — narrative transportation page. Optional in older cached editorials (warn if missing).

    Strict rules when present: 200-250 words, no second-person 'you' addressing the seller,
    references at least one named time of day, ends on a sensory image not a conclusion.
    """
    text = (editorial.get("morning_in_this_home") or "").strip()
    if not text:
        return CheckResult("morning_narrative", False,
                           "missing — Phase 1 module M11 not generated (older editorial?)",
                           severity="warn")
    word_count = len(text.split())
    # Tolerate slightly outside the 200-250 target — but flag obvious off-target generations.
    if word_count < 170 or word_count > 290:
        return CheckResult("morning_narrative", False,
                           f"word count {word_count}, expected 200-250 (tolerated 170-290)")
    # No "you" addressing — narrator IS the buyer.
    # NB. Permitted if it's clearly part of an inner thought ("could you imagine living here") but the
    # rule is strict for safety; if a legitimate phrasing trips this, edit prompt to forbid the construction.
    if re.search(r"\b(you|your|you're|you've|you'll|you'd)\b", text, re.IGNORECASE):
        return CheckResult("morning_narrative", False,
                           "contains 'you'/'your' — narrator must be a buyer, not address the seller")
    # Must reference a named time of day or temporal moment.
    times = [
        "morning", "afternoon", "evening", "dusk", "dawn", "sunrise", "sunset",
        "twilight", "midday", "midnight", "midmorning", "midafternoon",
        "first light", "early", "late afternoon", "late evening",
        "saturday", "sunday", "weekend",
    ]
    if not any(re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE) for t in times):
        return CheckResult("morning_narrative", False, "no named time of day or temporal moment")
    # Should not end with a hard pitch / conclusion. Heuristic: last sentence shouldn't contain
    # advice/CTA verbs.
    last_sentence = re.split(r"(?<=[.!?])\s+", text)[-1].strip()
    pitch_words = ["consider", "discover", "experience this", "this is the", "don't miss",
                   "act now", "the perfect"]
    if any(p in last_sentence.lower() for p in pitch_words):
        return CheckResult("morning_narrative", False,
                           f"ending reads as pitch/conclusion, not sensory image: '{last_sentence[:60]}…'",
                           severity="warn")
    return CheckResult("morning_narrative", True)


def check_seller_possession_hallucination(editorial: dict) -> CheckResult:
    """M11 hallucination guard: detect phrases that imply the seller owns objects we have no data for.

    Pattern: possessive determiners ('the X', 'their X', 'the family X') paired with belongings
    we cannot verify (boat, kayak, Mustang, dog, etc.). Generic descriptions of activity AROUND
    the home (a boat puttering past, a kayaker gliding upstream) are fine — they don't claim
    seller ownership.

    Severity: WARN (surfaces for human review without blocking; some patterns may be legitimate
    in context, e.g. 'the boat ramp at Currumbin Creek').
    """
    morning = (editorial.get("morning_in_this_home") or "").strip()
    if not morning:
        return CheckResult("seller_possession_hallucination", True, severity="warn")

    suspicious = []

    # Pattern 1: "the X" / "the family X" where X is a vehicle/pet/hobby gear that implies ownership.
    # We require the determiner "the" + space + the noun, NOT followed by neutral landmarks
    # (ramp, dock, club, shed, storage, repair, hire).
    nouns_strong = r"(?:Mustang|Tesla|BMW|Audi|Mercedes|Porsche|Lamborghini|Ferrari|Range Rover|Jet ?Ski|jet-ski|surfboards?)"
    nouns_medium = r"(?:boat|kayak|motorcycle|motorbike|caravan|trailer|jetski|jet ski)"
    pat_strong = re.compile(rf"\b(?:the|the family|their|her|his)\s+{nouns_strong}\b", re.IGNORECASE)
    pat_medium = re.compile(
        rf"\b(?:the|the family|their|her|his)\s+{nouns_medium}\b"
        r"(?!\s+(?:ramp|dock|club|shed|storage|hire|repair|trip|ride|sail|tour))",
        re.IGNORECASE,
    )
    for pat in (pat_strong, pat_medium):
        for m in pat.finditer(morning):
            suspicious.append(m.group(0))

    # Pattern 2: "their dog/cat" or "the family dog/cat" — pets the seller may not have.
    pat_pet = re.compile(r"\b(?:their|her|his|the family)\s+(?:dog|cat|pet|puppy|kitten)\b", re.IGNORECASE)
    for m in pat_pet.finditer(morning):
        suspicious.append(m.group(0))

    if suspicious:
        unique = list(dict.fromkeys(suspicious))  # dedupe preserve order
        return CheckResult(
            "seller_possession_hallucination", False,
            f"Possible invented seller belongings: {unique}",
            severity="warn",  # warn — needs human review, may be legitimate
        )
    return CheckResult("seller_possession_hallucination", True)


def check_pricing_cards(editorial: dict) -> CheckResult:
    """4 pricing cards expected; each must have a range and rationale."""
    cards = editorial.get("pricing_cards", []) or []
    issues = []
    for i, c in enumerate(cards):
        if not isinstance(c, dict):
            issues.append(f"card #{i+1} not a dict")
            continue
        if not c.get("range") or not re.search(r"\$[\d,]+", str(c.get("range", ""))):
            issues.append(f"card #{i+1} missing/invalid range")
        if len((c.get("rationale") or "")) < 40:
            issues.append(f"card #{i+1} rationale too short")
    if issues:
        return CheckResult("pricing_cards_quality", False, "; ".join(issues))
    return CheckResult("pricing_cards_quality", True)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_required_keys,
    check_counts,
    check_forbidden_words,
    check_no_advice,
    check_no_predictions,
    check_round_dollars,
    check_verdict_quality,
    check_headline_anchor,
    check_strengths_quality,
    check_trade_off_specificity,
    check_inoculation,
    check_value_equation_quality,
    check_buyer_profile_specificity,
    check_pricing_cards,
    # Phase 1 modules — warn-severity when field absent (backwards-compat with older cached editorials)
    check_limits_of_evidence,
    check_morning_narrative,
    # Hallucination guard for M11 (warn — may need human judgement on edge cases)
    check_seller_possession_hallucination,
]


def validate_editorial(editorial: dict) -> ReviewResult:
    """Run all checks; return ReviewResult. `passed` = no FAIL-severity check failed."""
    results = []
    for check in ALL_CHECKS:
        try:
            results.append(check(editorial))
        except Exception as e:
            results.append(CheckResult(check.__name__, False, f"check raised: {e}"))
    overall = all(c.passed or c.severity == "warn" for c in results)
    return ReviewResult(passed=overall, checks=results)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_human(result: ReviewResult) -> None:
    print(f"Editorial review: {'PASS' if result.passed else 'FAIL'}")
    print(f"  Checks: {len(result.checks)} run · "
          f"{len([c for c in result.checks if c.passed])} passed · "
          f"{len(result.fails)} fail · {len(result.warns)} warn")
    print()
    for c in result.checks:
        if c.passed:
            mark = "✓"
        elif c.severity == "warn":
            mark = "!"
        else:
            mark = "✗"
        line = f"  {mark} {c.name}"
        if c.detail:
            line += f"  —  {c.detail}"
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Fields Appraisal editorial JSON file.")
    parser.add_argument("editorial_path", help="Path to editorial JSON (or '-' for stdin)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any FAIL-severity check (warnings still pass)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    if args.editorial_path == "-":
        editorial = json.load(sys.stdin)
    else:
        editorial = json.loads(Path(args.editorial_path).read_text())

    result = validate_editorial(editorial)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_human(result)

    if args.strict and not result.passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
claim_gate.py — Marketing-claim fact-check gate.

Every public-facing marketing claim about a property (headline, ad, carousel
card, mailer line, chart caption) must pass this gate BEFORE publish. It turns
the discipline we have been applying by hand — the "one of the best combination"
claim that FAILED adversarial testing, the "Res B" zoning claim that had no
source document — into a repeatable, un-skippable checklist plus partial
automation.

It is deliberately conservative: it flags for a human, it does not "approve"
marketing. A PASS means "no automated tripwire fired", not "true".

Verdicts
--------
  PASS             no tripwire fired — still a human's call, but nothing flagged
  NEEDS-QUALIFIER  claim is publishable only with a stated qualifier / a verify
                   query run first (superlatives, bounded market claims, $-claims)
  FAIL             hard Rule 5 breach (advice, prediction, forbidden word,
                   single-valuation-in-headline) OR a planning/zoning claim that
                   contradicts the property's planning verdict / cites no source

Exit code is non-zero if ANY claim is FAIL, so this can gate a publish script:

    python3 scripts/claim_gate.py --slug 12-example-st-burleigh-waters \
        --file draft_claims.txt || { echo "blocked"; exit 1; }

Rules enforced come from /home/fields/CLAUDE.md Rule 5 (editorial rules) and the
valuation claim-limit memory notes. Read-only on the DB.
"""

import argparse
import json
import re
import sys

# ---------------------------------------------------------------------------
# Rule 5 lexical tables
# ---------------------------------------------------------------------------

# Forbidden words — hard FAIL (CLAUDE.md Rule 5 "Forbidden words").
FORBIDDEN_WORDS = [
    "stunning",
    "nestled",
    "boasting",
    "boast",
    "rare opportunity",
    "robust market",
]

# Advice phrasing — telling the reader what to do. Hard FAIL ("No advice").
ADVICE_PATTERNS = [
    r"\byou should\b",
    r"\byou must\b",
    r"\bnow is (?:a good |the )?time to (?:buy|sell|act|invest)\b",
    r"\bnow is the time\b",
    r"\bmust sell\b",
    r"\bpriced to sell\b",
    r"\bdon'?t miss\b",
    r"\bact now\b",
    r"\bconsider (?:buying|selling)\b",
    r"\bwe recommend\b",
    r"\byou need to\b",
]

# Prediction phrasing — forecasting price direction. Hard FAIL ("No predictions").
PREDICTION_PATTERNS = [
    r"\bwill rise\b",
    r"\bwill fall\b",
    r"\bwill (?:increase|decrease|drop|climb|surge|crash|boom)\b",
    r"\bprices will\b",
    r"\bvalues will\b",
    r"\bis going to (?:rise|fall|increase|drop)\b",
    r"\bset to (?:rise|fall|soar|jump)\b",
    r"\bexpect(?:ed)? to (?:rise|fall|grow|increase|drop)\b",
]

# Superlatives — need data backing; unqualified market superlatives are unverifiable.
SUPERLATIVE_PATTERNS = [
    r"\bbest\b",
    r"\bonly\b",
    r"\bcheapest\b",
    r"\bmost affordable\b",
    r"\blargest\b",
    r"\bbiggest\b",
    r"\bsmallest\b",
    r"\bhighest\b",
    r"\blowest\b",
    r"\bmost\b",
    r"\bunbeatable\b",
    r"\bnumber one\b",
    r"\bno other\b",
    r"\bnowhere else\b",
    # Universal quantifiers over the market — same un-censusable problem as a
    # superlative. Scoped to a property noun so a bare "no"/"all" doesn't trip.
    r"\bno\s+(?:\w+\s+){0,3}(?:house|home|property|listing|block)s?\b",
    r"\bnot?\s+(?:a\s+)?single\s+(?:\w+\s+){0,3}(?:house|home|property|listing|block)\b",
    r"\bevery\s+(?:\w+\s+){0,3}(?:house|home|property|listing|block)\b",
    r"\ball\s+(?:\w+\s+){0,3}(?:houses|homes|properties|listings|blocks)\b",
    r"\bnone\s+of\b",
    r"\bnever\s+(?:been\s+)?(?:offered|sold|listed|available)\b",
]

# Planning / zoning / development claims — need a cited source document.
PLANNING_PATTERNS = [
    r"\bres\s?b\b",
    r"\bres\s?a\b",
    r"\brd\d\b",
    r"\bduplex\b",
    r"\bdevelopment (?:site|block|potential|opportunity)\b",
    r"\bsubdivi",           # subdivide / subdivision / subdividable
    r"\bapproved\b",
    r"\bda approv",
    r"\bdevelopment approval\b",
    r"\bzoned\b",
    r"\bzoning\b",
    r"\bmedium density\b",
    r"\bhigh density\b",
    r"\bdual occupancy\b",
    r"\bgranny flat approved\b",
    r"\brezon",
]

# Valuation-accuracy guardrails — documented limits, must never be stated.
VALUATION_CLAIM_PATTERNS = [
    (r"\b90\s?%?\s?confidence\b", "'90% confidence' — our ±band contained the actual price only 61-77%; a true 90% band needs ~3x the width. Banned."),
    (r"\bnine times out of ten\b", "'nine times out of ten' — same miscalibration as the 90% claim. Banned."),
    (r"\bconfidence (?:range|interval)\b", "'confidence range/interval' — our range is a flat per-suburb band, NOT a statistical CI. Do not call it one."),
    (r"\b\d+\s?%\s+fall outside\b", "'X% fall outside' — implies a calibrated CI we do not have. Banned."),
    (r"\b10\s?%\s+fall outside\b", "'~10% fall outside' — the band is not a 90% CI. Banned."),
    (r"\bmore accurate than\b", "'more accurate than [Domain/competitor]' — falsifiable from our own published table in Robina & Burleigh Waters. Banned. Sayable: 'we publish our error rate'."),
    (r"\bmost accurate\b", "'most accurate' valuation — unsubstantiated competitor comparison. Banned."),
]

# Known suburbs that must be capitalised (CLAUDE.md Rule 5 "suburbs always capitalised").
KNOWN_SUBURBS = [
    "robina", "varsity lakes", "burleigh waters", "burleigh heads",
    "burleigh", "surfers paradise", "mermaid waters", "mermaid beach",
    "miami", "palm beach", "reedy creek", "mudgeeraba", "worongary",
    "carrara", "merrimac", "clear island waters", "broadbeach",
    "gold coast", "currumbin", "elanora", "tallebudgera",
]

# Words that make a fragment look like a headline (used to decide whether a bare
# "$X" is being presented as the home's worth).
HEADLINE_HINT = re.compile(
    r"\b(worth|valued? at|value|priced?|asking|for sale at|now|just|only|from)\b",
    re.I,
)

# A single dollar figure, e.g. $1,915,000 / $1.9m / $1,900,000 / $1.9 million.
DOLLAR_FIG = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:m|mil|million|k)?\b",
    re.I,
)
# The abbreviated/rounded form Rule 5 forbids in copy ("$1.25m", "$1.9m", "$1.9 million").
ROUNDED_DOLLAR = re.compile(
    r"\$\s?\d+(?:\.\d+)?\s?(?:m|mil|million|k)\b",
    re.I,
)
# A properly formatted figure: $1,915,000
FORMATTED_DOLLAR = re.compile(r"\$\d{1,3}(?:,\d{3})+\b")

# A range or gap ($1.75M-$1.98M, "$98K hiding", "$98,000 gap").
RANGE_OR_GAP = re.compile(
    r"(\$[\d,\.]+\s?(?:m|k|million)?\s?[-–—to]{1,3}\s?\$?[\d,\.]+\s?(?:m|k|million)?)"
    r"|(\bgap\b)|(\bsaving[s]?\b)|(\bhiding\b)|(\bdifference\b)",
    re.I,
)


# ---------------------------------------------------------------------------
# Property lookup (best-effort, read-only)
# ---------------------------------------------------------------------------

def load_property(slug=None, prop_id=None):
    """Best-effort read-only lookup across Gold_Coast collections.

    Returns (doc, note). doc is None if not found or DB unreachable — the gate
    still runs, it just cannot cross-check planning claims against a verdict.
    """
    if not slug and not prop_id:
        return None, "no --slug/--id given; planning claims cannot be cross-checked against a verdict"
    try:
        from shared.db import get_gold_coast_db
        db = get_gold_coast_db()
    except Exception as e:  # noqa: BLE001
        return None, f"DB unreachable ({e.__class__.__name__}); planning cross-check skipped"

    query = {}
    if slug:
        query = {"url_slug": slug}
    elif prop_id:
        try:
            from bson import ObjectId
            query = {"_id": ObjectId(prop_id)}
        except Exception:
            query = {"_id": prop_id}

    try:
        for coll_name in db.list_collection_names():
            doc = db[coll_name].find_one(query)
            if doc:
                doc["_collection"] = coll_name
                return doc, f"matched in Gold_Coast.{coll_name}"
    except Exception as e:  # noqa: BLE001
        return None, f"lookup failed ({e.__class__.__name__}); planning cross-check skipped"
    return None, "no property matched --slug/--id; planning cross-check skipped"


def planning_verdict(doc):
    """Extract a planning/zoning verdict string from the property doc, if present.

    Prefers zoning_data.cityplan (a written planning verdict), falls back to the
    structured zoning fields. Returns (verdict_text, evidence_dict) or (None, {}).
    """
    if not doc:
        return None, {}
    zd = doc.get("zoning_data") or {}
    evidence = {}
    for k in ("zone", "residential_density", "min_lot_size_sqm",
              "max_storeys", "max_building_height_m"):
        if zd.get(k) not in (None, ""):
            evidence[k] = zd.get(k)

    cityplan = zd.get("cityplan")
    if isinstance(cityplan, dict):
        verdict = cityplan.get("verdict") or cityplan.get("summary") or cityplan.get("assessment")
        if verdict:
            return str(verdict), {"cityplan": cityplan}
    elif isinstance(cityplan, str) and cityplan.strip():
        return cityplan.strip(), {"cityplan": cityplan}

    if evidence:
        # Synthesise a short verdict line from structured zoning.
        parts = []
        if "zone" in evidence:
            parts.append(f"zone={evidence['zone']}")
        if "residential_density" in evidence:
            parts.append(f"density={evidence['residential_density']}")
        if "min_lot_size_sqm" in evidence:
            parts.append(f"min_lot={evidence['min_lot_size_sqm']}sqm")
        return "structured zoning only: " + ", ".join(parts), evidence
    return None, {}


# ---------------------------------------------------------------------------
# Individual checks — each appends (severity, reason) findings.
#   severity: "FAIL" | "QUALIFY" | "INFO"
# ---------------------------------------------------------------------------

def check_forbidden_words(text, findings):
    low = text.lower()
    for w in FORBIDDEN_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            findings.append(("FAIL", f"Forbidden word (Rule 5): \"{w}\". Remove it — value framing only, no hype."))


def check_advice(text, findings):
    for pat in ADVICE_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            findings.append(("FAIL", f"Advice phrasing (Rule 5 'No advice'): \"{m.group(0)}\". Never tell the reader what to do — state data, let them conclude."))


def check_prediction(text, findings):
    for pat in PREDICTION_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            findings.append(("FAIL", f"Prediction phrasing (Rule 5 'No predictions'): \"{m.group(0)}\". Use conditional language ('if X, data suggests Y'); never assert price direction."))


def check_single_valuation_headline(text, findings):
    """A single $ figure presented as the home's worth. Hard FAIL in a headline-like claim.

    A range/gap is allowed (Rule 5, 2026-07-27). A single figure asserted as the
    home's value is not.
    """
    figs = DOLLAR_FIG.findall(text)
    has_range = bool(RANGE_OR_GAP.search(text))
    single_figs = [f for f in figs]
    if len(single_figs) == 1 and not has_range:
        # Is it framed as worth/value/price (headline-like)?
        if HEADLINE_HINT.search(text):
            findings.append((
                "FAIL",
                f"Single valuation figure presented as the home's worth (Rule 5 'No single valuation in headlines'): {single_figs[0].strip()}. "
                "Use a comparable RANGE or a gap/saving instead (e.g. 'comps say $1,750,000-$1,980,000'). "
                "A single figure as worth is only allowed inside the Valuation Guide tab.",
            ))


def check_rounded_dollars(text, findings):
    for m in ROUNDED_DOLLAR.finditer(text):
        findings.append((
            "QUALIFY",
            f"Rounded/abbreviated $ format (Rule 5 'Number format'): \"{m.group(0).strip()}\". "
            "Write the exact figure with commas, e.g. $1,900,000 not $1.9m.",
        ))


def check_suburb_capitalisation(text, findings):
    for sub in KNOWN_SUBURBS:
        # find lowercase occurrences not already capitalised
        for m in re.finditer(r"\b" + re.escape(sub) + r"\b", text, re.I):
            token = m.group(0)
            # Correct capitalisation = each word title-cased
            correct = sub.title()
            if token != correct and token.lower() == sub:
                findings.append((
                    "QUALIFY",
                    f"Suburb not capitalised (Rule 5): \"{token}\" should be \"{correct}\".",
                ))
                break  # one flag per suburb is enough


def check_superlative(text, slug_ref, findings):
    hits = []
    for pat in SUPERLATIVE_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            hits.append(m.group(0))
    if not hits:
        return
    joined = ", ".join(sorted(set(h.lower() for h in hits)))
    target = slug_ref or "<property>"
    findings.append((
        "QUALIFY",
        f"Superlative(s) require data backing: {joined}. "
        "This is unverifiable as written. A reviewer MUST run the backing query before publish:\n"
        f"      python3 scripts/comparable_set.py --slug {target} --market burleigh_waters \\\n"
        "          --dump-sold  # compare the subject against the sold set for this leg\n"
        "    WARNING: our sold set is a FLOOR, not a census of the market. It captures sales we "
        "have ingested, not every sale. An unqualified 'only/best/every' claim OVER THE WHOLE "
        "MARKET can never be verified from it. Qualify to what is checkable "
        "('of the homes CURRENTLY ADVERTISED that publish a price...') or drop the superlative.",
    ))


def check_dollar_preflight(text, findings):
    """Rule 5 (2026-07-27) $-claim pre-flight checklist."""
    has_fig = bool(DOLLAR_FIG.search(text))
    has_range_gap = bool(RANGE_OR_GAP.search(text))
    if not (has_fig or has_range_gap):
        return
    findings.append((
        "QUALIFY",
        "$-claim pre-flight (Rule 5, 2026-07-27) — MANDATORY before this ad/claim ships:\n"
        "      [ ] (a) Claim points to a landing page that VISIBLY shows the valuation methodology "
        "+ confidence disclaimer. Property pages already do; /for-sale-v3 needs the one-line "
        "disclaimer present.\n"
        "      [ ] (b) It is NOT a single-property valuation stated as the home's worth in a "
        "headline (ranges & gaps/savings are allowed; a single 'worth' figure is not).\n"
        "    Allowed: comparable RANGES and GAPS/SAVINGS ('$98,000 hiding in plain sight', "
        "'comps say $1,750,000-$1,980,000'). This checklist is not auto-satisfied — a human "
        "confirms the landing page before publish.",
    ))


def check_planning(text, verdict, verdict_evidence, findings):
    hits = []
    for pat in PLANNING_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            hits.append(m.group(0))
    if not hits:
        return
    joined = ", ".join(sorted(set(h.lower().strip() for h in hits)))

    # Base requirement: a cited source document.
    base = (
        f"Development/zoning/planning claim(s): {joined}. "
        "REQUIRES a cited source document (Gold Coast City Plan mapping, a DA number, a town-"
        "planner's letter, or the property's own zoning_data.cityplan verdict). "
        "The 'Res B' claim FAILED exactly here — no source document existed."
    )

    if verdict:
        vlow = verdict.lower()
        # Detect contradiction: claim asserts duplex/development-yes while verdict says otherwise.
        claim_asserts_yield = any(
            re.search(p, text, re.I) for p in
            [r"\bduplex\b", r"\bdevelopment (?:site|block|potential)\b",
             r"\bsubdivi", r"\bdual occupancy\b", r"\bapproved\b"]
        )
        verdict_denies = any(
            k in vlow for k in
            ["impact-assessable", "impact assessable", "not a duplex", "no duplex",
             "not a development", "single dwelling", "does not support",
             "not supported", "code assessable would not", "unlikely", "no subdivision"]
        )
        if claim_asserts_yield and verdict_denies:
            findings.append((
                "FAIL",
                base + f"\n    CONTRADICTS the property's planning verdict: \"{verdict}\". "
                "The claim asserts a yield the verdict does not support. Do not publish.",
            ))
            return
        findings.append((
            "FAIL",
            base + f"\n    Property planning verdict on file: \"{verdict}\". "
            "Confirm the claim is consistent with it AND cite the source document. "
            "Unsourced planning claims are FAIL until a document is attached.",
        ))
    else:
        findings.append((
            "FAIL",
            base + "\n    No planning verdict found on the property "
            "(zoning_data.cityplan absent, or no --slug/--id given). "
            "A planning claim with no source document is FAIL.",
        ))


def check_valuation_guardrails(text, findings):
    for pat, reason in VALUATION_CLAIM_PATTERNS:
        if re.search(pat, text, re.I):
            findings.append(("FAIL", f"Valuation-accuracy guardrail: {reason}"))
    # "more accurate" adjustment claim (0.5 -> 0.8 adjustments)
    if re.search(r"\b(?:adjust\w*|adjusted comparables?)\b", text, re.I) and re.search(r"\bmore accurate\b", text, re.I):
        findings.append((
            "FAIL",
            "'adjusted comparables are more accurate' — the adjustment step's accuracy gain is NOT "
            "supported by backtest. Never claim adjusted comps are 'more accurate'. Sayable: we show "
            "our working / per-feature adjustments transparently.",
        ))


# ---------------------------------------------------------------------------
# Per-claim evaluation
# ---------------------------------------------------------------------------

def evaluate_claim(text, verdict, verdict_evidence, slug_ref):
    findings = []
    check_forbidden_words(text, findings)
    check_advice(text, findings)
    check_prediction(text, findings)
    check_single_valuation_headline(text, findings)
    check_rounded_dollars(text, findings)
    check_suburb_capitalisation(text, findings)
    check_superlative(text, slug_ref, findings)
    check_dollar_preflight(text, findings)
    check_planning(text, verdict, verdict_evidence, findings)
    check_valuation_guardrails(text, findings)

    severities = {sev for sev, _ in findings}
    if "FAIL" in severities:
        verdict_label = "FAIL"
    elif "QUALIFY" in severities:
        verdict_label = "NEEDS-QUALIFIER"
    else:
        verdict_label = "PASS"
    return verdict_label, findings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

VERDICT_ICON = {"PASS": "PASS ", "NEEDS-QUALIFIER": "QUAL ", "FAIL": "FAIL "}


def render_human(results, property_note, verdict, verdict_evidence):
    out = []
    out.append("=" * 78)
    out.append("CLAIM GATE — marketing fact-check (CLAUDE.md Rule 5 + valuation claim limits)")
    out.append("=" * 78)
    out.append(f"Property: {property_note}")
    if verdict:
        out.append(f"Planning verdict on file: {verdict}")
    out.append("")
    for i, (text, label, findings) in enumerate(results, 1):
        out.append(f"[{label}] Claim {i}: {text}")
        if not findings:
            out.append("    (no tripwire fired — human sign-off still required)")
        for sev, reason in findings:
            tag = {"FAIL": "FAIL", "QUALIFY": "QUALIFY", "INFO": "INFO"}[sev]
            out.append(f"    - [{tag}] {reason}")
        out.append("")
    n_fail = sum(1 for _, l, _ in results if l == "FAIL")
    n_qual = sum(1 for _, l, _ in results if l == "NEEDS-QUALIFIER")
    n_pass = sum(1 for _, l, _ in results if l == "PASS")
    out.append("-" * 78)
    out.append(f"SUMMARY: {n_pass} PASS · {n_qual} NEEDS-QUALIFIER · {n_fail} FAIL")
    if n_fail:
        out.append("RESULT: BLOCKED — at least one claim is FAIL. Do not publish. (exit 1)")
    elif n_qual:
        out.append("RESULT: HOLD — qualifiers/verify-queries required before publish. (exit 0)")
    else:
        out.append("RESULT: CLEAR of automated tripwires — human sign-off still required. (exit 0)")
    out.append("-" * 78)
    return "\n".join(out)


def render_json(results, property_note, verdict):
    payload = {
        "property": property_note,
        "planning_verdict": verdict,
        "claims": [
            {
                "claim": text,
                "verdict": label,
                "findings": [{"severity": sev, "reason": reason} for sev, reason in findings],
            }
            for text, label, findings in results
        ],
        "summary": {
            "pass": sum(1 for _, l, _ in results if l == "PASS"),
            "needs_qualifier": sum(1 for _, l, _ in results if l == "NEEDS-QUALIFIER"),
            "fail": sum(1 for _, l, _ in results if l == "FAIL"),
        },
    }
    payload["blocked"] = payload["summary"]["fail"] > 0
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def gather_claims(args):
    claims = []
    if args.claim:
        claims.extend(args.claim)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    claims.append(line)
    return claims


def main():
    ap = argparse.ArgumentParser(
        description="Marketing-claim fact-check gate (CLAUDE.md Rule 5). Exits non-zero if any claim FAILs.",
    )
    ap.add_argument("--claim", action="append", help="A claim string (repeatable).")
    ap.add_argument("--file", help="File of claims, one per line (# comments allowed).")
    ap.add_argument("--slug", help="Property url_slug for planning cross-check + verify query.")
    ap.add_argument("--id", dest="prop_id", help="Property _id (ObjectId) alternative to --slug.")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable.")
    args = ap.parse_args()

    claims = gather_claims(args)
    if not claims:
        ap.error("no claims given — use --claim or --file")

    doc, property_note = load_property(args.slug, args.prop_id)
    verdict, verdict_evidence = planning_verdict(doc)
    slug_ref = args.slug or (doc.get("url_slug") if doc else None)

    results = []
    for text in claims:
        label, findings = evaluate_claim(text, verdict, verdict_evidence, slug_ref)
        results.append((text, label, findings))

    if args.json:
        print(render_json(results, property_note, verdict))
    else:
        print(render_human(results, property_note, verdict, verdict_evidence))

    if any(l == "FAIL" for _, l, _ in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

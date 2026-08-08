#!/usr/bin/env python3
"""
guardrails.py -- editorial compliance linter for the owner-subject article.

This is unsolicited mail about someone's home. The failure modes are specific and
each one is a rule in CLAUDE.md section 5 or a standing memory:

  ADVICE      telling the reader what to do -- liability risk, and the whole
              editorial position is "data only, reader draws conclusions".
  PREDICTION  stating what prices will do. Report indicators, never forecast.
  URGENCY     manufactured scarcity/pressure. This piece asks for nothing.
  SOLICIT     any CTA, invitation, or mention of selling/appraisals. For the
              posted owner-subject piece, reading as solicitation IS the failure.
  VALUATION   a single figure presented as what the home is worth. The RANGE of
              adjusted comparables is the valuation.
  CONFIDENCE  printing a confidence grade. Measured across 512 sold homes it is
              non-discriminating (high 56.0% vs medium 57.5%), so a grade tells
              the reader nothing true.
  WORDS       house-style banned vocabulary.

BLOCK findings must be zero before anything is rendered for post. WARN findings
are for human judgement.
"""
from __future__ import annotations

import re

# (severity, label, pattern, why)
RULES: list[tuple[str, str, str, str]] = [
    # ---- advice ----
    ("BLOCK", "ADVICE", r"\byou should\b", "direct instruction to the reader"),
    ("BLOCK", "ADVICE", r"\byou (?:need|ought) to\b", "direct instruction"),
    ("BLOCK", "ADVICE", r"\bwe recommend\b", "recommendation"),
    ("BLOCK", "ADVICE", r"\b(?:consider|think about) (?:selling|listing|buying)\b", "advice to transact"),
    ("BLOCK", "ADVICE", r"\bnow (?:is|would be) a (?:good|great|smart) time\b", "timing advice"),
    ("BLOCK", "ADVICE", r"\bthe best (?:time|move|option) (?:is|would be)\b", "prescriptive"),
    ("WARN",  "ADVICE", r"\bweigh it accordingly\b", "vague hedge that tells the reader nothing"),

    # ---- prediction ----
    ("BLOCK", "PREDICTION", r"\bprices will\b", "forecast"),
    ("BLOCK", "PREDICTION", r"\bwill (?:rise|fall|climb|drop|increase|decrease)\b", "forecast"),
    ("BLOCK", "PREDICTION", r"\b(?:expect|anticipate) (?:prices|values|the market) to\b", "forecast"),
    ("BLOCK", "PREDICTION", r"\bis (?:set|poised|likely) to (?:rise|fall|grow)\b", "forecast"),
    ("WARN",  "PREDICTION", r"\b(?:turning point|cooling|recovery|rebound|upturn|downturn)\b",
     "trend language -- report the measured figure, do not name a trend"),

    # ---- urgency / solicitation ----
    ("BLOCK", "URGENCY", r"\b(?:act now|don't miss|limited time|before it's too late)\b", "manufactured urgency"),
    ("BLOCK", "SOLICIT", r"\b(?:contact|call|email|phone) (?:us|me|the fields|our team)\b", "CTA"),
    ("BLOCK", "SOLICIT", r"\b(?:book|request|arrange) (?:a|an|your) (?:appraisal|valuation|consultation|call)\b", "CTA"),
    ("BLOCK", "SOLICIT", r"\bfree (?:appraisal|valuation|market appraisal)\b", "solicitation"),
    ("BLOCK", "SOLICIT", r"\bif you(?:'re| are) (?:thinking of|considering) selling\b", "solicitation"),
    ("BLOCK", "SOLICIT", r"\bwhat your home could achieve\b", "solicitation"),
    ("WARN",  "SOLICIT", r"\bget in touch\b", "reads as an invitation"),

    # ---- confidence grade ----
    ("BLOCK", "CONFIDENCE", r"\bconfidence (?:grade|level|rating)\b", "grade is non-discriminating -- do not print"),
    ("BLOCK", "CONFIDENCE", r"\bconfidence(?: recorded)?(?: for this set)?:\s*(?:high|medium|low|very low)\b",
     "grade is non-discriminating -- do not print"),
    ("BLOCK", "CONFIDENCE", r"\b(?:high|medium|low|very low)[- ]confidence\b", "grade is non-discriminating"),
    # ⚠ Narrow, deliberately. There are TWO different intervals in this article and
    # only one of them is a lie:
    #   * the PROPERTY band (+/-12% of reconciled_valuation) is NOT a statistical CI
    #     -- it contains the actual sale price ~57% of the time. Calling it a 90%
    #     confidence range is the thing this rule exists to stop.
    #   * the SUBURB MEDIAN interval IS a real bootstrap 90% CI --
    #     `precompute_union_prices.bootstrap_ci(values, confidence=0.90)`. Disclosing
    #     it is honest and is exactly the "publish the confidence" move.
    # So the block is scoped by EXEMPTION: a line that is talking about the median is
    # allowed to say 90% CI. See `_EXEMPT`.
    ("BLOCK", "CONFIDENCE", r"\b90% confidence (?:range|interval)\b",
     "the property's +/-12% band is not a statistical CI -- it contains the sale "
     "price ~57% of the time (the suburb MEDIAN's bootstrap CI is exempt)"),

    # ---- house style ----
    ("BLOCK", "WORDS", r"\bstunning\b", "banned word"),
    ("BLOCK", "WORDS", r"\bnestled\b", "banned word"),
    ("BLOCK", "WORDS", r"\bboasting\b", "banned word"),
    ("BLOCK", "WORDS", r"\brare opportunity\b", "banned phrase"),
    ("BLOCK", "WORDS", r"\brobust market\b", "banned phrase"),
    ("WARN",  "WORDS", r"\$\d+(?:\.\d+)?\s?m\b", "use $1,250,000 not $1.25m"),

    # ---- our-history-as-excuse (Will, 2026-08-05) ----
    ("WARN", "FRAMING", r"\b(?:we|our) (?:only )?(?:began|started) (?:recording|tracking|collecting)\b",
     "never narrate our collection history -- attach the sample size to the figure instead"),
    ("WARN", "FRAMING", r"\bhas only been recorded here\b",
     "'here' reads as the suburb but means our database"),
]

_HEADLINE_MONEY = re.compile(r"\$[\d,]+")

# Per-RULE exemptions, keyed by the rule's own pattern -- deliberately NOT keyed by
# label, which would also excuse the confidence-GRADE rules sharing that label.
# If the matched line also matches the exemption, the finding is dropped.
_EXEMPT = {
    # The union pipeline's suburb-median interval is a genuine bootstrap 90% CI
    # (`precompute_union_prices.bootstrap_ci(values, confidence=0.90)`), so a line
    # about the median may say so. The property's +/-12% band still may not.
    r"\b90% confidence (?:range|interval)\b":
        re.compile(r"\bmedian\b", re.IGNORECASE),
}


def lint(markdown: str) -> list[dict]:
    """Return findings. Each: {severity, label, why, match, line}."""
    findings = []
    lines = markdown.splitlines()
    for sev, label, pat, why in RULES:
        rx = re.compile(pat, re.IGNORECASE)
        exempt = _EXEMPT.get(pat)
        for i, line in enumerate(lines, 1):
            if exempt and exempt.search(line):
                continue
            for m in rx.finditer(line):
                findings.append({
                    "severity": sev, "label": label, "why": why,
                    "match": m.group(0), "line": i,
                })

    # Structural rule: no money figure in ANY heading. The range lives in the body,
    # attached to the sample it came from.
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("#") and _HEADLINE_MONEY.search(line):
            findings.append({
                "severity": "BLOCK", "label": "VALUATION",
                "why": "no valuation figure in a headline -- ranges belong in the body",
                "match": line.strip()[:80], "line": i,
            })

    findings.sort(key=lambda f: (f["severity"] != "BLOCK", f["line"]))
    return findings


def blocks(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f["severity"] == "BLOCK"]


def format_report(findings: list[dict]) -> str:
    if not findings:
        return "guardrails: clean (0 findings)"
    out = []
    for f in findings:
        out.append(f"  [{f['severity']}] {f['label']} line {f['line']}: "
                   f"{f['match']!r} -- {f['why']}")
    n_block = len(blocks(findings))
    return (f"guardrails: {len(findings)} finding(s), {n_block} BLOCK\n"
            + "\n".join(out))

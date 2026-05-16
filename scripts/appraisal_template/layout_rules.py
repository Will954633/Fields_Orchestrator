"""Section content budgets for V4 appraisal reports — Layer 1.

This module defines declarative content-length budgets for each templated
section of the V4 appraisal. It validates rendered section payloads against
those budgets and records warnings/errors without modifying the payload.

Phase 1 (current): observational only. Budgets fire warnings; no truncation
or compact-variant fallback. The audit JSON written next to each generated
PDF reveals which budgets are realistic and which need tuning.

Phase 2 (future): renderers consume the validation result and switch to a
compact layout variant when a hard limit fires.

Each section_key maps to a list of Rule dicts:
    {"field": "headline_html", "kind": "max_chars", "soft": 60, "hard": 80}

`kind` is one of:
    max_chars   — len of the value (HTML-stripped) ≤ limit
    max_words   — whitespace-split word count ≤ limit
    max_items   — len of a list ≤ limit
    exact_items — len of a list == limit
    min_items   — len of a list ≥ limit

`field` paths support dotted access and a `[*]` wildcard to iterate a list.
Examples:
    "subhead"
    "personas[*].demographics"
    "cards[*].adjustments"  (validates the length of each card's adjustments list)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

# Universal defaults — tuned to actual V4 rendering (subheads run long, often
# wrap to 2 lines and still fit visually). Section overrides tighten these
# where the on-page space is genuinely smaller.
_UNIVERSAL_RULES = [
    {"field": "headline_html", "kind": "max_chars", "soft": 60, "hard": 80},
    {"field": "subhead", "kind": "max_chars", "soft": 130, "hard": 175},
]


SECTION_RULES: dict[str, list[dict]] = {
    "01_right": [
        *_UNIVERSAL_RULES,
        {"field": "feature_bullets", "kind": "max_items", "soft": 5, "hard": 6},
        {"field": "feature_bullets[*]", "kind": "max_words", "soft": 4, "hard": 6},
        {"field": "cohort_body_html", "kind": "max_words", "soft": 30, "hard": 40},
        {"field": "advantage_body_html", "kind": "max_words", "soft": 110, "hard": 130},
    ],
    "02_right": [
        *_UNIVERSAL_RULES,
        {"field": "headline_html", "kind": "max_chars", "soft": 40, "hard": 55},
        {"field": "personas", "kind": "min_items", "soft": 2, "hard": 1},
        {"field": "personas", "kind": "max_items", "soft": 3, "hard": 4},
        {"field": "personas[*].label", "kind": "max_chars", "soft": 30, "hard": 38},
        {"field": "personas[*].demographics", "kind": "max_words", "soft": 28, "hard": 35},
        {"field": "personas[*].evidence_note", "kind": "max_words", "soft": 24, "hard": 32},
        {"field": "personas[*].willingness_range", "kind": "max_chars", "soft": 16, "hard": 20},
        {"field": "anti_fit", "kind": "max_words", "soft": 15, "hard": 22},
        {"field": "caption", "kind": "max_words", "soft": 42, "hard": 55},
        {"field": "advantage_body_html", "kind": "max_words", "soft": 100, "hard": 120},
    ],
    "03_right": [
        *_UNIVERSAL_RULES,
        {"field": "cohort_anchor_html", "kind": "max_words", "soft": 35, "hard": 45},
        {"field": "evidence_stack", "kind": "max_items", "soft": 3, "hard": 4},
        {"field": "evidence_stack[*].signal", "kind": "max_words", "soft": 18, "hard": 24},
        {"field": "method_note", "kind": "max_words", "soft": 22, "hard": 28},
        {"field": "caption", "kind": "max_words", "soft": 35, "hard": 50},
        {"field": "advantage_body_html", "kind": "max_words", "soft": 100, "hard": 130},
    ],
    "03_receipts": [
        *_UNIVERSAL_RULES,
        {"field": "cards", "kind": "max_items", "soft": 3, "hard": 3},
        {"field": "cards[*].address", "kind": "max_chars", "soft": 32, "hard": 38},
        {"field": "cards[*].adjustments", "kind": "max_items", "soft": 6, "hard": 8},
        {"field": "caption", "kind": "max_words", "soft": 35, "hard": 50},
    ],
    "04_right": [
        *_UNIVERSAL_RULES,
        {"field": "modes", "kind": "exact_items", "soft": 3, "hard": 3},
        # Retargeting mode label is "Retargeting (active and passive, after engagement)" — 50 chars.
        {"field": "modes[*].label", "kind": "max_chars", "soft": 42, "hard": 55},
        {"field": "modes[*].desc", "kind": "max_words", "soft": 28, "hard": 38},
        {"field": "modes[*].channels", "kind": "max_chars", "soft": 65, "hard": 80},
        {"field": "caption", "kind": "max_words", "soft": 35, "hard": 50},
        {"field": "advantage_body_html", "kind": "max_words", "soft": 95, "hard": 120},
    ],
    "05_right": [
        *_UNIVERSAL_RULES,
        {"field": "presentation_rows", "kind": "max_items", "soft": 3, "hard": 4},
        {"field": "presentation_rows[*].label", "kind": "max_chars", "soft": 28, "hard": 35},
        {"field": "presentation_rows[*].desc", "kind": "max_words", "soft": 35, "hard": 50},
        {"field": "advantage_body_html", "kind": "max_words", "soft": 90, "hard": 110},
    ],
    "06_right": [
        *_UNIVERSAL_RULES,
        {"field": "assets", "kind": "max_items", "soft": 3, "hard": 4},
        {"field": "assets[*].label", "kind": "max_chars", "soft": 28, "hard": 35},
        {"field": "assets[*].desc", "kind": "max_words", "soft": 30, "hard": 38},
        {"field": "advantage_body_html", "kind": "max_words", "soft": 90, "hard": 110},
    ],
    "recommendation_p11": [
        {"field": "derived_range_explanation", "kind": "max_words", "soft": 35, "hard": 45},
    ],
    "recommendation_p18": [
        {"field": "campaign_duration_days", "kind": "max_chars", "soft": 18, "hard": 22},
    ],
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    """Outcome of applying a single rule."""
    field: str
    kind: str
    value: int
    limit_soft: int | None
    limit_hard: int | None
    status: str  # "ok" | "warn" | "fail" | "missing"
    detail: str | None = None


@dataclass
class ValidationResult:
    """Aggregate of all rules applied to one section."""
    section_key: str
    applied_rules: list[RuleResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(self.errors)

    @property
    def n_warn(self) -> int:
        return len([r for r in self.applied_rules if r.status == "warn"])

    @property
    def n_fail(self) -> int:
        return len([r for r in self.applied_rules if r.status == "fail"])

    def to_dict(self) -> dict:
        return {
            "section_key": self.section_key,
            "applied_rules": [r.__dict__ for r in self.applied_rules],
            "warnings": self.warnings,
            "errors": self.errors,
        }


# Module-level register: renderers append their ValidationResult here so
# generate_appraisal_v4.py can drain and write a unified audit file at the
# end of a render run. clear_records() is called at the start of each render.
_VALIDATION_RECORDS: list[ValidationResult] = []


def clear_records() -> None:
    _VALIDATION_RECORDS.clear()


def get_records() -> list[ValidationResult]:
    return list(_VALIDATION_RECORDS)


def validate_and_record(section_key: str, fields: dict) -> ValidationResult:
    """Convenience: validate, append to the module register, return result."""
    result = validate(section_key, fields)
    _VALIDATION_RECORDS.append(result)
    return result


# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    return _HTML_TAG_RE.sub("", s or "").strip()


def _word_count(s: str) -> int:
    s = _strip_html(s)
    if not s:
        return 0
    return len([w for w in _WS_RE.split(s) if w])


def _char_count(s: str) -> int:
    return len(_strip_html(s))


def _resolve_field(fields: dict, path: str) -> list[tuple[str, Any]]:
    """Resolve a dotted field path with [*] wildcards. Returns list of
    (display_path, value) tuples. Used so a single rule can fire against
    every item in a list (e.g. `personas[*].demographics`)."""
    parts = path.split(".")
    results: list[tuple[str, Any]] = [("", fields)]
    for part in parts:
        next_results: list[tuple[str, Any]] = []
        if part.endswith("[*]"):
            key = part[:-3]
            for prefix, ctx in results:
                if not isinstance(ctx, dict):
                    continue
                lst = ctx.get(key)
                if not isinstance(lst, list):
                    continue
                for i, item in enumerate(lst):
                    new_prefix = f"{prefix}.{key}[{i}]" if prefix else f"{key}[{i}]"
                    next_results.append((new_prefix, item))
        else:
            for prefix, ctx in results:
                if not isinstance(ctx, dict):
                    continue
                val = ctx.get(part)
                new_prefix = f"{prefix}.{part}" if prefix else part
                next_results.append((new_prefix, val))
        results = next_results
    return results


def _apply_rule(rule: dict, label: str, value: Any) -> RuleResult:
    """Apply a single rule against a single value. Returns one RuleResult."""
    kind = rule["kind"]
    soft = rule.get("soft")
    hard = rule.get("hard")

    if value is None:
        return RuleResult(field=label, kind=kind, value=0, limit_soft=soft,
                          limit_hard=hard, status="missing",
                          detail="field is None/missing — not validating")

    if kind == "max_chars":
        measured = _char_count(str(value))
    elif kind == "max_words":
        measured = _word_count(str(value))
    elif kind in ("max_items", "exact_items", "min_items"):
        measured = len(value) if isinstance(value, (list, tuple)) else 0
    else:
        return RuleResult(field=label, kind=kind, value=0, limit_soft=soft,
                          limit_hard=hard, status="missing",
                          detail=f"unknown rule kind: {kind}")

    # Determine status
    status = "ok"
    detail = None
    if kind == "exact_items":
        if measured != soft:
            status = "fail"
            detail = f"expected exactly {soft}, got {measured}"
    elif kind == "min_items":
        if hard is not None and measured < hard:
            status = "fail"
            detail = f"below hard min {hard}"
        elif soft is not None and measured < soft:
            status = "warn"
            detail = f"below soft min {soft}"
    else:  # max_* kinds
        if hard is not None and measured > hard:
            status = "fail"
            detail = f"exceeds hard limit {hard}"
        elif soft is not None and measured > soft:
            status = "warn"
            detail = f"exceeds soft limit {soft}"

    return RuleResult(field=label, kind=kind, value=measured,
                      limit_soft=soft, limit_hard=hard, status=status,
                      detail=detail)


def validate(section_key: str, fields: dict) -> ValidationResult:
    """Validate a section payload against its declared budgets. Pure function —
    does not mutate `fields`. Phase 1: warnings only; renderers ignore the
    result. Phase 2: renderers consume `result.has_failures` to switch
    to compact layout variants."""
    result = ValidationResult(section_key=section_key)
    rules = SECTION_RULES.get(section_key, [])
    if not rules:
        return result
    for rule in rules:
        resolved = _resolve_field(fields, rule["field"])
        for label, value in resolved:
            rule_result = _apply_rule(rule, label, value)
            result.applied_rules.append(rule_result)
            if rule_result.status == "warn":
                msg = f"[{section_key}] {label}: {rule_result.value} (soft {rule_result.limit_soft})"
                result.warnings.append(msg)
            elif rule_result.status == "fail":
                msg = f"[{section_key}] {label}: {rule_result.value} {rule_result.detail}"
                result.errors.append(msg)
    return result

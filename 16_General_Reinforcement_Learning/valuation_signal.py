#!/usr/bin/env python3
"""
valuation_signal.py — the VALUATION sensor: is the number we show sellers any good?

Sibling to ops_signal.py. Where that one answers "what is broken in the MACHINE", this
answers "what is broken in the PRODUCT" — the reconciled valuation and the range around
it, which every other thing Fields makes (property page, appraisal, mini-site, off-market
report) is a wrapper around.

It measures four things, in the order the mandate ranks them:

  1. COVERAGE      — share of the live for-sale book carrying a reconciled valuation,
                     and the SPLIT of the failures by cause. A refusal for a stated
                     reason is not the same defect as a silent never-computed.
  2. SUPPRESSION   — the design-envelope flag ($1,000,000-$2,000,000, detached houses).
                     A suppressed valuation is the method behaving CORRECTLY; a rising
                     suppressed share is the market leaving the method behind, which is
                     a strategy question, not a bug.
  3. COMP-POOL     — how thin the comparable pools are: comps used per subject, their
                     recency, how many subjects sit at the floor. This is where accuracy
                     dies without erroring — the estimate can never exceed its priciest
                     comparable, so a thinning pool drags every number toward the median.
  4. INTEGRITY     — internal contradictions in what the documents claim about themselves.

It does NOT judge, fix, or recompute anything. It counts, and it writes
system_monitor.rl_valuation_signal (_id="latest" + a timestamped history doc so the agent
can see direction of travel rather than one week's snapshot). Rule 7 heartbeat as
`rl_valuation_signal`.

──────────────────────────────────────────────────────────────────────────────────────
⚠ EVERY PATH BELOW WAS VERIFIED BEFORE USE (CLAUDE.md Rule 8), 2026-08-13.
A query returning zero is a fact about the field name you typed, not about the data.
Reproduce with:

    python3 scripts/db_fields.py --find valuation
    python3 scripts/db_fields.py Gold_Coast robina --check valuation_data.confidence.reconciled_valuation \
        --query '{"listing_status": "for_sale"}'
    python3 scripts/db_fields.py Gold_Coast robina --grep adjusted_comparables \
        --query '{"listing_status": "for_sale"}'
    awk -F'\t' '$1=="Gold_Coast" && $2=="robina" && $3 ~ /^valuation_data\./' SCHEMA_PATHS.tsv

Paths that DO NOT EXIST — do not reintroduce them from memory or intuition:
    directional_only            (bare/top-level)   0/108 — the real one is nested, see below
    valuation_data.confidence.confidence_reason    0/108 — there is no single "confidence
                                                   reason"; there are three different ones
                                                   (directional_reason / exclusion_reason /
                                                   suburb_calibration.reason)
    valuation_status / valuation_failed / valuation_error
                                                   0/108 — failure is expressed as
                                                   exclusion_reason + insufficient_data +
                                                   confidence == "not_available"
    valuation_data.comparables[]                   legacy shape, ~1/300. Use
                                                   adjusted_comparables[].

⚠ `valuation_data` itself is present on 212/212 live listings, so an unvalued property is
NEVER a missing sub-document — it is `reconciled_valuation: null`. Counting documents that
lack the key would report 0 unvalued and be completely wrong.
──────────────────────────────────────────────────────────────────────────────────────

Usage:
    python3 valuation_signal.py            # collect + write
    python3 valuation_signal.py --dry-run  # print, don't write
"""
import argparse
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from shared.db import get_client  # noqa: E402

# Verified collection names in the Gold_Coast master DB (2026-08-13). Deliberately NOT
# read from config/settings.yaml: that file lists target SUBURBS for the scrape schedule,
# and the mapping suburb -> collection is a naming convention, not a guarantee. If a
# fourth suburb goes live, add it here after checking the collection actually exists.
#
# ⚠ Gold_Coast_Currently_For_Sale holds a SMALLER, disagreeing mirror (83 docs vs 212).
# It is deprecated and read-only. Never count from it.
SUBURBS = ("robina", "varsity_lakes", "burleigh_waters")
LIVE = {"listing_status": "for_sale"}

# The figure shown to a seller. int, or null when we could not or would not value.
RV = "valuation_data.confidence.reconciled_valuation"

# The design envelope, from precompute_valuations.py: _ENVELOPE_MIN = 1_000_000,
# _ENVELOPE_MAX = 2_000_000, applied as `_ENVELOPE_MIN <= rv < _ENVELOPE_MAX` — note the
# STRICT ceiling, so exactly $2,000,000 is above_design_ceiling, not inside.
ENVELOPE_MIN = 1_000_000
ENVELOPE_MAX = 2_000_000

# ⚠ THREE copies of the envelope flag exist and they do not agree.
#   valuation_data.confidence.directional_only  — written True only; absent = no breach
#   valuation_data.summary.directional_only     — mirror, matched confidence in all 3 suburbs
#   valuation_data.metadata.directional_only    — ALSO written False, so its FILL count is
#                                                 not its TRUE count, and on 2026-08-13 it
#                                                 disagreed with the other two in
#                                                 burleigh_waters (19 vs 21).
# We report all three plus the disagreement count rather than picking a winner. Picking
# one would hide exactly the inconsistency worth knowing about.
DIRECTIONAL_PATHS = (
    "valuation_data.confidence.directional_only",
    "valuation_data.summary.directional_only",
    "valuation_data.metadata.directional_only",
)

# A pool this thin cannot support a weighted mean that means anything. Not a threshold the
# method enforces — a line for triage, so "at the floor" is countable.
THIN_POOL_MAX = 3
STALE_COMP_DAYS = 365


def _dig(doc, path):
    """doc['a']['b'] for 'a.b', tolerating missing keys AND null intermediates.

    Null intermediates are the norm here, not an edge case: `valuation_data.confidence.range`
    is present on 108/108 docs and is `null` on the unvalued ones. A plain chained .get()
    raises AttributeError on those.
    """
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _parse_date(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and len(v) >= 10:
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def collect_suburb(coll, now):
    """Everything measurable about one suburb's live for-sale book."""
    docs = list(coll.find(LIVE, {
        "address": 1, "property_type": 1, "classified_property_type": 1,
        "bedrooms": 1, "valuation_data": 1, "enriched_data.floor_area_sqm": 1,
    }))
    total = len(docs)
    if total == 0:
        return {"total_for_sale": 0, "docs_scanned": 0}

    valued = unvalued = 0
    exclusion = Counter()
    conf_tier = Counter()
    directional = {p: 0 for p in DIRECTIONAL_PATHS}
    directional_reason = Counter()
    in_envelope = above_env = below_env = 0
    n_used, comp_ages, thin_pools, zero_pools = [], [], 0, 0
    stale_comp_subjects = 0
    computed_ages = []
    missing_floor_area = missing_land_size = 0
    # Integrity contradictions — each is a document disagreeing with itself.
    contra_insufficient_but_valued = 0
    contra_valued_no_range = 0
    contra_directional_with_figure = 0
    directional_disagreement = 0

    for d in docs:
        rv = _dig(d, RV)
        has_rv = rv is not None
        valued += has_rv
        unvalued += (not has_rv)

        tier = _dig(d, "valuation_data.confidence.confidence")
        conf_tier[tier if tier else "(absent)"] += 1

        # Why it failed. Written in two places; either is authoritative, prefer summary.
        reason = (_dig(d, "valuation_data.summary.exclusion_reason")
                  or _dig(d, "valuation_data.confidence.exclusion_reason"))
        if not has_rv:
            exclusion[reason or "(no reason recorded)"] += 1

        flags = {p: _dig(d, p) for p in DIRECTIONAL_PATHS}
        for p, v in flags.items():
            if v is True:
                directional[p] += 1
        # True where the three copies do not tell the same story about this document.
        if len({bool(v) for v in flags.values()}) > 1:
            directional_disagreement += 1
        if any(v is True for v in flags.values()):
            directional_reason[_dig(d, "valuation_data.confidence.directional_reason")
                               or "(none)"] += 1
            if has_rv:
                contra_directional_with_figure += 1

        if has_rv:
            if rv < ENVELOPE_MIN:
                below_env += 1
            elif rv >= ENVELOPE_MAX:      # strict ceiling, mirrors the production check
                above_env += 1
            else:
                in_envelope += 1
            lo = _dig(d, "valuation_data.confidence.range.low")
            hi = _dig(d, "valuation_data.confidence.range.high")
            if lo is None or hi is None:
                contra_valued_no_range += 1

        if _dig(d, "valuation_data.summary.insufficient_data") is True and has_rv:
            contra_insufficient_but_valued += 1

        used = _dig(d, "valuation_data.summary.n_included_in_valuation")
        if isinstance(used, int):
            n_used.append(used)
            if used == 0:
                zero_pools += 1
            elif used <= THIN_POOL_MAX:
                thin_pools += 1

        comps = _dig(d, "valuation_data.adjusted_comparables") or []
        ages = []
        for c in comps:
            sd = _parse_date((c or {}).get("sale_date"))
            if sd:
                ages.append((now - sd).days)
        if ages:
            med = statistics.median(ages)
            comp_ages.append(med)
            if med > STALE_COMP_DAYS:
                stale_comp_subjects += 1

        ca = _parse_date(_dig(d, "valuation_data.computed_at"))
        if ca:
            computed_ages.append((now - ca).days)

        # The two adjustments that carry the most weight, and the two most often missing.
        if not (_dig(d, "valuation_data.subject_property.features.basic.floor_area_sqm")
                or _dig(d, "enriched_data.floor_area_sqm")):
            missing_floor_area += 1
        if not _dig(d, "valuation_data.subject_property.features.basic.land_size_sqm"):
            missing_land_size += 1

    def _med(xs):
        return round(statistics.median(xs), 1) if xs else None

    return {
        "total_for_sale": total,
        "docs_scanned": total,
        "valued": valued,
        "unvalued": unvalued,
        "coverage_pct": _pct(valued, total),
        "unvalued_pct": _pct(unvalued, total),
        "exclusion_reasons": dict(exclusion.most_common()),
        "confidence_tiers": dict(conf_tier.most_common()),
        "directional_by_path": directional,
        "directional_disagreement": directional_disagreement,
        "directional_reasons": dict(directional_reason.most_common()),
        "envelope": {"inside": in_envelope, "above": above_env, "below": below_env,
                     "inside_pct_of_valued": _pct(in_envelope, valued)},
        "comp_pool": {
            "median_comps_used": _med(n_used),
            "min_comps_used": min(n_used) if n_used else None,
            "zero_comp_subjects": zero_pools,
            "thin_pool_subjects": thin_pools,
            "thin_pool_pct_of_valued": _pct(thin_pools + zero_pools, valued),
            "median_comp_age_days": _med(comp_ages),
            "subjects_with_stale_comps": stale_comp_subjects,
        },
        "freshness": {
            "median_days_since_computed": _med(computed_ages),
            "max_days_since_computed": max(computed_ages) if computed_ages else None,
            "never_computed": total - len(computed_ages),
        },
        "inputs_missing": {
            "floor_area": missing_floor_area,
            "floor_area_pct": _pct(missing_floor_area, total),
            "land_size": missing_land_size,
            "land_size_pct": _pct(missing_land_size, total),
        },
        "integrity": {
            "insufficient_data_but_valued": contra_insufficient_but_valued,
            "valued_without_range": contra_valued_no_range,
            "directional_but_figure_present": contra_directional_with_figure,
            "directional_flags_disagree": directional_disagreement,
        },
    }


def collect():
    now = datetime.now(timezone.utc)
    db = get_client()["Gold_Coast"]
    existing = set(db.list_collection_names())

    per_suburb, missing_collections = {}, []
    for s in SUBURBS:
        if s not in existing:
            # Rule 8 in spirit: a collection we cannot find is reported as such, never
            # silently folded into the totals as a zero.
            missing_collections.append(s)
            continue
        per_suburb[s] = collect_suburb(db[s], now)

    live = [v for v in per_suburb.values() if v.get("total_for_sale")]
    total = sum(v["total_for_sale"] for v in live)
    valued = sum(v["valued"] for v in live)
    exclusion = Counter()
    integrity = Counter()
    for v in live:
        exclusion.update(v["exclusion_reasons"])
        integrity.update(v["integrity"])

    return {
        "_id": "latest",
        "generated_at": now,
        "suburbs": SUBURBS,
        "missing_collections": missing_collections,
        "book": {
            "total_for_sale": total,
            "valued": valued,
            "unvalued": total - valued,
            "coverage_pct": _pct(valued, total),
            "unvalued_pct": _pct(total - valued, total),
        },
        "exclusion_reasons_all": dict(exclusion.most_common()),
        "integrity_all": dict(integrity),
        "per_suburb": per_suburb,
    }


def render(doc):
    b = doc["book"]
    print(f"valuation_signal: {b['valued']}/{b['total_for_sale']} of the live for-sale book "
          f"carries a reconciled valuation ({b['coverage_pct']}%) — "
          f"{b['unvalued']} unvalued ({b['unvalued_pct']}%)")
    if doc["missing_collections"]:
        print(f"  ⚠ collections not found: {', '.join(doc['missing_collections'])}")
    for s, v in doc["per_suburb"].items():
        if not v.get("total_for_sale"):
            print(f"  [{s:16}] no live listings")
            continue
        cp = v["comp_pool"]
        print(f"  [{s:16}] {v['valued']:3}/{v['total_for_sale']:3} valued "
              f"({v['coverage_pct']:5}%) · envelope in/above/below "
              f"{v['envelope']['inside']}/{v['envelope']['above']}/{v['envelope']['below']}"
              f" · comps med {cp['median_comps_used']} (thin {cp['thin_pool_subjects']}, "
              f"zero {cp['zero_comp_subjects']}) · comp age med "
              f"{cp['median_comp_age_days']}d · computed med "
              f"{v['freshness']['median_days_since_computed']}d ago")
        if v["exclusion_reasons"]:
            top = ", ".join(f"{k} {n}" for k, n in list(v["exclusion_reasons"].items())[:4])
            print(f"                     why unvalued: {top}")
    if doc["exclusion_reasons_all"]:
        print("  exclusion reasons (all suburbs): "
              + ", ".join(f"{k} {n}" for k, n in doc["exclusion_reasons_all"].items()))
    bad = {k: n for k, n in doc["integrity_all"].items() if n}
    print("  integrity contradictions: " + (", ".join(f"{k} {n}" for k, n in bad.items())
                                            if bad else "none"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    doc = collect()
    render(doc)

    if args.dry_run:
        return 0

    sm = get_client()["system_monitor"]
    sm["rl_valuation_signal"].replace_one({"_id": "latest"}, doc, upsert=True)
    hist = dict(doc)
    hist.pop("_id", None)
    sm["rl_valuation_signal"].insert_one(hist)

    # ── Rule 7b: assert an OUTCOME, not merely that nothing threw. ────────────────────
    # The zero-output path is real and specific here: this sensor reads ONE database, and
    # every metric it reports is a share of `total_for_sale`. If that count is zero the
    # script still completes perfectly happily and writes a document reading "0 unvalued,
    # coverage None" — which renders as a clean bill of health for a book that has simply
    # vanished. There are always live listings in these three suburbs (212 on 2026-08-13);
    # zero means the scrape died or the collection names moved, NOT that the market emptied.
    b = doc["book"]
    problems = []
    if b["total_for_sale"] == 0:
        problems.append("0 live for-sale listings across all three suburbs — the scrape or "
                        "the collection names are broken, the market did not empty")
    if doc["missing_collections"]:
        problems.append("collections not found: " + ", ".join(doc["missing_collections"]))
    if b["total_for_sale"] and b["valued"] == 0:
        problems.append(f"{b['total_for_sale']} live listings and NOT ONE carries a "
                        f"valuation — precompute_valuations has stopped writing")

    status = "error" if problems else "success"
    detail = ("; ".join(problems) if problems else
              f"{b['valued']}/{b['total_for_sale']} valued ({b['coverage_pct']}%), "
              f"{b['unvalued']} unvalued")
    try:
        from job_status import record_job_result
        record_job_result(
            "rl_valuation_signal", status,
            # Weekly, matching weekly_cycle.sh valuation. 200h stale window so a cycle that
            # runs a few hours late does not flag, but a missed week does.
            cadence_hours=168, stale_hours=200,
            title="Valuation — product-quality sensor (is the number any good?)",
            detail=detail,
            coverage_pct=b["coverage_pct"],
            unvalued=b["unvalued"],
        )
    except Exception as e:
        print(f"(job_status record failed: {e})")

    if problems:
        raise RuntimeError(detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())

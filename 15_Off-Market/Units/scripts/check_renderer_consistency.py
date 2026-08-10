#!/usr/bin/env python3
"""check_renderer_consistency.py — the two renderers must agree on every fact.

WHY THIS EXISTS
---------------
`render_unit_page.py` (HTML) consumes `unit_page_data.assemble()`.
`render_unit_report.py` (markdown) still assembles its own — it was written first.

That is one concept with two implementations, which is the single most common defect
in this codebase and the one that produced almost every bug found during this project:
`_toFullRes` duplicated, the SERP hook read at two shapes, the unit-address test written
three times in three languages, the effective-address chain written three ways, the
partial-quarter exclusion applied to the headline but not the deflator.

Refactoring the markdown renderer onto the shared layer is the right fix and is TODO.
Until then this check makes drift LOUD rather than silent: it renders both for the same
address and asserts the figures a reader would compare actually match.

⚠ Run this after touching either renderer or the data layer. A silent divergence here
means one surface is telling Will something the other is not.

    python3 check_renderer_consistency.py --slugs a b c
    echo $?      # non-zero if any fact disagrees
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from unit_page_data import assemble          # noqa: E402

REPORTS = HERE.parent / "artifacts" / "unit_reports"
PAGES = HERE.parent.parent / "Concepts" / "Unit_Page_Prototype"


def nums(text):
    """Every dollar figure and percentage a reader could compare."""
    return set(re.findall(r"\$[\d,]{4,}", text)) | set(re.findall(r"\b\d+(?:\.\d+)?%", text))


def check(slug):
    """Compare the FACTS, not the prose — the two media legitimately differ in wording."""
    d = assemble(slug=slug)
    problems = []

    md_p, html_p = REPORTS / f"{slug}.md", PAGES / f"{slug}.html"
    if not md_p.exists() or not html_p.exists():
        return [f"{slug}: missing {'markdown' if not md_p.exists() else 'html'} render "
                f"— cannot compare"]

    md, page = md_p.read_text(), html_p.read_text()
    val, mkt = d["valuation"], d["market"]

    def present(hay, needle, where):
        if needle and needle not in hay:
            problems.append(f"{slug}: {where} missing {needle!r}")

    # The valuation is the figure a reader would carry between the two.
    if val.get("method") == "same_complex_comparables":
        for label, v in (("point", val["point"]), ("low", val["low"]), ("high", val["high"])):
            # Both renderers round to millions above $1M, so compare the raw dollars
            # only where they render raw.
            raw = f"${v:,.0f}"
            if raw in md and raw not in page:
                problems.append(f"{slug}: {label} {raw} in markdown but not in the page")
            if raw in page and raw not in md:
                problems.append(f"{slug}: {label} {raw} in the page but not in markdown")
    else:
        for name, hay in (("markdown", md), ("page", page)):
            if "not going to put a figure" not in hay:
                problems.append(f"{slug}: {name} does not carry the refusal, "
                                f"but the method declined ({val.get('decline_reason')})")

    # Market figures must agree — this is the exact class of thing that went wrong live.
    if mkt.get("latest_rolling_median"):
        present(md, f"${mkt['latest_rolling_median']:,.0f}", "markdown market")
        present(page, f"${mkt['latest_rolling_median']:,.0f}", "page market")

    # Scheme size: the cadastre-vs-our-count bug rendered "2 lots" for a 53-home block.
    if d["scheme_size"]:
        for name, hay in (("markdown", md), ("page", page)):
            if str(d["scheme_size"]) not in hay:
                problems.append(f"{name} does not state scheme size {d['scheme_size']} for {slug}")

    # Neither surface may carry house-market language.
    for name, hay in (("markdown", md), ("page", page)):
        for bad in ("median house price", "houses for sale in", "backyard"):
            if bad in hay:
                problems.append(f"{slug}: {name} contains house language {bad!r}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slugs", nargs="+", required=True)
    args = ap.parse_args()
    allp = []
    for s in args.slugs:
        try:
            p = check(s)
        except Exception as ex:
            p = [f"{s}: check raised {type(ex).__name__}: {ex}"]
        allp += p
        print(f"  {s:44s} {'OK' if not p else f'{len(p)} PROBLEM(S)'}")
    if allp:
        print("\n  DRIFT DETECTED:")
        for p in allp:
            print(f"    - {p}")
        return 1
    print(f"\n  {len(args.slugs)} address(es) consistent across both renderers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

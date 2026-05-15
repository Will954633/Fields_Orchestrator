#!/usr/bin/env python3
"""V4-native appraisal generator.

Produces a complete 19-page V4-format PDF for any subject_id, using the
appraisal template system (Phase A/B/C). Parallels the legacy
`generate_appraisal_report.py` (11-page V2-format) but uses
`09_Appraisals/Version_Four/preview.html` as the base layout, splicing
template-rendered sections in place of hardcoded subject content.

USAGE
    python3 scripts/generate_appraisal_v4.py --subject-id <ObjectId>
    python3 scripts/generate_appraisal_v4.py --pipeline-id <ObjectId>
    python3 scripts/generate_appraisal_v4.py --pipeline-id <ObjectId> --pdf

WHAT IT REPLACES IN preview.html
    - Page 01 (cover)
    - Page 05 (§01 right)
    - Page 07 (§02 right)
    - Page 09 (§03 right)
    - Page 13 (§04 right)
    - Page 15 (§05 right)
    - Page 17 (§06 right)

EVERYTHING ELSE (left thesis pages, philosophy page, receipts page,
recommendation pages, campaign plan) currently inherits the 13TC content
already in preview.html. Those pages are part of Phase D scope —
templatizing the receipts comp-by-comp and the recommendation/campaign
sections.

The HTML output is always written. The PDF is rendered via headless
chromium if `--pdf` (default) is set.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bson import ObjectId  # type: ignore
from shared.db import get_client  # type: ignore
from scripts.appraisal_template import render  # type: ignore


V4_DIR = REPO_ROOT / "09_Appraisals" / "Version_Four"
TEMPLATE_FILE = V4_DIR / "preview.html"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "appraisals_v4"


# Splice points — start/end markers for each section in preview.html.
# Splicer replaces from the divider above `start_marker` up to (and
# including the divider above) `end_marker`.
# Markers reflect preview.html as of 2026-05-15 (after Phase B+C inserts).
SPLICE_POINTS = {
    "cover": (
        "<!-- PAGE 01 — OUTER COVER",
        "<!-- PAGE 02 — INSIDE FRONT COVER",
    ),
    "s01_right": (
        "<!-- PAGE 05 — SECTION 01 RIGHT",
        "<!-- PAGE 04 — SPREAD 02 LEFT",
    ),
    "s02_right": (
        "<!-- PAGE 07 — SECTION 02 RIGHT",
        "<!-- PAGE 06 — SPREAD 03 LEFT",
    ),
    "s03_right": (
        "<!-- PAGE 09 — SECTION 03 RIGHT",
        "<!-- PAGE 10 — SPREAD 03 RECEIPTS",
    ),
    "s04_right": (
        "<!-- PAGE 09 — SPREAD 04 RIGHT",
        "<!-- PAGE 10 — SPREAD 05 LEFT",
    ),
    "s05_right": (
        "<!-- PAGE 11 — SPREAD 05 RIGHT",
        "<!-- PAGE 12 — SPREAD 06 LEFT",
    ),
    "s06_right": (
        "<!-- PAGE 13 — SPREAD 06 RIGHT",
        "<!-- PAGE 17 — RECOMMENDATION",
    ),
}


def splice(text: str, key: str, new_block: str) -> str:
    """Replace the section block bounded by SPLICE_POINTS[key] markers."""
    start_marker, end_marker = SPLICE_POINTS[key]
    start_idx = text.find(start_marker)
    end_idx = text.find(end_marker)
    if start_idx < 0 or end_idx < 0 or end_idx <= start_idx:
        raise ValueError(
            f"Splice markers not found for '{key}'. "
            f"start='{start_marker}' (found={start_idx >= 0}), "
            f"end='{end_marker}' (found={end_idx >= 0}). "
            f"Preview template may have drifted."
        )
    above_start = text.rfind("<!-- ====", 0, start_idx)
    above_end = text.rfind("<!-- ====", 0, end_idx)
    return text[:above_start] + new_block + "\n\n" + text[above_end:]


def resolve_pipeline(pipeline_id: str) -> dict:
    """Fetch the appraisal_pipeline record."""
    sm = get_client()["system_monitor"]
    doc = sm.appraisal_pipeline.find_one({"_id": ObjectId(pipeline_id)})
    if not doc:
        raise LookupError(f"appraisal_pipeline {pipeline_id} not found")
    return doc


def render_appraisal(
    subject_id: str,
    pipeline_record: dict | None = None,
    output_basename: str | None = None,
    render_pdf: bool = True,
    open_pdf: bool = False,
) -> dict:
    """Render the full V4-format appraisal HTML and (optionally) PDF.

    Returns a dict with keys: html_path, pdf_path (or None), pipeline_id,
    subject_id, sections_rendered.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pipeline_record = pipeline_record or {}
    overrides_all = pipeline_record.get if pipeline_record else (lambda *_: None)

    # Pull section-specific editorial overrides off the pipeline record
    def get_overrides(section_key: str) -> dict:
        field = f"section_{section_key}_editorial_overrides"
        return pipeline_record.get(field, {}) if pipeline_record else {}

    # Section render — each returns the HTML block
    sections_rendered = []
    cover_html = render.render_section_00_cover_html(
        subject_id,
        editorial_overrides=get_overrides("00_cover"),
        hero_image_src=pipeline_record.get("cover_hero_image_src"),
        prepared_for=pipeline_record.get("name") or "the Owner",
        date_override=pipeline_record.get("cover_date_override"),
        write_substantiation=True,
    )
    sections_rendered.append("00_cover")

    s01 = render.render_section_01_right_html(
        subject_id,
        highlight_key=pipeline_record.get("highlight_chosen_key"),
        editorial_overrides=get_overrides("01_right"),
        satellite_image_src=pipeline_record.get("satellite_image_src"),
        write_substantiation=True,
    )
    sections_rendered.append("01_right")

    # Pull valuation midpoint for §02 willingness-to-pay
    val_mid = None
    db = get_client()["Gold_Coast"]
    suburb_key = (pipeline_record.get("suburb_key")
                  or (pipeline_record.get("suburb") or "").lower().replace(" ", "_"))
    if suburb_key:
        prop = db[suburb_key].find_one({"_id": ObjectId(subject_id)})
        if prop:
            val_mid = ((prop.get("valuation_data") or {}).get("confidence") or {}).get("reconciled_valuation")

    s02 = render.render_section_02_right_html(
        subject_id, valuation_mid=val_mid,
        editorial_overrides=get_overrides("02_right"), write_substantiation=True,
    )
    sections_rendered.append("02_right")

    s03 = render.render_section_03_right_html(
        subject_id,
        editorial_overrides=get_overrides("03_right"), write_substantiation=True,
    )
    sections_rendered.append("03_right")

    s04 = render.render_section_04_right_html(
        subject_id,
        editorial_overrides=get_overrides("04_right"), write_substantiation=True,
    )
    sections_rendered.append("04_right")

    s05 = render.render_section_05_right_html(
        subject_id,
        editorial_overrides=get_overrides("05_right"), write_substantiation=True,
    )
    sections_rendered.append("05_right")

    s06 = render.render_section_06_right_html(
        subject_id,
        editorial_overrides=get_overrides("06_right"), write_substantiation=True,
    )
    sections_rendered.append("06_right")

    # Load template + splice
    text = TEMPLATE_FILE.read_text()
    text = splice(text, "cover", cover_html)
    text = splice(text, "s01_right", s01)
    text = splice(text, "s02_right", s02)
    text = splice(text, "s03_right", s03)
    text = splice(text, "s04_right", s04)
    text = splice(text, "s05_right", s05)
    text = splice(text, "s06_right", s06)

    # Write HTML
    basename = output_basename or f"{subject_id}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    html_path = OUTPUT_DIR / f"{basename}.html"
    html_path.write_text(text)

    # Copy assets next to the HTML so file:// loading works
    assets_dst = OUTPUT_DIR / "assets"
    if not assets_dst.exists():
        shutil.copytree(V4_DIR / "assets", assets_dst)

    # Render PDF
    pdf_path: Path | None = None
    if render_pdf:
        pdf_path = OUTPUT_DIR / f"{basename}.pdf"
        proc = subprocess.run([
            "google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
            "--no-pdf-header-footer", "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            f"file://{html_path}",
        ], capture_output=True, text=True, timeout=180)
        if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
            raise RuntimeError(f"PDF render failed: {proc.stderr[-500:]}")

    return {
        "html_path": str(html_path),
        "pdf_path": str(pdf_path) if pdf_path else None,
        "subject_id": subject_id,
        "pipeline_id": str(pipeline_record.get("_id")) if pipeline_record else None,
        "sections_rendered": sections_rendered,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--subject-id", help="Subject property ObjectId (Gold_Coast.<suburb>._id)")
    g.add_argument("--pipeline-id", help="Appraisal pipeline ObjectId (system_monitor.appraisal_pipeline._id)")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF render, only emit HTML")
    parser.add_argument("--output-basename", help="Override basename for output files")
    parser.add_argument("--update-pipeline", action="store_true",
                        help="Save report_path on the appraisal_pipeline record")
    args = parser.parse_args()

    if args.pipeline_id:
        pipe = resolve_pipeline(args.pipeline_id)
        subject_id = pipe.get("subject_property_id")
        if not subject_id:
            raise SystemExit(
                f"Pipeline {args.pipeline_id} has no subject_property_id. "
                f"Run the bridge sync with --refresh first."
            )
    else:
        subject_id = args.subject_id
        pipe = None

    result = render_appraisal(
        subject_id,
        pipeline_record=pipe,
        output_basename=args.output_basename,
        render_pdf=not args.no_pdf,
    )

    print(f"\n✓ V4 appraisal rendered for subject {subject_id}")
    print(f"  HTML: {result['html_path']}")
    if result["pdf_path"]:
        print(f"  PDF:  {result['pdf_path']}")
    print(f"  Sections: {', '.join(result['sections_rendered'])}")

    if args.update_pipeline and pipe and result["pdf_path"]:
        sm = get_client()["system_monitor"]
        sm.appraisal_pipeline.update_one(
            {"_id": pipe["_id"]},
            {"$set": {
                "report_path_v4": result["pdf_path"],
                "report_html_v4": result["html_path"],
                "report_rendered_at_v4": datetime.now(timezone.utc),
                "report_sections_rendered": result["sections_rendered"],
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        print(f"  Pipeline record updated: {pipe['_id']}")


if __name__ == "__main__":
    main()

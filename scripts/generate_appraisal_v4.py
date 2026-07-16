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

import json

from bson import ObjectId  # type: ignore
from shared.db import get_client  # type: ignore
from shared.domain_urls import to_bucket_api_url  # type: ignore
from scripts.appraisal_template import render, layout_rules  # type: ignore


V4_DIR = REPO_ROOT / "09_Appraisals" / "Version_Four"
TEMPLATE_FILE = V4_DIR / "preview.html"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "appraisals_v4"

# DPI used to rasterise the cover page during the print-safe flatten step.
# 300 keeps the cover headline/QR crisp at A4 print size.
COVER_FLATTEN_DPI = 300


def flatten_cover_for_print(pdf_path: Path, dpi: int = COVER_FLATTEN_DPI) -> None:
    """Rasterise page 1 (the cover) to a flat, opaque DeviceRGB image and
    write it back in place, leaving all content pages as vector text.

    Why: the cover is the only page with live transparency composited over a
    photo — the darkening gradient over the hero, plus the QR card shadow.
    Officeworks' online print pipeline flattens transparency and converts
    RGB->CMYK on upload; that recomputation over the hero swings its blues
    toward magenta ("pink haze"). Content-page photos have nothing overlaid,
    so they are untouched. Baking the cover to a flat image removes the
    transparency trigger while keeping the rest of the booklet selectable.
    See logs/fix-history for the 2026-07-16 Officeworks pink-hero diagnosis.
    """
    import fitz  # PyMuPDF — lazy import so --no-pdf runs need no dep

    doc = fitz.open(pdf_path)
    try:
        if doc.page_count == 0:
            return
        cover = doc[0]
        rect = cover.rect
        # Render the composited cover to an opaque RGB raster (transparency baked in).
        pix = cover.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)

        out = fitz.open()
        new_cover = out.new_page(width=rect.width, height=rect.height)
        new_cover.insert_image(rect, pixmap=pix)
        if doc.page_count > 1:
            out.insert_pdf(doc, from_page=1, to_page=doc.page_count - 1)

        tmp = pdf_path.with_suffix(".flat.tmp.pdf")
        out.save(tmp, deflate=True, garbage=4)
        out.close()
    finally:
        doc.close()
    tmp.replace(pdf_path)


# Splice points — start/end markers for each section in preview.html.
# Splicer replaces from the divider above `start_marker` up to (and
# including the divider above) `end_marker`.
# Markers reflect preview.html as of 2026-05-15 (after Phase B+C inserts).
SPLICE_POINTS = {
    "cover": (
        "<!-- PAGE 01 — OUTER COVER",
        "<!-- PAGE 02 — INSIDE FRONT COVER",
    ),
    "s01_left": (
        "<!-- PAGE 04 — Locked from V3: Section 01 LEFT",
        "<!-- PAGE 05 — SECTION 01 RIGHT",
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
        "<!-- PAGE 10 — SECTION 03 RECEIPTS",  # after s03_receipts splice, marker rewrites
    ),
    "s03_receipts": (
        "<!-- PAGE 10 — SPREAD 03 RECEIPTS",
        "<!-- PAGE 11 — RECOMMENDATION",  # after rec_p11 splice the marker rewrites this
    ),
    "rec_p11": (
        "<!-- PAGE 11 — PRICING RECOMMENDATION",
        "<!-- PAGE 12 — SPREAD 04 LEFT",
    ),
    "rec_p18": (
        "<!-- PAGE 17 — RECOMMENDATION",
        "<!-- PAGE 18 — THE 28-DAY PLAN",
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
        "<!-- PAGE 18 — RECOMMENDATION",
    ),
}


def _suburb_key_for(subject_id: str) -> str | None:
    """Find which suburb collection holds the subject doc by scanning the
    target catchment. Faster than listing all collections."""
    db = get_client()["Gold_Coast"]
    for s in ["merrimac","robina","varsity_lakes","burleigh_waters"]:
        if db[s].find_one({"_id": ObjectId(subject_id)}, {"_id": 1}):
            return s
    return None


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

    # Drain any layout-rules audit records from a previous run in this process
    # so the audit file only reflects this render.
    layout_rules.clear_records()

    # QR code — encodes the attributable scan-redirect (a homeowner scan logs
    # to PostHog + CRM + Brain 2 physical attribution, then 302s to the live
    # mini-site). Falls back to the direct mini-site URL when no tracking_id is
    # on the pipeline record yet. Rendered onto both the front and back cover.
    subject_doc_for_qr = get_client()["Gold_Coast"]
    _sk = (pipeline_record.get("suburb_key")
           or (pipeline_record.get("suburb") or "").lower().replace(" ", "_")) if pipeline_record else None
    _subj_for_qr = subject_doc_for_qr[_sk].find_one({"_id": ObjectId(subject_id)}) if _sk else {}
    scan_url, minisite_url = render._minisite_urls(pipeline_record, _subj_for_qr or {})
    qr_svg = render._qr_data_uri(scan_url)

    # Section render — each returns the HTML block
    sections_rendered = []
    cover_html = render.render_section_00_cover_html(
        subject_id,
        editorial_overrides=get_overrides("00_cover"),
        hero_image_src=to_bucket_api_url(pipeline_record.get("cover_hero_image_src")) if pipeline_record.get("cover_hero_image_src") else None,
        prepared_for=pipeline_record.get("name") or "the Owner",
        date_override=pipeline_record.get("cover_date_override"),
        write_substantiation=True,
        qr_svg=qr_svg,
    )
    sections_rendered.append("00_cover")

    s01_left = render.render_section_01_left_html(
        subject_id,
        editorial_overrides=get_overrides("01_left"),
        write_substantiation=True,
    )
    sections_rendered.append("01_left")

    s01 = render.render_section_01_right_html(
        subject_id,
        highlight_key=pipeline_record.get("highlight_chosen_key"),
        editorial_overrides=get_overrides("01_right"),
        satellite_image_src=pipeline_record.get("satellite_image_src"),
        write_substantiation=True,
        report_slug=pipeline_record.get("property_reports_slug"),
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
        pipeline_record=pipeline_record,
    )
    sections_rendered.append("03_right")

    s03r = render.render_section_03_receipts_html(
        subject_id,
        editorial_overrides=get_overrides("03_receipts"), write_substantiation=True,
    )
    sections_rendered.append("03_receipts")

    rec_p11 = render.render_section_recommendation_html(
        subject_id, page_number=11, pipeline_record=pipeline_record, write_substantiation=True,
    )
    sections_rendered.append("recommendation_p11")
    rec_p18 = render.render_section_recommendation_html(
        subject_id, page_number=18, pipeline_record=pipeline_record, write_substantiation=True,
    )
    sections_rendered.append("recommendation_p18")

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
    # Splice bottom-up so earlier-page splices don't invalidate later-page
    # markers. Each splice replaces text between markers — if we replaced
    # PAGE 17's marker before splicing PAGE 13's section (which uses PAGE 17
    # as its end-boundary), PAGE 13's splice would fail.
    text = splice(text, "rec_p18", rec_p18)
    text = splice(text, "s06_right", s06)
    text = splice(text, "s05_right", s05)
    text = splice(text, "s04_right", s04)
    text = splice(text, "rec_p11", rec_p11)
    text = splice(text, "s03_receipts", s03r)
    text = splice(text, "s03_right", s03)
    text = splice(text, "s02_right", s02)
    text = splice(text, "s01_right", s01)
    text = splice(text, "s01_left", s01_left)
    text = splice(text, "cover", cover_html)

    # Post-process — replace hardcoded subject references in static thesis pages
    # (page 2 philosophy, page 3 TOC, §0X left close lines, page headers).
    # Cleaner than per-page templating because the static-thesis copy is otherwise
    # generic and reusable across all subjects.
    db = get_client()["Gold_Coast"]
    suburb_key = (pipeline_record.get("suburb_key") if pipeline_record
                  else None) or _suburb_key_for(subject_id)
    subject_doc = db[suburb_key].find_one({"_id": ObjectId(subject_id)}) if suburb_key else None
    if subject_doc:
        # Street address — cadastral / analyse-your-home records have no
        # `street_address`; they carry a full `address`
        # ("18 Silvabank Drive, Varsity Lakes QLD 4227") or `complete_address`
        # (ALL CAPS). Derive the street portion (before the first comma) so the
        # 13TC → subject substitution below actually fires for them. Without
        # this the substitution silently no-ops and "13 Terrace Court" leaks
        # onto every inherited thesis/recommendation page.
        raw_addr = subject_doc.get("street_address") or ""
        if not raw_addr:
            full_addr = subject_doc.get("address") or subject_doc.get("complete_address") or ""
            street = full_addr.split(",")[0].strip()
            if "," not in full_addr and street:
                # complete_address has no commas — cut before the suburb token
                loc = (subject_doc.get("LOCALITY") or "").strip()
                if loc and loc.upper() in street.upper():
                    street = street[: street.upper().index(loc.upper())].strip()
            raw_addr = street
        title_addr = raw_addr.title() if raw_addr.isupper() else raw_addr
        upper_addr = (raw_addr or "").upper() if raw_addr else None
        # Suburb — prefer the pipeline record (clean-cased), then the doc's
        # `suburb`, then the cadastral `LOCALITY` (ALL CAPS).
        suburb_name = ((pipeline_record or {}).get("suburb")
                       or subject_doc.get("suburb")
                       or subject_doc.get("LOCALITY") or "")
        prepared_for_name = (pipeline_record or {}).get("name") or "the Owner"
        import re
        # Subject address substitution (only where original was hardcoded "13 Terrace Court")
        if title_addr and title_addr != "13 Terrace Court":
            text = text.replace("13 Terrace Court", title_addr)
            text = text.replace("13 TERRACE COURT", upper_addr or title_addr.upper())
        # Prepared-for name substitution — handle:
        # - "Prepared for Dee" (cover band)
        # - <span class="name">Dee</span> (inside-cover)
        # - "and for Dee" (page 19 closing sign-off — drop the clause entirely
        #   when there is no real name on the pipeline record, otherwise swap).
        if prepared_for_name:
            text = text.replace("Prepared for Dee", f"Prepared for {prepared_for_name}")
            text = text.replace('<span class="name">Dee</span>', f'<span class="name">{prepared_for_name}</span>')
            if prepared_for_name == "the Owner":
                text = text.replace(" and for Dee", "")
            else:
                text = text.replace("for Dee", f"for {prepared_for_name}")
        # Suburb substitution — handle multiple patterns:
        #   "· Merrimac" (thesis eyebrow) → "· {suburb}"
        #   "<street_addr><br>\n      Merrimac, QLD 4226" (inside cover) → use subject's actual suburb+postcode
        if suburb_name and suburb_name.lower() != "merrimac":
            sub_title = suburb_name.title() if suburb_name.isupper() else suburb_name
            text = text.replace("· Merrimac", f"· {sub_title}")
            # Inside-cover suburb block — anchored to the subject street address
            postcode = (subject_doc.get("postcode") or subject_doc.get("display_postcode")
                        or subject_doc.get("POSTCODE") or "")
            if title_addr and postcode:
                text = re.sub(
                    r'(' + re.escape(title_addr) + r'<br>\s*)Merrimac, QLD 4226',
                    rf'\g<1>{sub_title}, QLD {postcode}',
                    text,
                )

    # Back cover + even-page booklet padding. Count printed page units (front
    # cover + content pages; `class="page"`/`class="cover"` match exactly, not
    # `page-pad`/`cover-image`). The booklet must end on the back cover with an
    # even total, so insert one blank spacer before it when adding it would make
    # the count odd.
    page_units = len(re.findall(r'class="(?:page|cover)"', text))
    back_cover = render.render_back_cover_html(
        subject_id, qr_svg=qr_svg,
        prepared_for=(pipeline_record or {}).get("name"),
    )
    tail = ""
    if (page_units + 1) % 2 == 1:  # content even -> back cover alone would make it odd
        tail += ('\n<div class="page" data-section="spacer" '
                 'style="background:#ffffff; page-break-before:always;"></div>\n')
        page_units += 1
    tail += "\n" + back_cover + "\n"
    text = text.replace("</body>", tail + "</body>", 1)
    sections_rendered.append("back_cover")

    # Write HTML
    basename = output_basename or f"{subject_id}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    html_path = OUTPUT_DIR / f"{basename}.html"
    html_path.write_text(text)

    # Copy assets next to the HTML so file:// loading works.
    # `dirs_exist_ok=True` so re-renders refresh new assets that may have
    # been added since the last run.
    assets_dst = OUTPUT_DIR / "assets"
    shutil.copytree(V4_DIR / "assets", assets_dst, dirs_exist_ok=True)

    # Per-subject photos: auto-fetch from live sources, only fall back to
    # generic placeholder if every option fails. Tracks which source was used
    # so the audit + console can warn loudly when a fallback is in play —
    # critical for production homeowner reports where the wrong photo on a
    # mailed PDF is unacceptable.
    fallback_hero = V4_DIR / "assets" / "img" / "cover_hero_13_terrace_court.jpg"
    fallback_sat = V4_DIR / "assets" / "satellite_13_terrace_court.png"
    expected_hero = OUTPUT_DIR / "assets" / "img" / f"cover_hero_{subject_id}.jpg"
    expected_sat = OUTPUT_DIR / "assets" / f"satellite_{subject_id}.png"
    expected_hero.parent.mkdir(parents=True, exist_ok=True)
    expected_sat.parent.mkdir(parents=True, exist_ok=True)

    hero_source = None     # "pipeline" | "auto_apr01" | "auto_scraped" | "fallback" | "missing"
    satellite_source = None  # "pipeline" | "annotated" | "satellite_analysis" | "auto_static_maps" | "fallback" | "missing"

    # Look up the subject doc up-front — used by both hero and satellite blocks.
    from shared.db import get_client as _gc
    _subj = None
    if suburb_key:
        _subj = _gc()["Gold_Coast"][suburb_key].find_one({"_id": ObjectId(subject_id)})

    if (pipeline_record or {}).get("cover_hero_image_src"):
        hero_source = "pipeline"  # respected — pipeline supplied an explicit path
        # When the analyst picked a hero in the ops dashboard, download it into
        # expected_hero so the PDF render finds it locally (file:// loading).
        # Domain CDN URLs are rewritten to bucket-api (full-res, no signed-hash
        # thumbnail trap) — same fix as FP-001 for floor plans.
        hero_url = to_bucket_api_url(pipeline_record["cover_hero_image_src"])
        if hero_url.startswith("http") and "blob.core.windows.net" not in hero_url:
            try:
                import urllib.request
                req = urllib.request.Request(hero_url, headers={"User-Agent": "Fields-Appraisal/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                if len(data) > 2000:
                    expected_hero.write_bytes(data)
            except Exception as exc:
                print(f"  [WARN] pipeline cover_hero download failed: {exc} — falling back to existing asset")
    else:
        # Try Domain-CDN URLs from apr01-recovered first (live), then scraped_data
        # (often dead Azure URLs but worth trying). Skip dead Azure blob domains.
        candidates = []
        if _subj:
            for source_key, store_key in [
                ("scraped_data_apr01_recovered", "auto_apr01"),
                ("scraped_data", "auto_scraped"),
            ]:
                imgs = (_subj.get(source_key) or {}).get("images") or []
                for img in imgs[:8]:  # try first 8 images max
                    url = img.get("url") if isinstance(img, dict) else img
                    if not url or "blob.core.windows.net" in url:
                        continue
                    candidates.append((url, store_key))
        # Attempt download (overwrite any stale fallback file from previous run).
        # For each candidate try the bucket-api rewrite first (full-res, FP-001),
        # then the original URL — the rewrite mangles Domain URLs whose tail is a
        # nested absolute http://static.domain.com.au/... link (produces
        # `.../image/http:`), so the original must be tried as a fallback.
        if candidates:
            import urllib.request
            for url, kind in candidates:
                for try_url in dict.fromkeys([to_bucket_api_url(url), url]):
                    try:
                        req = urllib.request.Request(try_url, headers={"User-Agent": "Fields-Appraisal/1.0"})
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            data = resp.read()
                        if len(data) > 2000:  # sanity: not an error placeholder
                            expected_hero.write_bytes(data)
                            hero_source = kind
                            break
                    except Exception:
                        continue
                if hero_source:
                    break
        # Local on-disk subject images — survive after Domain CDN URLs expire
        # (a listing scraped months ago has 404 photos). For a homeowner
        # appraisal with no live listing photo, the Street View front is the
        # correct hero: it is the actual subject house. Cadastral photos are a
        # weaker fallback (sometimes an aerial), but a real image of the subject
        # still beats the generic 13TC placeholder.
        if not hero_source and suburb_key:
            local_candidates = [
                (Path(f"/data/blobs/property-images/for_sale/{suburb_key}/{subject_id}/street_view/front.jpg"),
                 "local_street_view"),
            ]
            cad_dir = (_subj or {}).get("cadastral_photos_dir")
            if cad_dir:
                for jpg in sorted(Path(cad_dir).glob("*.jpg")):
                    local_candidates.append((jpg, "local_cadastral"))
            for path, kind in local_candidates:
                try:
                    if path.exists() and path.stat().st_size > 2000:
                        shutil.copy(path, expected_hero)
                        hero_source = kind
                        break
                except Exception:
                    continue
        if not hero_source:
            # Auto-fetch failed — use the generic fallback so the PDF isn't broken,
            # but mark loudly that this is the wrong photo for the subject.
            if fallback_hero.exists():
                shutil.copy(fallback_hero, expected_hero)
                hero_source = "fallback"
            else:
                hero_source = "missing"

    # Satellite source priority:
    #   1. pipeline_record.satellite_image_src  — analyst override
    #   2. satellite_analysis.annotated_image_url — bounding boxes + Fields drop pin,
    #      produced by the inline_satellite resolver. This is the version that
    #      visibly demonstrates the analysis tech and matches what the seller
    #      mini-site renders. Use it whenever it's available.
    #   3. satellite_analysis.satellite_image_url — raw Google Maps tile from
    #      the inline_satellite resolver (or the nightly step 117 batch).
    #   4. Fresh Google Static Maps call — fallback when nothing is cached.
    #   5. Local fallback asset.
    if (pipeline_record or {}).get("satellite_image_src"):
        satellite_source = "pipeline"
    else:
        import os as _os
        _sa = (_subj or {}).get("satellite_analysis") or {}
        cached_url = _sa.get("annotated_image_url") or _sa.get("satellite_image_url")
        # Skip dead Azure URLs left over from the legacy blob account.
        if cached_url and "blob.core.windows.net" in cached_url:
            cached_url = None
        if cached_url:
            try:
                import urllib.request as _ur
                req = _ur.Request(cached_url, headers={"User-Agent": "Fields-Appraisal/1.0"})
                with _ur.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                if len(data) > 2000:
                    expected_sat.write_bytes(data)
                    satellite_source = "annotated" if _sa.get("annotated_image_url") else "satellite_analysis"
            except Exception as exc:
                print(f"  [WARN] cached satellite fetch failed ({cached_url[:80]}…): {exc}")

        # Fall back to a fresh Google Static Maps fetch only when nothing
        # cached worked. This is the path Will's old reports went through.
        if not satellite_source:
            lat = _subj.get("LATITUDE") if _subj else None
            lng = _subj.get("LONGITUDE") if _subj else None
            api_key = _os.environ.get("GOOGLE_MAPS_STATIC_API_KEY")
            if lat and lng and api_key:
                url = (
                    "https://maps.googleapis.com/maps/api/staticmap"
                    f"?center={lat},{lng}&zoom=19&size=640x640&maptype=satellite"
                    f"&markers=color:red%7C{lat},{lng}&key={api_key}"
                )
                try:
                    import urllib.request as _ur
                    with _ur.urlopen(url, timeout=15) as resp:
                        data = resp.read()
                    if len(data) > 2000:
                        expected_sat.write_bytes(data)
                        satellite_source = "auto_static_maps"
                except Exception:
                    pass
        if not satellite_source:
            if fallback_sat.exists():
                shutil.copy(fallback_sat, expected_sat)
                satellite_source = "fallback"
            else:
                satellite_source = "missing"

    # Drain layout-rules audit records collected during section renders and
    # write a structured audit alongside the HTML/PDF. Phase 1: warnings only
    # (no truncation, no compact-variant fallback). The audit lets us tune
    # SECTION_RULES against real subjects before turning on enforcement.
    audit_records = layout_rules.get_records()
    audit_path = OUTPUT_DIR / f"{basename}.audit.json"

    # Layer 2 — browser-based fit check + compact-variant cascade. The first
    # pass measures every `[data-section]` page in headless Chromium at A4
    # print dimensions. Any section flagged `overflow` has its `data-variant`
    # swapped from "standard" to "compact" (pure CSS — smaller fonts, tighter
    # padding) and the HTML is rewritten + re-measured. A second cascade level
    # (ultra_compact / continuation pages) is left for Phase 2.5 if needed.
    fit_report = None
    fit_check_script = REPO_ROOT / "scripts" / "appraisal_template" / "fit_check.js"
    fit_check_out = OUTPUT_DIR / f"{basename}.fit_check.json"
    variants_applied: dict[str, str] = {}
    fit_passes: list[dict] = []

    def _run_fit_check() -> dict | None:
        try:
            subprocess.run(
                ["node", str(fit_check_script), str(html_path), str(fit_check_out)],
                check=True, capture_output=True, text=True, timeout=90,
            )
            return json.loads(fit_check_out.read_text()) if fit_check_out.exists() else None
        except subprocess.CalledProcessError as exc:
            return {"error": f"fit_check failed: {exc.stderr[-400:]}"}
        except subprocess.TimeoutExpired:
            return {"error": "fit_check timeout"}

    if fit_check_script.exists():
        # Pass 1: measure standard render
        fit_report = _run_fit_check()
        fit_passes.append({"variant": "standard", "summary": (fit_report or {}).get("summary")})

        # Find sections needing compact treatment. Trigger on both "overflow"
        # (literal clip) and "tight" (content within 30px of page bottom — no
        # footer breathing room). Tight sections visually feel cramped even
        # though no clipping occurs, so they get compact treatment too.
        if fit_report and "sections" in fit_report:
            overflowing = [s["section_key"] for s in fit_report["sections"]
                           if s.get("status") in ("overflow", "tight")]
            if overflowing:
                current_html = html_path.read_text()
                for key in overflowing:
                    # The data-variant attribute is right after data-section on each .page div.
                    # We resolved the recommendation_p* keys via jinja so they're concrete here.
                    old_attr = f'data-section="{key}" data-variant="standard"'
                    new_attr = f'data-section="{key}" data-variant="compact"'
                    if old_attr in current_html:
                        current_html = current_html.replace(old_attr, new_attr, 1)
                        variants_applied[key] = "compact"
                html_path.write_text(current_html)

                # Pass 2: re-measure after compact swap
                fit_report = _run_fit_check()
                fit_passes.append({"variant": "compact", "summary": (fit_report or {}).get("summary"),
                                   "applied_to": list(variants_applied.keys())})

    audit_payload = {
        "subject_id": subject_id,
        "pipeline_id": str(pipeline_record.get("_id")) if pipeline_record else None,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "sections": [r.to_dict() for r in audit_records],
        "summary": {
            "sections_checked": len(audit_records),
            "soft_warnings": sum(r.n_warn for r in audit_records),
            "hard_failures": sum(r.n_fail for r in audit_records),
        },
        "fit_check": fit_report,
        "fit_passes": fit_passes,
        "variants_applied": variants_applied,
        "photo_sources": {
            "cover_hero": hero_source,
            "satellite": satellite_source,
        },
    }
    audit_path.write_text(json.dumps(audit_payload, indent=2))

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

        # Print-safe pass: flatten the cover so Officeworks / any CMYK RIP
        # can't shift the hero to pink via transparency flattening.
        try:
            flatten_cover_for_print(pdf_path)
        except Exception as exc:  # never fail generation over the print-safe pass
            print(f"WARN: cover flatten skipped ({exc})", file=sys.stderr)

    return {
        "html_path": str(html_path),
        "pdf_path": str(pdf_path) if pdf_path else None,
        "audit_path": str(audit_path),
        "audit_summary": audit_payload["summary"],
        "audit_records": audit_records,
        "fit_check": fit_report,
        "fit_passes": fit_passes,
        "variants_applied": variants_applied,
        "photo_sources": {"cover_hero": hero_source, "satellite": satellite_source},
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
    parser.add_argument("--strict-photos", action="store_true",
                        help="Exit non-zero if cover_hero or satellite fell back to the generic 13TC placeholder. Use this before printing/mailing.")
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

    # Ensure a tracking_id exists BEFORE the render so the cover/back QR encodes
    # the attributable scan-redirect (/track/scan/<id>) rather than the bare
    # mini-site URL. Also stamp the mini-site slug/url on the tracking record so
    # the /scan route knows where to redirect. Best-effort — a QR that falls
    # back to the direct URL is still fine.
    if pipe and args.update_pipeline and not pipe.get("tracking_id"):
        try:
            sys.path.insert(0, str(REPO_ROOT / "tracking-server"))
            from send_report import create_tracking_record  # type: ignore
            sm_pre = get_client()["system_monitor"]
            slug = pipe.get("property_reports_slug")
            tid = create_tracking_record(
                sm_pre,
                pipe.get("email") or "preview@fieldsestate.com.au",
                pipe.get("name") or "the Owner",
                pipe.get("address") or "Property",
                "(pending render)", subject_id, 0,
            )
            sm_pre["email_tracking"].update_one(
                {"tracking_id": tid},
                {"$set": {
                    "minisite_slug": slug,
                    "minisite_url": (f"https://fieldsestate.com.au/your-home/{slug}#home"
                                     if slug else None),
                    "source_channel": "physical_appraisal",
                }},
            )
            sm_pre.appraisal_pipeline.update_one(
                {"_id": pipe["_id"]}, {"$set": {"tracking_id": tid}})
            pipe["tracking_id"] = tid
            print(f"  Tracking ID minted (pre-render, for QR): {tid}")
        except Exception as exc:
            print(f"  [WARN] pre-render tracking mint failed: {exc} — QR will use direct URL")

    # When updating a pipeline record, mark it as in-progress before the
    # (potentially slow) render so the ops panel reflects current state.
    if args.update_pipeline and pipe:
        _now = datetime.now(timezone.utc)
        get_client()["system_monitor"]["appraisal_pipeline"].update_one(
            {"_id": pipe["_id"]},
            {
                "$set": {"stage": "report_generating", "updated_at": _now},
                "$push": {"stage_history": {"stage": "report_generating", "at": _now.isoformat()}},
            },
        )

    try:
        result = render_appraisal(
            subject_id,
            pipeline_record=pipe,
            output_basename=args.output_basename,
            render_pdf=not args.no_pdf,
        )
    except Exception as exc:
        if args.update_pipeline and pipe:
            _now = datetime.now(timezone.utc)
            get_client()["system_monitor"]["appraisal_pipeline"].update_one(
                {"_id": pipe["_id"]},
                {
                    "$set": {"stage": "error", "updated_at": _now,
                             "last_error": f"{type(exc).__name__}: {exc}"[:500]},
                    "$push": {"stage_history": {"stage": "error", "at": _now.isoformat()}},
                },
            )
            print(f"\n✗ Render failed — pipeline {pipe['_id']} → error: {exc}")
        raise

    print(f"\n✓ V4 appraisal rendered for subject {subject_id}")
    print(f"  HTML: {result['html_path']}")
    if result["pdf_path"]:
        print(f"  PDF:  {result['pdf_path']}")
    print(f"  Sections: {', '.join(result['sections_rendered'])}")

    ps = result.get("photo_sources") or {}
    hero_src = ps.get("cover_hero")
    sat_src = ps.get("satellite")
    hero_warn = "  ⚠  COVER HERO is GENERIC FALLBACK (not the subject's photo)" if hero_src == "fallback" else None
    sat_warn = "  ⚠  SATELLITE is GENERIC FALLBACK (not the subject's location)" if sat_src == "fallback" else None
    print(f"  Photos: cover_hero={hero_src} · satellite={sat_src}")
    if hero_warn: print(hero_warn)
    if sat_warn: print(sat_warn)

    summary = result["audit_summary"]
    print(
        f"  Audit: {summary['sections_checked']} sections checked · "
        f"{summary['hard_failures']} hard breaches · "
        f"{summary['soft_warnings']} soft warnings  →  {result['audit_path']}"
    )
    for record in result["audit_records"]:
        for msg in record.errors:
            print(f"    FAIL {msg}")
        for msg in record.warnings:
            print(f"    warn {msg}")

    fit = result.get("fit_check")
    variants = result.get("variants_applied") or {}
    if fit and "summary" in fit:
        fs = fit["summary"]
        passes = len(result.get("fit_passes") or [])
        print(
            f"  Fit-check: {fs['sections_measured']} pages measured · "
            f"{fs['overflows']} overflow · {fs['tight']} tight · "
            f"{fs.get('footer_misaligned', 0)} footer-misaligned · "
            f"{passes} pass{'es' if passes != 1 else ''}"
        )
        if variants:
            for key, variant in variants.items():
                print(f"    compact-variant applied to {key}")
        for s in fit["sections"]:
            if s["status"] == "overflow":
                print(f"    OVERFLOW  {s['section_key']}: content {s['scroll_height_px']}px > page {s['client_height_px']}px (+{s['overflow_px']}px)")
            elif s["status"] == "tight":
                print(f"    tight     {s['section_key']}: content {s['scroll_height_px']}px > page {s['client_height_px']}px (+{s['overflow_px']}px)")
        for m in (fit.get("footer_alignment") or {}).get("misaligned", []):
            print(f"    FOOTER-MISALIGNED  {m['section_key']} ({m['variant']}): "
                  f"footer at {m['footer_bottom_px']}px, expected {fit['footer_alignment']['expected_bottom_px']}px "
                  f"({m['drift_px']:+d}px drift)")
    elif fit and "error" in fit:
        print(f"  Fit-check: error — {fit['error']}")

    if args.update_pipeline and pipe and result["pdf_path"]:
        sm = get_client()["system_monitor"]
        now = datetime.now(timezone.utc)

        # Try to mint a tracking_id so the ops panel's "Preview Report (as client
        # will see it)" link works. Re-uses the same tracking module the V2
        # generator uses — falls back gracefully if the module is missing or
        # the subject's address can't be resolved.
        tracking_id = pipe.get("tracking_id")  # re-use if it already exists
        try:
            sys.path.insert(0, str(REPO_ROOT / "tracking-server"))
            from send_report import create_tracking_record, count_pdf_pages  # type: ignore
            addr = pipe.get("address") or "Property"
            client_name = pipe.get("name") or "the Owner"
            total_pages = count_pdf_pages(result["pdf_path"])
            if not tracking_id:
                tracking_id = create_tracking_record(
                    sm,
                    pipe.get("email") or "preview@fieldsestate.com.au",
                    client_name, addr, result["pdf_path"],
                    f"Your Property Appraisal — {addr}",
                    total_pages,
                )
                print(f"  Tracking ID minted: {tracking_id}")
            else:
                # On re-render, point the existing tracking record at the new
                # PDF — otherwise the Preview link serves stale page PNGs from
                # the original render before the analyst's tweaks.
                _slug = pipe.get("property_reports_slug")
                sm["email_tracking"].update_one(
                    {"tracking_id": tracking_id},
                    {"$set": {
                        "report_path": str(result["pdf_path"]),
                        "report_filename": Path(result["pdf_path"]).name,
                        "total_pages": total_pages,
                        # Backfill mini-site target so /track/scan/<id> can redirect
                        # (existing tracking records pre-date the QR feature).
                        "minisite_slug": _slug,
                        "minisite_url": (f"https://fieldsestate.com.au/your-home/{_slug}#home"
                                         if _slug else None),
                        "source_channel": "physical_appraisal",
                    }},
                )
                print(f"  Tracking record updated → {Path(result['pdf_path']).name}")
        except Exception as exc:
            print(f"  [WARN] tracking record update failed: {exc}")
            if not tracking_id:
                tracking_id = None

        # Stage advance + legacy field aliases so the ops panel sees the V4
        # output through the same fields it reads for V2 reports.
        set_fields = {
            "stage": "draft_ready",
            "report_path": result["pdf_path"],          # legacy field — panel reads this
            "report_path_v4": result["pdf_path"],
            "report_html_v4": result["html_path"],
            "report_rendered_at_v4": now,
            "report_sections_rendered": result["sections_rendered"],
            "report_audit_path": result.get("audit_path"),
            "report_photo_sources": result.get("photo_sources") or {},
            "report_variants_applied": result.get("variants_applied") or {},
            "updated_at": now,
        }
        if tracking_id:
            set_fields["tracking_id"] = tracking_id
        sm.appraisal_pipeline.update_one(
            {"_id": pipe["_id"]},
            {
                "$set": set_fields,
                "$push": {"stage_history": {"stage": "draft_ready", "at": now.isoformat()}},
            },
        )
        print(f"  Pipeline {pipe['_id']} → draft_ready")
        if tracking_id:
            print(f"  Preview: https://vm.fieldsestate.com.au/track/view/{tracking_id}")

    # Strict-photos enforcement — block production/postal rendering when
    # either the cover hero or satellite is the generic 13TC fallback. The
    # rendered files exist on disk so the operator can inspect, but the
    # exit code is non-zero so any wrapping script knows not to send.
    if args.strict_photos:
        bad = [k for k, v in (result.get("photo_sources") or {}).items()
               if v in ("fallback", "missing")]
        if bad:
            print(f"\n✗ STRICT-PHOTOS CHECK FAILED — {', '.join(bad)} used the generic fallback.", flush=True)
            print(f"  The rendered PDF is on disk for inspection but MUST NOT be sent to a homeowner.")
            print(f"  Resolve by: (a) adding the per-subject asset to assets/, OR")
            print(f"             (b) setting cover_hero_image_src / satellite_image_src on the pipeline_record, OR")
            print(f"             (c) ensuring the subject doc has live Domain CDN images / valid LATITUDE/LONGITUDE.")
            raise SystemExit(2)


if __name__ == "__main__":
    main()

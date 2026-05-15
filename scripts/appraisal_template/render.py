"""HTML/PDF rendering for the appraisal template system.

`render_section_01_right_html(subject_id)` produces the §01 right page as a
ready-to-insert HTML block. Callers (the V4 preview, the production
seller_report_v2 template, the ops dashboard preview, etc.) decide where to
splice it.

Editorial-override fields live on the appraisal_pipeline record for the
subject (or default to a deterministic auto-generated subhead). This keeps the
90/10 split clean: 90% from `data_pull.section_01_right()`, 10% optional
editorial overrides.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from jinja2 import Environment, BaseLoader, select_autoescape  # type: ignore

from scripts.appraisal_template import data_pull, dot_grid, pick_highlight, substantiation


SECTION_02_RIGHT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 07 — SECTION 02 RIGHT — Three buyers. One outbids.       -->
<!-- Live HTML, template-driven from                                  -->
<!-- scripts/appraisal_template/render.render_section_02_right_html() -->
<!-- ============================================================ -->
<div class="page">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 22 26" xmlns="http://www.w3.org/2000/svg">
        <path d="M 3 2 L 3 24 L 6 24 L 6 14 L 17 14 Q 20 14 20 11 Q 20 8 17 8 L 6 8 L 6 2 Z M 6 10 L 17 10 Q 17.5 10 17.5 11 Q 17.5 12 17 12 L 6 12 Z" fill="#B76749"/>
      </svg>
    </div>

    <h2 class="right-headline" style="font-size:28pt; margin-bottom:3mm;">{{ s02.headline_html | safe }}</h2>
    <div class="right-subhead" style="margin-bottom:6mm;">{{ s02.subhead }}</div>

    <div class="personas">
{% for p in s02.personas %}
      <div class="persona-card{% if p.rank_class == 'primary' %} primary{% endif %}">
        <span class="persona-rank">{{ p.rank_label }}</span>
        <span class="persona-share">{{ p.share_pct }}% share</span>

        <div>
          <div class="persona-name">{{ p.label }}</div>
          <div class="persona-demo">{{ p.demographics | safe }}</div>
          <div class="persona-evidence">{{ p.evidence_note | safe }}</div>
        </div>

        <div class="match-bar">
{% for row in p.match_bars %}          <div class="match-bar-label">{{ row.label }}</div>
          <div class="match-dots">{% for d in row.dots %}<span class="dot{% if d == 'full' %} full{% elif d == 'half' %} half{% endif %}"></span>{% endfor %}</div>
{% endfor %}        </div>
{% if p.willingness_range %}
        <div class="willingness">
          <span class="willingness-label">Willingness to pay</span>
          <span class="willingness-range">{{ p.willingness_range }}</span>
        </div>
{% endif %}
      </div>
{% endfor %}
    </div>

    <div class="anti-fit" style="margin:1mm 0 2mm; font-size:9.5pt;">{{ s02.anti_fit }}</div>

    <div class="source-line" style="margin-bottom:2mm; font-size:7pt;">{{ s02.caption }}</div>

    <div class="fields-advantage" style="padding:3.5mm 7mm 3.5mm 8mm;">
      <span class="fa-label" style="margin-bottom:2mm;">{{ s02.advantage_label }}</span>
      <p class="fa-body" style="font-size:9.5pt; line-height:1.45;">{{ s02.advantage_body_html | safe }}</p>
    </div>

    <div class="page-footer">
      <span class="smarter-mark">
        <svg viewBox="0 0 14 17" xmlns="http://www.w3.org/2000/svg">
          <path d="M 2 2 L 2 15 L 4 15 L 4 9 L 11 9 Q 13 9 13 7 Q 13 5 11 5 L 4 5 L 4 2 Z M 4 6 L 11 6 Q 11.5 6 11.5 7 Q 11.5 8 11 8 L 4 8 Z" fill="#B76749"/>
        </svg>
        Smarter with data
      </span>
      <span class="page-num">7</span>
    </div>
  </div>
</div>"""


def render_section_02_right_html(
    subject_id: str,
    *,
    valuation_mid: float | None = None,
    editorial_overrides: dict | None = None,
    write_substantiation: bool = True,
) -> str:
    """Return the §02 right page as a ready-to-insert HTML block.

    Args:
        subject_id: MongoDB _id (string) of the subject property.
        valuation_mid: midpoint of the reconciled valuation range. Drives
            per-persona willingness-to-pay calculations. None = leave blank.
        editorial_overrides: optional overrides — `subhead`, `anti_fit`,
            `personas` (full replacement), `advantage_body_html`.
        write_substantiation: dual-write the substantiation record (default
            True).
    """
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)

    s02 = data_pull.section_02_right(subject_id, valuation_mid=valuation_mid)

    # Apply editorial overrides
    if "subhead" in overrides:
        s02["subhead"] = overrides["subhead"]
    if "anti_fit" in overrides:
        s02["anti_fit"] = overrides["anti_fit"]
    if "personas" in overrides:
        s02["personas"] = overrides["personas"]

    advantage_body_html = overrides.get("advantage_body_html") or s02["advantage_box"]["body"]

    ctx = {
        "subject": {"short_address": _short_address(subject), "id": str(subject["_id"])},
        "s02": {
            "headline_html": s02["headline_html"],
            "subhead": s02["subhead"],
            "personas": s02["personas"],
            "anti_fit": s02["anti_fit"],
            "caption": s02["caption"],
            "advantage_label": s02["advantage_box"]["label"],
            "advantage_body_html": advantage_body_html,
        },
    }

    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    template = env.from_string(SECTION_02_RIGHT_TEMPLATE)
    html = template.render(**ctx)

    if write_substantiation:
        record = dict(s02["substantiation_record"])
        record["editorial_overrides_applied"] = {k: True for k in overrides}
        record["rendered_html_hash"] = _hash(html)
        substantiation.save(record)

    return html


SECTION_01_RIGHT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 05 — SECTION 01 RIGHT — Why this home is hard to replace -->
<!-- Live HTML. Template-driven from                                   -->
<!-- scripts/appraisal_template/render.render_section_01_right_html() -->
<!-- ============================================================ -->
<div class="page">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 22 26" xmlns="http://www.w3.org/2000/svg">
        <path d="M 3 2 L 3 24 L 6 24 L 6 14 L 17 14 Q 20 14 20 11 Q 20 8 17 8 L 6 8 L 6 2 Z M 6 10 L 17 10 Q 17.5 10 17.5 11 Q 17.5 12 17 12 L 6 12 Z" fill="#B76749"/>
      </svg>
    </div>

    <h2 class="right-headline" style="font-size:30pt; margin-bottom:3mm;">{{ s01.headline_html | safe }}</h2>
    <div class="right-subhead" style="margin-bottom:5mm; font-size:10.5pt;">{{ s01.subhead }}</div>

    <div style="position:relative; margin: 0 0 5mm; border-radius:1.5mm; overflow:hidden;">
      <img src="{{ s01.satellite_image_src }}" alt="{{ subject.short_address }} — aerial view" style="display:block; width:100%; height:auto; border-radius:1.5mm;" />
    </div>

    <div style="display:grid; grid-template-columns: 1fr 60mm; gap:6mm; align-items:start; margin-bottom:4mm;">
      <div>
        <p style="margin:0 0 3mm; font-size:11pt; line-height:1.45;">{{ s01.cohort_body_html | safe }}</p>
        <ul style="margin:0; padding-left:4mm; font-size:10pt; line-height:1.65; list-style:none;">
{% for f in s01.feature_bullets %}          <li style="margin-bottom:1mm;">&mdash; {{ f }}</li>
{% endfor %}        </ul>
      </div>
      <div style="text-align:right;">
{{ s01.dot_grid_svg | safe }}
        <div style="font-size:8pt; letter-spacing:0.04em; color:#8d4d33; margin-top:2mm; font-weight:600;">{{ s01.dot_grid_label_total }} &middot; <span class="copper">{{ s01.dot_grid_label_highlighted }}</span></div>
      </div>
    </div>

    <div class="source-line" style="margin-bottom:3mm; font-size:7.5pt;">{{ s01.caption }}</div>

    <div class="fields-advantage" style="padding:3.5mm 7mm 3.5mm 8mm;">
      <span class="fa-label" style="margin-bottom:2mm;">{{ s01.advantage_label }}</span>
      <p class="fa-body" style="font-size:9.5pt; line-height:1.45;">{{ s01.advantage_body_html | safe }}</p>
    </div>

    <div class="page-footer">
      <span class="smarter-mark">
        <svg viewBox="0 0 14 17" xmlns="http://www.w3.org/2000/svg">
          <path d="M 2 2 L 2 15 L 4 15 L 4 9 L 11 9 Q 13 9 13 7 Q 13 5 11 5 L 4 5 L 4 2 Z M 4 6 L 11 6 Q 11.5 6 11.5 7 Q 11.5 8 11 8 L 4 8 Z" fill="#B76749"/>
        </svg>
        Smarter with data
      </span>
      <span class="page-num">5</span>
    </div>
  </div>
</div>"""


def render_section_01_right_html(
    subject_id: str,
    *,
    highlight_key: Optional[str] = None,
    editorial_overrides: Optional[dict] = None,
    write_substantiation: bool = True,
    satellite_image_src: Optional[str] = None,
) -> str:
    """Return the §01 right page as a ready-to-insert HTML block.

    Args:
        subject_id: MongoDB _id (string) of the subject property.
        highlight_key: optional `pick_highlight` candidate key. If None, the
            top-ranked candidate is used.
        editorial_overrides: optional overrides for narrative copy. Keys:
            `subhead`, `feature_bullets`, `advantage_body_html`,
            `cohort_body_html`, `headline_html`. Stored on the
            appraisal_pipeline record by the ops UI.
        write_substantiation: dual-write the substantiation record (default
            True). Set False when previewing in the ops UI.
        satellite_image_src: optional override for the satellite image path.
            Defaults to the subject's `satellite_analysis.satellite_image_url`,
            falling back to a per-subject asset slug.
    """
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)

    # Resolve highlight (top-ranked unless human picked a different one)
    ranked = pick_highlight.rank(subject)
    if not ranked:
        raise ValueError(f"No highlight candidates ranked for {subject_id}")
    if highlight_key:
        chosen = next((c for c in ranked if c["key"] == highlight_key), None)
        if chosen is None:
            raise ValueError(
                f"Highlight key {highlight_key!r} not in top-ranked candidates for {subject_id}. "
                f"Available keys: {[c['key'] for c in ranked]}"
            )
    else:
        chosen = ranked[0]

    # Pull section payload
    s01 = data_pull.section_01_right(subject_id, highlight=chosen)

    # Render SVG dot grid (deterministic by subject_id)
    svg = dot_grid.render(
        total=s01["dot_grid"]["total"],
        highlighted_count=s01["dot_grid"]["highlighted_count"],
        seed=subject_id,
    )
    # Constrain rendered width via inline attrs so the SVG fits the column
    svg = svg.replace(
        f'width="{_extract_svg_attr(svg, "width")}" height="{_extract_svg_attr(svg, "height")}"',
        'width="58mm" height="51mm"',
        1,
    )

    # Auto-generated narrative bits (overridable)
    short_addr = _short_address(subject)
    cohort_count_word = _n_word(s01["dot_grid"]["highlighted_count"])
    cohort_body_html = overrides.get("cohort_body_html") or (
        f"Of the <strong>{s01['dot_grid']['total']} houses</strong> sold across "
        f"the southern Gold Coast catchment in the last 12 months, "
        f"only <strong>{cohort_count_word} had {chosen['description']}</strong>."
    )
    headline_html = overrides.get("headline_html") or (
        'Why this home is <span class="copper">hard to replace</span>.'
    )
    subhead = overrides.get("subhead") or s01.get("subhead") or ""
    feature_bullets = overrides.get("feature_bullets") or _default_feature_bullets(subject)
    advantage_label = s01["advantage_box"]["label"]
    advantage_body_html = overrides.get("advantage_body_html") or s01["advantage_box"]["body"].replace("\n\n", " ").replace(
        "describing a home and positioning it.",
        "describing a home and positioning it.",
    )
    # Fold "That is the difference..." closing line into strong/em for the V4 design
    if "That is the difference" in advantage_body_html and "<strong>" not in advantage_body_html:
        advantage_body_html = advantage_body_html.replace(
            "That is the difference between describing a home and positioning it.",
            "<strong>That is the difference between describing a home and positioning it.</strong>",
        )

    sat_src = (
        satellite_image_src
        or (subject.get("satellite_analysis") or {}).get("satellite_image_url")
        or _default_satellite_src(subject_id)
    )

    ctx = {
        "subject": {"short_address": short_addr, "id": str(subject["_id"])},
        "s01": {
            "headline_html": headline_html,
            "subhead": subhead,
            "satellite_image_src": sat_src,
            "cohort_body_html": cohort_body_html,
            "feature_bullets": feature_bullets,
            "dot_grid_svg": svg,
            # Compact uppercase tally labels — the body sentence already
            # carries the descriptive narrative ("six had six bedrooms");
            # these labels are the visual proof rhythm beat.
            "dot_grid_label_total": f"{s01['dot_grid']['total']} SOLD",
            "dot_grid_label_highlighted": f"{s01['dot_grid']['highlighted_count']} MATCH",
            "caption": s01["caption"],
            "advantage_label": advantage_label,
            "advantage_body_html": advantage_body_html,
        },
    }

    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    template = env.from_string(SECTION_01_RIGHT_TEMPLATE)
    html = template.render(**ctx)

    if write_substantiation:
        record = dict(s01["substantiation_record"])
        record["editorial_overrides_applied"] = {k: True for k in overrides}
        record["rendered_html_hash"] = _hash(html)
        substantiation.save(record)

    return html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_address(subject: dict) -> str:
    addr = subject.get("street_address") or subject.get("complete_address") or ""
    return addr.title() if addr.isupper() else addr


def _default_feature_bullets(subject: dict) -> list[str]:
    """Build a sensible default feature list from the subject's structured
    fields. The ops UI exposes this for human refinement before render."""
    pvd = subject.get("property_valuation_data") or {}
    outdoor = pvd.get("outdoor") or {}
    meta = pvd.get("property_metadata") or {}
    bullets = []
    beds = subject.get("bedrooms")
    if beds and beds >= 5:
        bullets.append(f"{_n_word(beds)} bedrooms")
    if meta.get("has_study") and meta.get("has_home_office"):
        bullets.append("dual-living configuration")
    if outdoor.get("pool_present"):
        bullets.append("pool")
    # Cul-de-sac + bushland boundary fall to editorial_overrides until
    # satellite_analysis enrichment runs on the subject doc.
    return bullets


def _default_satellite_src(subject_id: str) -> str:
    """Path-relative satellite image src for the V4 preview. Subjects that
    have a working satellite_analysis.satellite_image_url should use that
    instead — this is the fallback for the asset Will manually placed."""
    return f"assets/satellite_{subject_id}.png"


def _n_word(n: int) -> str:
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    if isinstance(n, int) and 0 <= n <= 9:
        return words[n]
    return str(n)


def _extract_svg_attr(svg: str, attr: str) -> str:
    """Pull an attribute value out of the leading <svg> tag."""
    import re
    m = re.search(rf'{attr}="([^"]+)"', svg[:300])
    return m.group(1) if m else ""


def _hash(s: str) -> str:
    """Short hash for audit trail."""
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:16]

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

from scripts.appraisal_template import data_pull, dot_grid, pick_highlight, substantiation, layout_rules


SECTION_01_LEFT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 04 — SECTION 01 LEFT — Buyers pay more for what they      -->
<!-- cannot easily replace. (Live HTML, was locked_p01.png.)        -->
<!-- ============================================================ -->
<div class="page" data-section="01_left">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>

    <div style="display:flex; flex-direction:column; padding: 0 6mm;">
      <div class="spread-number">01</div>

      <h1 style="font-family:'Cormorant Garamond', serif; font-size:38pt; line-height:1.05; font-weight:500; color:#22382C; margin: 0 0 10mm;">Buyers pay more for what they <span class="copper">cannot easily replace</span>.</h1>

      <p style="font-size:11pt; line-height:1.6; color:#2c2924; margin: 0 0 6mm;">A buyer does not value features in isolation. They value combinations.</p>

      <p style="font-size:11pt; line-height:1.6; color:#2c2924; margin: 0 0 6mm;">A bedroom count matters. A pool matters. A quiet street matters. A permanent green boundary matters. The premium is created when those features work together to solve a buyer's problem better than the alternatives.</p>

      <p style="font-size:11pt; line-height:1.6; color:#2c2924; margin: 0 0 8mm;">Fields analyses that combination before the home goes to market — not to make a loose claim of rarity, but to identify the parts of the home that should carry the valuation, the buyer strategy, the presentation and the negotiation.</p>

      <p style="font-family:'Cormorant Garamond', serif; font-style:italic; font-size:13pt; line-height:1.5; color:#B76749; margin: 4mm 0 0;">For {{ subject.short_address }}, the strongest position is the combination.</p>
    </div>

    <div class="page-footer">
      <span class="smarter-mark">
        <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </svg>
        Smarter with data
      </span>
      <span class="page-num">— 4 —</span>
    </div>
  </div>
</div>"""


def render_section_01_left_html(
    subject_id: str,
    *,
    editorial_overrides: dict | None = None,
    write_substantiation: bool = True,
) -> str:
    """Return §01 left page (the irreplaceability thesis) as HTML.
    Editorial copy from the framework doc (07_amendments §5.1)."""
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)
    ctx = {
        "subject": {"short_address": _short_address(subject), "id": str(subject["_id"])},
    }
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = env.from_string(SECTION_01_LEFT_TEMPLATE).render(**ctx)
    if write_substantiation:
        from datetime import datetime, timezone
        substantiation.save({
            "section": "01_left",
            "subject_id": subject_id,
            "subject_address": subject.get("complete_address"),
            "as_at_date": datetime.now(timezone.utc).isoformat(),
            "framework_version": "2026-05-15",
            "rendered_html_hash": _hash(html),
        })
    return html


SECTION_00_COVER_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 01 — OUTER COVER (Alex-designed system)                  -->
<!-- Live HTML, template-driven from                                  -->
<!-- scripts/appraisal_template/render.render_section_00_cover_html() -->
<!-- ============================================================ -->
<div class="cover">
  <div class="cover-image" style="background-image: url('{{ cover.hero_image_src }}');"></div>

  <!-- Large copper F mark, top-left -->
  <img src="{{ cover.logotype_src }}" class="cover-mark-tl" alt="Fields logotype">

  <!-- Top-right Fields wordmark + F -->
  <div class="cover-mark-tr">
    <span>Fields</span>
    <img src="{{ cover.logotype_white_src }}" alt="Fields white logotype">
  </div>

  <!-- Address card, lower-left -->
  <div class="cover-card">
    <div class="cover-card-address">{{ cover.address_stacked_html | safe }}</div>
    <div class="cover-card-suburb">{{ cover.suburb_line }}</div>
  </div>

  <!-- Dark green bottom band with document metadata -->
  <div class="cover-bottom">
    <div class="cover-meta">
      <div class="cover-doc-type cover-doc-title">{{ cover.doc_type }}</div>
      <div class="cover-doc-text">
        <div class="cover-doc-by">{{ cover.prepared_for }}</div>
        <div class="cover-doc-rule"></div>
        <div class="cover-doc-by-text">{{ cover.author_line }}</div>
        <div class="cover-doc-url">{{ cover.url }}</div>
      </div>
      <div class="cover-doc-type cover-doc-date">{{ cover.date_upper }}</div>
    </div>
    <div class="cover-date">
      <span class="smarter-mark">
        <img src="{{ cover.logotype_src }}" alt="Fields logotype">
        Smarter with data
      </span>
    </div>
  </div>
</div>"""


def render_section_00_cover_html(
    subject_id: str,
    *,
    editorial_overrides: dict | None = None,
    hero_image_src: str | None = None,
    prepared_for: str | None = None,
    date_override: str | None = None,
    author: str = "by Will Simpson, Property Consultant",
    write_substantiation: bool = True,
) -> str:
    """Return Page 1 (outer cover) as a ready-to-insert HTML block.

    Parametric across all subjects — variable inputs are:
        hero_image_src      relative path to the cover hero photo
        address_stacked     street components stacked on separate lines
        suburb_line         e.g. "Merrimac, QLD 4226"
        prepared_for        e.g. "Prepared for Dee" / "Prepared for the Owner"
        date_upper          e.g. "10 MAY 2026" — defaults to today

    Brand chrome (Fields F marks, "PROPERTY POSITIONING REPORT" eyebrow,
    "Smarter with data" tagline) is constant.
    """
    from datetime import datetime
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)

    # Stacked address — "13 Terrace Court" → "13<br>Terrace<br>Court"
    street = subject.get("street_address") or _short_address(subject) or ""
    stacked = "<br>".join(w for w in street.split() if w)

    suburb = subject.get("suburb") or ""
    postcode = subject.get("postcode") or subject.get("display_postcode") or ""
    suburb_line = f"{suburb.title() if suburb.isupper() else suburb}, QLD {postcode}".strip(", ")

    prepared_for_final = overrides.get("prepared_for") or prepared_for or "Prepared for the Owner"
    if not prepared_for_final.lower().startswith("prepared"):
        prepared_for_final = f"Prepared for {prepared_for_final}"

    date_final = date_override or datetime.now().strftime("%-d %B %Y").upper()

    # Default hero image — per-subject asset by ObjectId; falls back to a
    # branded placeholder if no per-subject photo exists. Will should curate
    # the hero per appraisal (single photo selection in the ops UI is a
    # future Phase D item).
    hero_final = (
        hero_image_src
        or overrides.get("hero_image_src")
        or f"assets/img/cover_hero_{subject_id}.jpg"
    )

    ctx = {
        "cover": {
            "hero_image_src": hero_final,
            "logotype_src": "assets/img/fields_logotype.svg",
            "logotype_white_src": "assets/img/fields_logotype_white.svg",
            "address_stacked_html": stacked,
            "suburb_line": suburb_line,
            "doc_type": overrides.get("doc_type") or "Property Positioning Report",
            "prepared_for": prepared_for_final,
            "author_line": overrides.get("author_line") or author,
            "url": "fieldsestate.com.au",
            "date_upper": date_final,
        }
    }

    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    template = env.from_string(SECTION_00_COVER_TEMPLATE)
    html = template.render(**ctx)

    if write_substantiation:
        substantiation.save({
            "section": "00_cover",
            "subject_id": subject_id,
            "subject_address": subject.get("complete_address"),
            "hero_image_src": hero_final,
            "prepared_for": prepared_for_final,
            "date": date_final,
            "as_at_date": datetime.now().isoformat(),
            "framework_version": "2026-05-15",
            "rendered_html_hash": _hash(html),
        })

    return html


SECTION_03_RECEIPTS_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 10 — SECTION 03 RECEIPTS — comp-by-comp adjustments       -->
<!-- ============================================================ -->
<div class="page" data-section="03_receipts">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>

{% if s03r.pending_review %}
    <h2 class="right-headline s03" style="font-size:26pt; margin-bottom:2mm;">Comp adjustments — <span class="copper">pending review</span>.</h2>
    <div class="right-subhead" style="margin-bottom:5mm;">Per-comp adjustment cards itemise the dollar moves behind the valuation range.</div>

    <div style="background:#fdf3ec; border-left:3px solid #B76749; padding:7mm 9mm; margin:6mm 0;">
      <div style="font-family:'IBM Plex Mono', monospace; font-size:9pt; letter-spacing:0.18em; text-transform:uppercase; color:#B76749; margin-bottom:4mm;">Analyst review required</div>
      <p style="font-size:11pt; line-height:1.55; color:#2c2924; margin:0 0 4mm;">No comparable sales have been confirmed for this subject yet. Each card on this page shows the subject-versus-comp differences, dollar adjustments and weight — and only renders once the analyst confirms the comparable set in the ops dashboard.</p>
      <p style="font-size:9.5pt; line-height:1.5; color:#5a554d; font-style:italic; margin:0;">Workflow: Ops dashboard → Appraisal Pipeline → confirm comparables → re-render report.</p>
    </div>

    <div style="background:#fdf3ec; border-left:3px solid #B76749; padding:3mm 5mm; display:flex; align-items:center; gap:4mm; margin-bottom:4mm;">
      <div style="font-family:'Cormorant Garamond', serif; font-size:24pt; color:#B76749; line-height:1;">{{ s03r.backtest_stat.mae_pct }}%</div>
      <div style="font-size:9pt; line-height:1.45; color:#2c2924;">{{ s03r.backtest_stat.label | safe }}<br><span style="font-family:'IBM Plex Mono', monospace; font-size:7.5pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33;">Source: Fields valuation backtest · comparable_sales_v3 · 2026-03</span></div>
    </div>
{% else %}
    <h2 class="right-headline s03" style="font-size:26pt; margin-bottom:2mm;">{{ s03r.headline_html | safe }}</h2>
    <div class="right-subhead" style="margin-bottom:5mm;">{{ s03r.subhead }}</div>

{% for c in s03r.cards %}
    <div class="comp-card" style="border:1px solid #d8cfc1; border-radius:3px; margin-bottom:4mm; padding:4mm 5mm; background:#fdfaf3;">
      <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:3mm; border-bottom:1px solid #e6dfd0; padding-bottom:2mm;">
        <div style="font-family:'IBM Plex Mono', monospace; font-size:9pt; letter-spacing:0.06em; color:#8d4d33; font-weight:600;">{{ c.rank_label }}</div>
        <div style="font-family:'Cormorant Garamond', serif; font-size:15pt; color:#22382C;"><strong>{{ c.address }}</strong></div>
        <div style="font-family:'IBM Plex Mono', monospace; font-size:9pt; color:#5a554d;">
          {% if c.sold_price %}SOLD ${{ '{:,}'.format(c.sold_price) }}{% endif %}{% if c.distance_km %} · {{ '%.2f'|format(c.distance_km) }} km{% endif %}
        </div>
      </div>

      <table style="width:100%; font-size:9.5pt; border-collapse:collapse;">
{% for r in c.adjustments %}        <tr>
          <td style="padding:3px 0; color:#22382C;">{{ r.label }}{% if r.diff is not none and r.diff != 0 %} <span style="color:#7a8a80; font-style:italic;">(subject {% if r.diff > 0 %}+{% else %}{% endif %}{{ r.diff }}{% if r.key in ('floor_area','land_size','land_area') %} m²{% endif %})</span>{% endif %}</td>
          <td style="padding:3px 0; text-align:right; color:{% if r.adjustment_dollars >= 0 %}#22382C{% else %}#8d4d33{% endif %}; font-family:'IBM Plex Mono', monospace; font-size:10pt;">
            {% if r.adjustment_dollars >= 0 %}+{% else %}{% endif %}${{ '{:,}'.format(r.adjustment_dollars) }}
          </td>
        </tr>
{% endfor %}      </table>

      {% if c.adjusted_total %}
      <div style="display:flex; justify-content:space-between; align-items:center; margin-top:3mm; padding-top:3mm; border-top:1px solid #e6dfd0;">
        <div style="font-family:'IBM Plex Mono', monospace; font-size:8pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33;">Adjusted estimate of subject</div>
        <div style="font-family:'Cormorant Garamond', serif; font-size:18pt; color:#B76749;"><strong>${{ '{:,}'.format(c.adjusted_total) }}</strong></div>
        <div style="font-family:'IBM Plex Mono', monospace; font-size:8pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33;">Weight {{ c.weight_pct }}%</div>
      </div>
      {% endif %}
    </div>
{% endfor %}

    {% if s03r.rest_count > 0 %}
    <div style="background:#f0e6d5; border-left:3px solid #B76749; padding:3mm 5mm; font-size:9.5pt; line-height:1.5; margin-bottom:4mm;">
      <strong>{{ s03r.cards|length }} comp{% if s03r.cards|length > 1 %}s{% endif %} shown in detail.</strong> {{ s03r.rest_count }} additional comparable sale{% if s03r.rest_count > 1 %}s{% endif %} contribute the remaining {{ s03r.rest_weight_pct }}% of the weight. Every adjustment is verified against the cohort median before reconciliation.
    </div>
    {% endif %}

    <div style="background:#fdf3ec; border-left:3px solid #B76749; padding:3mm 5mm; display:flex; align-items:center; gap:4mm; margin-bottom:4mm;">
      <div style="font-family:'Cormorant Garamond', serif; font-size:24pt; color:#B76749; line-height:1;">{{ s03r.backtest_stat.mae_pct }}%</div>
      <div style="font-size:9pt; line-height:1.45; color:#2c2924;">{{ s03r.backtest_stat.label | safe }}<br><span style="font-family:'IBM Plex Mono', monospace; font-size:7.5pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33;">Source: Fields valuation backtest · comparable_sales_v3 · 2026-03</span></div>
    </div>

    <div class="source-line" style="font-size:7.5pt;">{{ s03r.caption }}</div>
{% endif %}

    <div class="page-footer">
      <span class="smarter-mark"><svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </svg>Smarter with data</span>
      <span class="page-num">— 10 —</span>
    </div>
  </div>
</div>"""


def render_section_03_receipts_html(
    subject_id: str,
    *,
    top_n: int = 2,
    editorial_overrides: dict | None = None,
    write_substantiation: bool = True,
) -> str:
    """§03 receipts page — comp-by-comp adjustment cards."""
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)
    s03r = data_pull.section_03_receipts(subject_id, top_n=top_n)
    if "subhead" in overrides:
        s03r["subhead"] = overrides["subhead"]
    ctx = {
        "subject": {"short_address": _short_address(subject)},
        "s03r": s03r,
    }
    if not s03r.get("pending_review", False):
        layout_rules.validate_and_record("03_receipts", {
            "headline_html": s03r["headline_html"],
            "subhead": s03r.get("subhead", ""),
            "cards": s03r.get("cards", []),
            "caption": s03r.get("caption", ""),
        })
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = env.from_string(SECTION_03_RECEIPTS_TEMPLATE).render(**ctx)
    if write_substantiation:
        substantiation.save({**s03r["substantiation_record"], "rendered_html_hash": _hash(html)})
    return html


SECTION_04_RIGHT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 13 — SECTION 04 RIGHT — Active/passive buyer reach.       -->
<!-- ============================================================ -->
<div class="page" data-section="04_right">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>
    <h2 class="right-headline s03" style="font-size:24pt; margin-bottom:6mm;">{{ s04.headline_html | safe }}</h2>
    <div style="display:flex; flex-direction:column; gap:4mm;">
{% for m in s04.modes %}
      <div style="display:grid; grid-template-columns:18mm 1fr; gap:5mm; align-items:center; background:#fdfaf3; border-left:3px solid #B76749; border-radius:2px; padding:5mm 6mm 5mm 5mm;">
        <div style="font-family:'Cormorant Garamond', serif; font-size:32pt; color:#B76749; line-height:1; text-align:center;">{{ m.num }}</div>
        <div>
          <div style="font-weight:600; color:#22382C; font-size:11pt; margin-bottom:2mm;">{{ m.label }}</div>
          <div style="font-size:10pt; line-height:1.5; color:#2c2924; margin-bottom:2.5mm;">{{ m.desc }}</div>
          <div style="font-family:'IBM Plex Mono', monospace; font-size:7.5pt; letter-spacing:0.06em; text-transform:uppercase; color:#B76749;">{{ m.channels }}</div>
        </div>
      </div>
{% endfor %}
    </div>
    <div class="campaign-model" style="background:#fdf3ec; border-radius:6px; padding:14px 18px; margin: 6mm 0 3mm; font-size:9.5pt;">
      <div style="font-family:'IBM Plex Mono', monospace; font-size:8pt; letter-spacing:0.04em; text-transform:uppercase; color:#8d4d33; margin-bottom:6px;">28-day campaign model</div>
      Based on recent campaign benchmarks, a property like {{ subject.short_address }} would be marketed toward approximately <strong>{{ s04.campaign_model.impressions_low|int }},000–{{ s04.campaign_model.impressions_high|int }},000 targeted impressions</strong>, with the aim of generating <strong>{{ s04.campaign_model.engagements_low }}–{{ s04.campaign_model.engagements_high }} deep engagements</strong> and <strong>{{ s04.campaign_model.inspections_low }}–{{ s04.campaign_model.inspections_high }} inspections</strong>. The objective is not exposure for its own sake — it is enough targeted reach to find the right buyer, and enough inspection volume to create competition.
    </div>
    <div class="source-line">{{ s04.caption }}</div>
    <div class="fields-advantage" style="padding:3.5mm 7mm;">
      <span class="fa-label">{{ s04.advantage_label }}</span>
      <p class="fa-body" style="font-size:9.5pt; line-height:1.45;">{{ s04.advantage_body_html | safe }}</p>
    </div>
    <div class="page-footer"><span class="smarter-mark"><svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </svg>Smarter with data</span><span class="page-num">— 13 —</span></div>
  </div>
</div>"""


SECTION_05_RIGHT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 15 — SECTION 05 RIGHT — Presentation turns features into desire. -->
<!-- ============================================================ -->
<div class="page" data-section="05_right">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>
    <h2 class="right-headline" style="font-size:28pt; margin-bottom:3mm;">{{ s05.headline_html | safe }}</h2>
    <div class="right-subhead" style="margin-bottom:5mm;">{{ s05.subhead }}</div>
    {% if s05.photo_left and s05.photo_right %}
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:4mm; margin-bottom:4mm;">
      <div><img src="{{ s05.photo_left }}" style="width:100%; border-radius:1mm;"/><div style="font-size:7.5pt; color:#5a554d; margin-top:1mm; font-family:'IBM Plex Mono', monospace;">STANDARD REAL-ESTATE PHOTOGRAPHY</div></div>
      <div><img src="{{ s05.photo_right }}" style="width:100%; border-radius:1mm;"/><div style="font-size:7.5pt; color:#B76749; margin-top:1mm; font-family:'IBM Plex Mono', monospace;">FIELDS TWILIGHT PHOTOGRAPHY</div></div>
    </div>
    {% endif %}
    <div class="stat-box" style="background:#fdf3ec; border-left:3px solid #B76749; padding:12px 16px; margin: 4mm 0;">
      <div style="font-family:'Cormorant Garamond', serif; font-size:30pt; line-height:1; color:#B76749;">+{{ s05.photo_contrast_stat.uplift_pct }}%</div>
      <div style="font-size:10pt; line-height:1.45; margin-top:4px;">{{ s05.photo_contrast_stat.label }}</div>
      <div style="font-family:'IBM Plex Mono', monospace; font-size:7.5pt; letter-spacing:0.04em; color:#8d4d33; margin-top:6px; text-transform:uppercase;">Source: {{ s05.photo_contrast_stat.source }}</div>
    </div>
{% for row in s05.presentation_rows %}
    <div style="display:grid; grid-template-columns:30mm 1fr; gap:6mm; align-items:start; padding:6mm 0; border-top:1px solid #e6dfd0;">
      <div style="font-family:'Cormorant Garamond', serif; font-size:24pt; color:#B76749; line-height:1;">{{ row.num }}</div>
      <div><div style="font-weight:600; margin-bottom:3px;">{{ row.label }}</div><div style="font-size:10pt; line-height:1.5;">{{ row.desc | safe }}</div></div>
    </div>
{% endfor %}
    <div class="fields-advantage" style="padding:3.5mm 7mm; margin-top:4mm;">
      <span class="fa-label">{{ s05.advantage_label }}</span>
      <p class="fa-body" style="font-size:9.5pt; line-height:1.45;">{{ s05.advantage_body_html | safe }}</p>
    </div>
    <div class="page-footer"><span class="smarter-mark"><svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </svg>Smarter with data</span><span class="page-num">— 15 —</span></div>
  </div>
</div>"""


SECTION_06_RIGHT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 17 — SECTION 06 RIGHT — The evidence buyers need.        -->
<!-- ============================================================ -->
<div class="page" data-section="06_right">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>
    <h2 class="right-headline" style="font-size:28pt; margin-bottom:3mm;">{{ s06.headline_html | safe }}</h2>
    <div class="right-subhead" style="margin-bottom:5mm;">{{ s06.subhead }}</div>
{% for a in s06.assets %}
    <div style="display:grid; grid-template-columns:30mm 1fr; gap:6mm; align-items:start; padding:6mm 0; border-top:1px solid #e6dfd0;">
      <div style="font-family:'Cormorant Garamond', serif; font-size:24pt; color:#B76749; line-height:1;">{{ a.num }}</div>
      <div><div style="font-weight:600; margin-bottom:3px;">{{ a.label }}</div><div style="font-size:10pt; line-height:1.5;">{{ a.desc | safe }}</div></div>
    </div>
{% endfor %}
    <div class="stat-box" style="background:#fdf3ec; border-left:3px solid #B76749; padding:12px 16px; margin: 4mm 0;">
      <div style="font-family:'Cormorant Garamond', serif; font-size:30pt; line-height:1; color:#B76749;">+{{ s06.relationship_premium_stat.uplift_pct }}%</div>
      <div style="font-size:10pt; line-height:1.45; margin-top:4px;">{{ s06.relationship_premium_stat.label }}</div>
      <div style="font-family:'IBM Plex Mono', monospace; font-size:7.5pt; letter-spacing:0.04em; color:#8d4d33; margin-top:6px; text-transform:uppercase;">Source: {{ s06.relationship_premium_stat.source }}</div>
    </div>
    <div class="fields-advantage" style="padding:3.5mm 7mm;">
      <span class="fa-label">{{ s06.advantage_label }}</span>
      <p class="fa-body" style="font-size:9.5pt; line-height:1.45;">{{ s06.advantage_body_html | safe }}</p>
    </div>
    <div class="page-footer"><span class="smarter-mark"><svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </svg>Smarter with data</span><span class="page-num">— 17 —</span></div>
  </div>
</div>"""


def render_section_04_right_html(subject_id: str, *, editorial_overrides: dict | None = None, write_substantiation: bool = True) -> str:
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)
    s04 = data_pull.section_04_right(subject_id)
    advantage_body_html = overrides.get("advantage_body_html") or s04["advantage_box"]["body"]
    ctx = {
        "subject": {"short_address": _short_address(subject)},
        "s04": {**s04, "advantage_label": s04["advantage_box"]["label"], "advantage_body_html": advantage_body_html},
    }
    layout_rules.validate_and_record("04_right", {
        "headline_html": s04["headline_html"],
        "subhead": s04.get("subhead", ""),
        "modes": s04.get("modes", []),
        "caption": s04.get("caption", ""),
        "advantage_body_html": advantage_body_html,
    })
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = env.from_string(SECTION_04_RIGHT_TEMPLATE).render(**ctx)
    if write_substantiation:
        substantiation.save({**s04["substantiation_record"], "rendered_html_hash": _hash(html)})
    return html


def render_section_05_right_html(subject_id: str, *, editorial_overrides: dict | None = None, write_substantiation: bool = True, photo_left: str | None = None, photo_right: str | None = None) -> str:
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)
    s05 = data_pull.section_05_right(subject_id)
    s05["photo_left"] = photo_left
    s05["photo_right"] = photo_right
    advantage_body_html = overrides.get("advantage_body_html") or s05["advantage_box"]["body"]
    ctx = {
        "subject": {"short_address": _short_address(subject)},
        "s05": {**s05, "advantage_label": s05["advantage_box"]["label"], "advantage_body_html": advantage_body_html},
    }
    layout_rules.validate_and_record("05_right", {
        "headline_html": s05["headline_html"],
        "subhead": s05.get("subhead", ""),
        "presentation_rows": s05.get("presentation_rows", []),
        "advantage_body_html": advantage_body_html,
    })
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = env.from_string(SECTION_05_RIGHT_TEMPLATE).render(**ctx)
    if write_substantiation:
        substantiation.save({**s05["substantiation_record"], "rendered_html_hash": _hash(html)})
    return html


def render_section_06_right_html(subject_id: str, *, editorial_overrides: dict | None = None, write_substantiation: bool = True) -> str:
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)
    s06 = data_pull.section_06_right(subject_id)
    advantage_body_html = overrides.get("advantage_body_html") or s06["advantage_box"]["body"]
    ctx = {
        "subject": {"short_address": _short_address(subject)},
        "s06": {**s06, "advantage_label": s06["advantage_box"]["label"], "advantage_body_html": advantage_body_html},
    }
    layout_rules.validate_and_record("06_right", {
        "headline_html": s06["headline_html"],
        "subhead": s06.get("subhead", ""),
        "assets": s06.get("assets", []),
        "advantage_body_html": advantage_body_html,
    })
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    html = env.from_string(SECTION_06_RIGHT_TEMPLATE).render(**ctx)
    if write_substantiation:
        substantiation.save({**s06["substantiation_record"], "rendered_html_hash": _hash(html)})
    return html


SECTION_03_RIGHT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 09 — SECTION 03 RIGHT — The range, derived.              -->
<!-- Live HTML, template-driven from                                  -->
<!-- scripts/appraisal_template/render.render_section_03_right_html() -->
<!-- ============================================================ -->
<div class="page" data-section="03_right">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>

{% if s03.pending_review %}
    <h2 class="right-headline s03"><span class="copper">The range, derived</span> — pending review.</h2>
    <div class="right-subhead" style="margin-bottom:6mm;">This page reports the catchment-anchored valuation range for the subject.</div>

    <div style="background:#fdf3ec; border-left:3px solid #B76749; padding:7mm 9mm; margin:8mm 0;">
      <div style="font-family:'IBM Plex Mono', monospace; font-size:9pt; letter-spacing:0.18em; text-transform:uppercase; color:#B76749; margin-bottom:4mm;">Analyst review required</div>
      <p style="font-size:11pt; line-height:1.55; color:#2c2924; margin:0 0 4mm;">The Fields valuation engine has not yet produced a reconciled range for this property. The comparable set, attribute weights, and derived range populate once the analyst confirms the comparables in the ops dashboard.</p>
      <p style="font-size:9.5pt; line-height:1.5; color:#5a554d; font-style:italic; margin:0;">Workflow: Ops dashboard → Appraisal Pipeline → confirm comparables → re-render report.</p>
    </div>

    <div class="cohort-anchor">
      {{ s03.cohort_anchor_html | safe }}
    </div>

    <div class="source-line">{{ s03.caption }}</div>
{% else %}
    <h2 class="right-headline s03"><span class="copper">{{ s03.headline_dollar_range }}.</span> The range, derived.</h2>
    <div class="right-subhead" style="margin-bottom:6mm;">{{ s03.subhead }}</div>

    <div class="cohort-anchor">
      {{ s03.cohort_anchor_html | safe }}
    </div>

    <div class="evidence-stack">
{% for row in s03.evidence_stack %}      <div class="evidence-row">
        <div class="attr">{{ row.attr | safe }}</div>
        <div class="band">
          <div class="band-dots">{% for d in row.dots %}<span class="dot{% if d == 'full' %} full{% elif d == 'half' %} half{% endif %}"></span>{% endfor %}</div>
        </div>
        <div class="signal">{{ row.signal | safe }}</div>
      </div>
{% endfor %}    </div>

    <div class="synthesis">
      <span class="label">Derived range</span>
      <span class="range">{{ s03.synthesis.low }} – {{ s03.synthesis.high }}</span>
      <span class="meta">midpoint {{ s03.synthesis.mid }} · 90% CI</span>
    </div>

    <div class="method-note">{{ s03.method_note }}</div>

    <div class="confidence-row">n={{ s03.n_comps }} comparable transactions analysed · cohort-weighted with attribute-level adjustment · confidence: {{ s03.confidence_label }}</div>

    <div class="source-line">{{ s03.caption }}</div>
{% endif %}

    <div class="fields-advantage">
      <span class="fa-label">{{ s03.advantage_label }}</span>
      <p class="fa-body">{{ s03.advantage_body_html | safe }}</p>
    </div>

    <div class="page-footer">
      <span class="smarter-mark">
        <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </svg>
        Smarter with data
      </span>
      <span class="page-num">— 9 —</span>
    </div>
  </div>
</div>"""


def render_section_03_right_html(
    subject_id: str,
    *,
    editorial_overrides: dict | None = None,
    write_substantiation: bool = True,
) -> str:
    """Return the §03 right page as a ready-to-insert HTML block."""
    overrides = editorial_overrides or {}
    subject = data_pull.get_subject(subject_id)
    s03 = data_pull.section_03_right(subject_id)

    # Evidence stack — defaults to a sensible 6-row baseline for premium homes,
    # fully overridable via editorial_overrides.evidence_stack. Each row:
    # {"attr": str, "dots": [5x 'full'|'half'|'empty'], "signal": str}
    default_stack = [
        {"attr": "Bedroom scale", "dots": ["full"]*4 + ["empty"],
         "signal": f"Bedroom cohort lift documented in the cohort-anchor table above."},
        {"attr": "Pool &amp; outdoor lifestyle", "dots": ["full"]*3 + ["empty"]*2,
         "signal": "Standard premium across southern Gold Coast (cohort coverage in valuation engine)."},
        {"attr": "Condition", "dots": ["full"]*4 + ["empty"],
         "signal": "Move-in-ready buyers pay above cohort median for completed homes."},
    ]
    s03["evidence_stack"] = overrides.get("evidence_stack") or default_stack
    s03["method_note"] = overrides.get("method_note") or (
        "Premium attributes co-vary; the range is derived from the weighted set "
        "of comparable transactions, not from arithmetic stacking."
    )
    advantage_body_html = overrides.get("advantage_body_html") or s03["advantage_box"]["body"]

    ctx = {
        "subject": {"short_address": _short_address(subject), "id": str(subject["_id"])},
        "s03": {
            "pending_review": s03.get("pending_review", False),
            "headline_dollar_range": s03["headline_dollar_range"],
            "subhead": overrides.get("subhead") or s03["subhead"],
            "cohort_anchor_html": s03["cohort_anchor_html"],
            "evidence_stack": s03["evidence_stack"],
            "synthesis": s03["synthesis"],
            "method_note": s03["method_note"],
            "n_comps": s03["n_comps"],
            "confidence_label": s03["confidence_label"] or "—",
            "caption": s03["caption"],
            "advantage_label": s03["advantage_box"]["label"],
            "advantage_body_html": advantage_body_html,
        },
    }

    # Validate only when content is present — pending-review state intentionally
    # omits cohort+evidence+synthesis so it should not fire budget warnings.
    if not s03.get("pending_review", False):
        layout_rules.validate_and_record("03_right", {
            "headline_html": f'<span class="copper">{s03["headline_dollar_range"]}.</span> The range, derived.',
            "subhead": overrides.get("subhead") or s03["subhead"],
            "cohort_anchor_html": s03["cohort_anchor_html"],
            "evidence_stack": s03["evidence_stack"],
            "method_note": s03["method_note"],
            "caption": s03["caption"],
            "advantage_body_html": advantage_body_html,
        })

    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
    template = env.from_string(SECTION_03_RIGHT_TEMPLATE)
    html = template.render(**ctx)

    if write_substantiation:
        record = dict(s03["substantiation_record"])
        record["editorial_overrides_applied"] = {k: True for k in overrides}
        record["rendered_html_hash"] = _hash(html)
        substantiation.save(record)

    return html


SECTION_02_RIGHT_TEMPLATE = """\
<!-- ============================================================ -->
<!-- PAGE 07 — SECTION 02 RIGHT — Three buyers. One outbids.       -->
<!-- Live HTML, template-driven from                                  -->
<!-- scripts/appraisal_template/render.render_section_02_right_html() -->
<!-- ============================================================ -->
<div class="page" data-section="02_right">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
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
        <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
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

    layout_rules.validate_and_record("02_right", {**ctx["s02"]})

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
<div class="page" data-section="01_right">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>

    <h2 class="right-headline" style="font-size:30pt; margin-bottom:3mm;">{{ s01.headline_html | safe }}</h2>
    <div class="right-subhead" style="margin-bottom:5mm; font-size:10.5pt;">{{ s01.subhead }}</div>

    <div style="position:relative; margin: 0 0 5mm; border-radius:1.5mm; overflow:hidden; max-height:88mm;">
      <img src="{{ s01.satellite_image_src }}" alt="{{ subject.short_address }} — aerial view" style="display:block; width:100%; height:88mm; object-fit:cover; border-radius:1.5mm;" />
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

    <div class="fields-advantage" style="padding:3.5mm 7mm 3.5mm 8mm; margin-bottom:8mm;">
      <span class="fa-label" style="margin-bottom:2mm;">{{ s01.advantage_label }}</span>
      <p class="fa-body" style="font-size:9.5pt; line-height:1.45;">{{ s01.advantage_body_html | safe }}</p>
    </div>

    <div class="page-footer">
      <span class="smarter-mark">
        <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
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

    # Filter dead Azure blob URLs — the migration left these as stale refs
    # on subject docs but the blob account is shut down. Same filter pattern
    # the Netlify functions use in their image-fallback chain.
    _stored = (subject.get("satellite_analysis") or {}).get("satellite_image_url") or ""
    if "blob.core.windows.net" in _stored:
        _stored = ""
    sat_src = satellite_image_src or _stored or _default_satellite_src(subject_id)

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

    layout_rules.validate_and_record("01_right", {
        "headline_html": headline_html,
        "subhead": subhead,
        "feature_bullets": feature_bullets,
        "cohort_body_html": cohort_body_html,
        "advantage_body_html": advantage_body_html,
    })

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

SECTION_RECOMMENDATION_TEMPLATE = '''\
<!-- ============================================================ -->
<!-- PAGE {{ rec.page_number }} — RECOMMENDATION                   -->
<!-- ============================================================ -->
<div class="page" data-section="recommendation_p{{ rec.page_number }}">
  <div class="page-pad">
    <div class="page-header">
      <div class="page-header-title">For {{ subject.short_address }}</div>
      <svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
        <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
        <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
      </svg>
    </div>
    <div style="font-family:IBM Plex Mono, monospace; font-size:9pt; letter-spacing:0.15em; text-transform:uppercase; color:#B76749; margin-bottom:3mm;">Recommendation</div>
    <h2 class="right-headline" style="font-size:30pt; margin-bottom:3mm;">{{ rec.headline_html | safe }}</h2>
    <div class="right-subhead" style="margin-bottom:6mm;">{{ rec.subhead }}</div>
    {% if rec.pending_review %}
    <div style="background:#fdf3ec; border-left:3px solid #B76749; padding:7mm 9mm; margin-bottom:6mm;">
      <div style="font-family:'IBM Plex Mono', monospace; font-size:9pt; letter-spacing:0.18em; text-transform:uppercase; color:#B76749; margin-bottom:4mm;">Analyst review required</div>
      <p style="font-size:11pt; line-height:1.55; color:#2c2924; margin:0 0 4mm;">The recommended listing price and target sale price are set by the analyst on top of the derived valuation range. Both are populated in the ops dashboard after the valuation is confirmed.</p>
      <p style="font-size:9.5pt; line-height:1.5; color:#5a554d; font-style:italic; margin:0;">Workflow: Ops dashboard → Appraisal Pipeline → set listing &amp; target prices → re-render report.</p>
    </div>
    {% else %}
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6mm; margin-bottom:6mm;">
      <div style="background:#fdf3ec; border-left:3px solid #B76749; padding:5mm 6mm;">
        <div style="font-family:IBM Plex Mono, monospace; font-size:8pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33; margin-bottom:3mm;">Recommended listing price</div>
        <div style="font-family:Cormorant Garamond, serif; font-size:36pt; color:#B76749; line-height:1;">${{ '{:,}'.format(rec.listing_price) }}</div>
      </div>
      <div style="background:#fdf3ec; border-left:3px solid #B76749; padding:5mm 6mm;">
        <div style="font-family:IBM Plex Mono, monospace; font-size:8pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33; margin-bottom:3mm;">Target sale price</div>
        <div style="font-family:Cormorant Garamond, serif; font-size:26pt; color:#B76749; line-height:1.15;">${{ '{:,}'.format(rec.target_sale_price_low) }} –<br>${{ '{:,}'.format(rec.target_sale_price_high) }}</div>
      </div>
    </div>
    {% if rec.page_number == 11 %}
    <p style="font-size:10.5pt; line-height:1.55; color:#2c2924; margin-bottom:5mm;">The listing price sits in the lower end of the derived <strong>${{ '{:,}'.format(rec.derived_range_low or 0) }} – ${{ '{:,}'.format(rec.derived_range_high or 0) }}</strong> range. The target sits in the upper end. <em>Multiple interested buyers move from the listing price toward the target. A single buyer moves the other way.</em></p>
    {% else %}
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:6mm; margin-top:6mm;">
      <div><div style="font-family:IBM Plex Mono, monospace; font-size:8pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33;">Campaign duration</div><div style="font-family:Cormorant Garamond, serif; font-size:30pt; color:#B76749;">{{ rec.campaign_duration_days }} days</div></div>
      <div><div style="font-family:IBM Plex Mono, monospace; font-size:8pt; letter-spacing:0.06em; text-transform:uppercase; color:#8d4d33;">Estimated inspections</div><div style="font-family:Cormorant Garamond, serif; font-size:30pt; color:#B76749;">{{ rec.estimated_inspections }}</div></div>
    </div>
    {% endif %}
    {% endif %}
    <div class="page-footer"><span class="smarter-mark"><svg viewBox="0 0 113.39 113.39" xmlns="http://www.w3.org/2000/svg">
          <path fill="#B76749" d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path fill="#B76749" d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </svg>Smarter with data</span><span class="page-num">— {{ rec.page_number }} —</span></div>
  </div>
</div>'''


def render_section_recommendation_html(
    subject_id: str,
    *,
    page_number: int = 11,
    pipeline_record: dict | None = None,
    write_substantiation: bool = True,
) -> str:
    subject = data_pull.get_subject(subject_id)
    rec = data_pull.section_recommendation(subject_id, pipeline_record=pipeline_record, page_number=page_number)
    ctx = {'subject': {'short_address': _short_address(subject)}, 'rec': rec}
    if not rec.get("pending_review", False):
        section_key = "recommendation_p11" if page_number == 11 else "recommendation_p18"
        layout_rules.validate_and_record(section_key, {
            "campaign_duration_days": rec.get("campaign_duration_days", ""),
        })
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(['html']))
    html = env.from_string(SECTION_RECOMMENDATION_TEMPLATE).render(**ctx)
    if write_substantiation:
        substantiation.save({**rec['substantiation_record'], 'rendered_html_hash': _hash(html)})
    return html


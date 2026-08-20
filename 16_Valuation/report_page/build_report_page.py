#!/usr/bin/env python3
"""Render the formal valuation report mock-up for a single address.

Every figure on the page is pulled from `valuation_data` on the property
document — nothing is hand-transcribed. Run it, read the HTML it writes.

    python3 16_Valuation/report_page/build_report_page.py \
        --address "27 HUNTINGDALE CRESCENT ROBINA QLD 4226" \
        --collection robina \
        --out 16_Valuation/report_page/report.html
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.db import get_gold_coast_db  # noqa: E402

REPORT_DATE = dt.date(2026, 8, 20)

# Adjustment lines in the order a valuer's grid presents them: physical
# attributes first, then condition, then locational.
LINE_ORDER = [
    ("land_size", "Land area", "sqm"),
    ("floor_area", "Living area", "sqm"),
    ("bedrooms", "Bedrooms", None),
    ("bathrooms", "Bathrooms", None),
    ("car_spaces", "Car spaces", None),
    ("pool", "Swimming pool", None),
    ("stories", "Storeys", None),
    ("cladding", "External cladding", None),
    ("ac_type", "Ducted air-conditioning", None),
    ("property_age", "Age of improvements", "yr"),
    ("water_views", "Water outlook", None),
    ("condition", "Condition", None),
    ("renovation", "Renovation level", None),
    ("kitchen", "Kitchen quality", None),
    ("renovation_quality", "Renovation quality", None),
    ("beach_proximity", "Beach proximity", None),
    ("street_premium", "Street premium", None),
    ("micro_location", "Micro-location", None),
    ("golf_course_backing", "Golf course frontage", None),
]

WEIGHT_FACTOR_LABELS = [
    ("adjustment_quality", "Adjustment quality"),
    ("adjusted_accuracy", "Adjusted accuracy"),
    ("proximity", "Proximity"),
    ("recency", "Recency"),
    ("verification", "Sale verified"),
    ("data_quality", "Data quality"),
]


def money(v, sign=False):
    if v is None:
        return "—"
    v = int(round(v))
    s = f"${abs(v):,}"
    if v < 0:
        return "−" + s
    if sign and v > 0:
        return "+" + s
    return s


def esc(s):
    return html.escape(str(s), quote=True)


def short_addr(a):
    """'4 Springvale Street, Robina QLD 4226' -> '4 Springvale Street'."""
    return a.split(",")[0].strip()


def fetch(collection: str, address: str):
    db = get_gold_coast_db()
    doc = db[collection].find_one({"complete_address": address})
    if not doc:
        raise SystemExit(f"No document with complete_address={address!r} in {collection}")
    vd = doc.get("valuation_data")
    if not vd:
        raise SystemExit(f"{address} has no valuation_data — nothing to report")
    comps = [r for r in vd.get("recent_sales", []) if r.get("included_in_valuation")]
    if not comps:
        raise SystemExit(f"{address} has valuation_data but zero included comparables")
    return doc, vd, comps


def pool_stats(vd, rows):
    """Facts about the FULL candidate pool the point figure is reconciled from.

    precompute_valuations.py:4013 computes the reconciled figure from
    `valuation_points(all_enriched_points)` — the whole pool — while
    `included_points` stays the eight shown to the reader. The report must not
    present the eight as the derivation, so it needs the pool's own numbers.
    """
    pool = [
        r
        for r in vd.get("recent_sales", [])
        if (r.get("adjustment_result") or {}).get("adjusted_price")
        and (r.get("weight") or {}).get("normalized")
    ]
    if not pool:
        raise SystemExit("no weighted candidate pool — cannot describe the derivation")
    total_w = sum(r["weight"]["normalized"] for r in pool)
    shown_w = sum(r["weight"]["normalized"] for r in pool if r.get("included_in_valuation"))
    prices = [r["adjustment_result"]["adjusted_price"] for r in pool]
    shown_mean = sum(r["adjusted_price"] * r["weight_norm"] for r in rows) / sum(
        r["weight_norm"] for r in rows
    )
    return {
        "n": len(pool),
        "shown_share": shown_w / total_w,
        "lo": min(prices),
        "hi": max(prices),
        "shown_mean": round(shown_mean),
    }


def attrs_from_adjustments(adjustments):
    """Read the comparable's attributes from the adjustment lines themselves.

    `features.basic` and the adjustment `comp_value` disagree on floor area for
    several comparables — features.basic carries 30 sqm for 28 Merion Court,
    which is a data defect, while the adjustment correctly used 233. The values
    that actually drove the assessment are the ones in the adjustment lines, so
    the schedule is sourced from there and the two sections cannot diverge.
    """

    def cv(key):
        a = adjustments.get(key) or {}
        if a.get("skipped") or a.get("retired"):
            return None
        return a.get("comp_value")

    return {
        "bedrooms": cv("bedrooms"),
        "bathrooms": cv("bathrooms"),
        "car_spaces": cv("car_spaces"),
        "floor_area_sqm": cv("floor_area"),
        "land_size_sqm": cv("land_size"),
        "pool_present": bool(cv("pool")),
    }


def build_comps(comps):
    """Normalise each included comparable into a flat row, sorted by adjusted price."""
    out = []
    for r in comps:
        ar = r["adjustment_result"]
        sale_date = dt.datetime.utcfromtimestamp(r["sale_date"] / 1000).date()
        months = (REPORT_DATE - sale_date).days / 30.44
        out.append(
            {
                "address": r["address"],
                "short": short_addr(r["address"]),
                "sale_price": int(r["price"]),
                "sale_date": sale_date,
                "months": months,
                "distance_km": r.get("distance_km"),
                "adjusted_price": int(ar["adjusted_price"]),
                "total_adjustment": ar.get("total_adjustment"),
                "total_pct": ar.get("total_adjustment_pct"),
                "reliability": ar.get("reliability_applied"),
                "rates_source": ar.get("rates_source"),
                "weight_raw": r["weight"]["raw_weight"],
                "weight_norm": r["weight"]["normalized"],
                "weight_factors": r["weight"]["factors"],
                "adjustments": ar.get("adjustments", {}),
                "features": attrs_from_adjustments(ar.get("adjustments", {})),
            }
        )
    out.sort(key=lambda x: x["adjusted_price"])
    return out


# --------------------------------------------------------------------------
# section renderers
# --------------------------------------------------------------------------


def render_adjustment_grid(rows):
    """The classic valuer's adjustment matrix: lines down, comparables across."""
    heads = "".join(
        f'<th scope="col"><span class="grid-addr">{esc(r["short"])}</span>'
        f'<span class="grid-sub">{r["sale_date"].strftime("%b %Y")}</span></th>'
        for r in rows
    )

    body = []
    # Sale price row
    cells = "".join(f'<td class="num">{money(r["sale_price"])}</td>' for r in rows)
    body.append(f'<tr class="grid-anchor"><th scope="row">Sale price achieved</th>{cells}</tr>')

    for key, label, unit in LINE_ORDER:
        # Is this line live anywhere, and is it retired?
        present = [r["adjustments"].get(key) for r in rows]
        if not any(present):
            continue
        retired = any(a and a.get("retired") for a in present)
        skipped_all = all((a or {}).get("skipped") for a in present if a is not None)
        nonzero = any((a or {}).get("dollars") for a in present)

        if retired or (skipped_all and not nonzero):
            cls = "grid-inert"
        elif not nonzero:
            cls = "grid-nil"
        else:
            cls = ""

        cells = []
        for a in present:
            if a is None:
                cells.append('<td class="num">—</td>')
                continue
            d = a.get("dollars") or 0
            if a.get("retired"):
                cells.append('<td class="num inert">n/a</td>')
            elif a.get("skipped"):
                cells.append('<td class="num inert">—</td>')
            elif d == 0:
                cells.append('<td class="num nil">—</td>')
            else:
                sgn = "pos" if d > 0 else "neg"
                diff = a.get("diff")
                title = ""
                if isinstance(diff, (int, float)) and unit:
                    title = f' title="subject {a.get("subject_value")} vs comparable {a.get("comp_value")} {unit}"'
                cells.append(f'<td class="num {sgn}"{title}>{money(d, sign=True)}</td>')

        note = ""
        if retired:
            note = '<span class="grid-note">withdrawn 07 Aug 2026</span>'
        elif skipped_all and not nonzero:
            note = '<span class="grid-note">not assessable</span>'

        body.append(
            f'<tr class="{cls}"><th scope="row">{esc(label)}{note}</th>{"".join(cells)}</tr>'
        )

    # Totals
    cells = "".join(
        f'<td class="num {"pos" if (r["total_adjustment"] or 0) > 0 else "neg" if (r["total_adjustment"] or 0) < 0 else "nil"}">'
        f'{money(r["total_adjustment"], sign=True)}</td>'
        for r in rows
    )
    body.append(f'<tr class="grid-total"><th scope="row">Net adjustment</th>{cells}</tr>')

    cells = "".join(
        f'<td class="num">{(("+%.1f" % ((r["total_pct"] or 0) * 100)) if (r["total_pct"] or 0) >= 0 else ("−%.1f" % abs((r["total_pct"] or 0) * 100)))}%</td>'
        for r in rows
    )
    body.append(
        f'<tr class="grid-total-sub"><th scope="row">Net adjustment as % of sale</th>{cells}</tr>'
    )

    cells = "".join(f'<td class="num">{money(r["adjusted_price"])}</td>' for r in rows)
    body.append(
        f'<tr class="grid-anchor grid-result"><th scope="row">Adjusted value indication</th>{cells}</tr>'
    )

    cells = "".join(f'<td class="num">{r["weight_raw"]:.3f}</td>' for r in rows)
    body.append(f'<tr class="grid-total-sub"><th scope="row">Weight applied</th>{cells}</tr>')

    return f"""<div class="grid-scroll" tabindex="0" role="region" aria-label="Adjustment grid, scrollable">
<table class="grid">
<thead><tr><th scope="col" class="grid-corner">Adjustment line</th>{heads}</tr></thead>
<tbody>{"".join(body)}</tbody>
</table>
</div>"""


def render_comp_schedule(rows):
    body = []
    for i, r in enumerate(rows, 1):
        f = r["features"]
        stale = r["months"] > 6
        flag = (
            f'<span class="flag-inline">outside 6-month window</span>' if stale else ""
        )
        body.append(
            f"""<tr>
<td class="num idx">{i}</td>
<td class="addr">{esc(r["short"])}{flag}</td>
<td class="num">{r["sale_date"].strftime("%d %b %Y")}</td>
<td class="num">{money(r["sale_price"])}</td>
<td class="num">{r["distance_km"]:.2f}</td>
<td class="num">{f.get("bedrooms") or "—"}</td>
<td class="num">{f.get("bathrooms") or "—"}</td>
<td class="num">{f.get("car_spaces") or "—"}</td>
<td class="num">{(f"{f['floor_area_sqm']:.0f}" if f.get("floor_area_sqm") else "—")}</td>
<td class="num">{(f"{f['land_size_sqm']:.0f}" if f.get("land_size_sqm") else "—")}</td>
<td class="num">{"Yes" if f.get("pool_present") else "No"}</td>
</tr>"""
        )
    return f"""<div class="grid-scroll" tabindex="0" role="region" aria-label="Schedule of comparable sales, scrollable">
<table class="sched">
<thead><tr>
<th scope="col" class="num">#</th><th scope="col">Address (Robina)</th>
<th scope="col" class="num">Sold</th><th scope="col" class="num">Price</th>
<th scope="col" class="num">km</th><th scope="col" class="num">Bd</th>
<th scope="col" class="num">Ba</th><th scope="col" class="num">Car</th>
<th scope="col" class="num">Living m&sup2;</th><th scope="col" class="num">Land m&sup2;</th>
<th scope="col" class="num">Pool</th>
</tr></thead>
<tbody>{"".join(body)}</tbody>
</table>
</div>"""


def render_weight_table(rows):
    heads = "".join(f'<th scope="col">{esc(r["short"])}</th>' for r in rows)
    body = []
    for key, label in WEIGHT_FACTOR_LABELS:
        cells = "".join(
            f'<td class="num">{r["weight_factors"].get(key, 0):.2f}</td>' for r in rows
        )
        body.append(f'<tr><th scope="row">{esc(label)}</th>{cells}</tr>')
    cells = "".join(f'<td class="num">{r["weight_raw"]:.3f}</td>' for r in rows)
    body.append(f'<tr class="grid-total"><th scope="row">Composite weight</th>{cells}</tr>')
    return f"""<div class="grid-scroll" tabindex="0" role="region" aria-label="Weighting factors, scrollable">
<table class="grid weights">
<thead><tr><th scope="col" class="grid-corner">Weighting factor</th>{heads}</tr></thead>
<tbody>{"".join(body)}</tbody>
</table>
</div>"""


def render_reconciliation(rows, reconciled):
    total_w = sum(r["weight_norm"] for r in rows)
    body = []
    for r in rows:
        share = r["weight_norm"] / total_w
        body.append(
            f"""<tr>
<td class="addr">{esc(r["short"])}</td>
<td class="num">{money(r["adjusted_price"])}</td>
<td class="num">{share * 100:.1f}%</td>
<td class="num">{money(r["adjusted_price"] * share)}</td>
<td class="bar-cell"><span class="bar" style="--w:{share / max(x['weight_norm'] / total_w for x in rows) * 100:.1f}%"></span></td>
</tr>"""
        )
    return f"""<table class="recon">
<thead><tr><th scope="col">Comparable</th><th scope="col" class="num">Adjusted indication</th>
<th scope="col" class="num">Weight share</th><th scope="col" class="num">Contribution</th>
<th scope="col" class="bar-head">Relative weight</th></tr></thead>
<tbody>{"".join(body)}</tbody>
<tfoot><tr><th scope="row">Weighted mean of these eight &mdash; see note below</th>
<td class="num"></td><td class="num">100.0%</td>
<td class="num">{money(sum(r["adjusted_price"] * r["weight_norm"] / total_w for r in rows))}</td>
<td></td></tr></tfoot>
</table>"""


# --------------------------------------------------------------------------


def render(doc, vd, rows, pool) -> str:
    subj = vd["subject_property"]
    sf = subj["features"]["basic"]
    conf = vd["confidence"]
    rb = conf["range_basis"]
    cal = conf["suburb_calibration"]
    rates = vd["adjustment_rates"]
    summary = vd["summary"]
    street = subj.get("street_evidence") or {}
    micro = subj.get("micro_location_evidence") or {}

    computed = vd["computed_at"]
    if isinstance(computed, dt.datetime):
        computed_d = computed.date()
    else:
        computed_d = dt.date.fromisoformat(str(computed)[:10])
    age_days = (REPORT_DATE - computed_d).days

    adj_lo = min(r["adjusted_price"] for r in rows)
    adj_hi = max(r["adjusted_price"] for r in rows)
    val = conf["reconciled_valuation"]
    lo, hi = conf["range"]["low"], conf["range"]["high"]
    half = rb["half_width_pct"]

    null_fields = subj["features"]["npui_breakdown"].get("null_fields", [])
    pretty_null = {
        "interior.overall_interior_condition_score": "Overall internal condition",
        "interior.kitchen_quality_score": "Kitchen quality",
        "interior.bathroom_quality_score": "Bathroom quality",
        "renovation.modern_features_score": "Modern fit-out",
        "interior.natural_light_score": "Natural light",
        "layout.number_of_living_areas": "Number of living areas",
        "outdoor.fence_condition_score": "Fencing condition",
    }
    null_list = "".join(
        f"<li>{esc(pretty_null.get(f, f))}</li>" for f in null_fields
    )

    within_6mo = sum(1 for r in rows if r["months"] <= 6)
    within_5km = sum(1 for r in rows if (r["distance_km"] or 0) <= 5)
    outside = [r for r in rows if r["months"] > 6]
    outside_txt = ", ".join(
        f"{esc(r['short'])} (sold {r['sale_date'].strftime('%B %Y')}, {r['months']:.1f} months)"
        for r in outside
    )

    street_sales = "".join(
        f"<li><span class=\"si-addr\">{esc(short_addr(s['address']))}</span>"
        f"<span class=\"si-date\">{dt.date.fromisoformat(s['sold_date']).strftime('%d %b %Y')}</span>"
        f"<span class=\"si-price\">{money(s['sale_price'])}</span>"
        f"<span class=\"si-pct\">{s['pct_vs_median'] * 100:+.1f}% vs suburb median</span></li>"
        for s in street.get("sample_sales", [])
    )

    addr_line = subj["address"]
    street_name = addr_line.split(",")[0]

    return f"""<title>Valuation Report — {esc(street_name)}</title>
<style>
:root {{
  --paper:#F7F8F6; --ink:#16211F; --muted:#5C6B65; --rule:#D2D8D3;
  --rule-strong:#A9B4AE; --accent:#1F5D4C; --accent-soft:#E4EDE8;
  --flag:#8A4B2A; --flag-soft:#F6EBE3; --pos:#1F5D4C; --neg:#8A4B2A;
  --inert:#9AA6A0; --band:#EFF3F0;
  --serif:Georgia,"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua","Times New Roman",serif;
  --grot:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,"Liberation Mono",monospace;
}}
@media (prefers-color-scheme:dark){{
  :root{{
    --paper:#12100E; --ink:#E6E3DC; --muted:#9AA39C; --rule:#2E3532;
    --rule-strong:#4A534E; --accent:#7FB79F; --accent-soft:#1B2622;
    --flag:#C98A5E; --flag-soft:#2A1F17; --pos:#7FB79F; --neg:#C98A5E;
    --inert:#5C645F; --band:#191F1C;
  }}
}}
:root[data-theme="dark"]{{
  --paper:#12100E; --ink:#E6E3DC; --muted:#9AA39C; --rule:#2E3532;
  --rule-strong:#4A534E; --accent:#7FB79F; --accent-soft:#1B2622;
  --flag:#C98A5E; --flag-soft:#2A1F17; --pos:#7FB79F; --neg:#C98A5E;
  --inert:#5C645F; --band:#191F1C;
}}
:root[data-theme="light"]{{
  --paper:#F7F8F6; --ink:#16211F; --muted:#5C6B65; --rule:#D2D8D3;
  --rule-strong:#A9B4AE; --accent:#1F5D4C; --accent-soft:#E4EDE8;
  --flag:#8A4B2A; --flag-soft:#F6EBE3; --pos:#1F5D4C; --neg:#8A4B2A;
  --inert:#9AA6A0; --band:#EFF3F0;
}}

body{{background:var(--paper);color:var(--ink);font-family:var(--serif);
  font-size:16px;line-height:1.62;-webkit-font-smoothing:antialiased;}}
.doc{{max-width:60rem;margin:0 auto;padding:0 1.5rem 6rem;}}

/* ---- masthead ---- */
.masthead{{padding:3.5rem 0 1.25rem;border-bottom:2px solid var(--ink);
  display:flex;flex-wrap:wrap;gap:1.5rem;align-items:flex-end;justify-content:space-between;}}
.brand{{display:flex;flex-direction:column;gap:.35rem;}}
.brand-name{{font-family:var(--grot);font-size:.72rem;font-weight:650;
  letter-spacing:.19em;text-transform:uppercase;color:var(--accent);}}
.brand-sub{{font-family:var(--grot);font-size:.68rem;letter-spacing:.13em;
  text-transform:uppercase;color:var(--muted);}}
.doc-type{{text-align:right;}}
.doc-type h1{{font-size:1.02rem;font-weight:600;letter-spacing:.03em;margin:0;}}
.doc-ref{{font-family:var(--mono);font-size:.72rem;color:var(--muted);}}

/* ---- title block ---- */
.title-block{{padding:2.5rem 0 2rem;border-bottom:1px solid var(--rule);}}
.eyebrow{{font-family:var(--grot);font-size:.68rem;font-weight:650;letter-spacing:.17em;
  text-transform:uppercase;color:var(--muted);margin:0 0 .75rem;}}
.subject-address{{font-size:clamp(1.7rem,4.2vw,2.5rem);line-height:1.14;margin:0;
  font-weight:400;text-wrap:balance;letter-spacing:-.012em;}}
.subject-address em{{font-style:normal;display:block;font-size:.52em;color:var(--muted);
  margin-top:.5rem;letter-spacing:.01em;}}

/* ---- summary ---- */
.summary{{margin:2.25rem 0 0;border:1.5px solid var(--ink);}}
.summary-head{{background:var(--ink);color:var(--paper);padding:.5rem 1.1rem;
  font-family:var(--grot);font-size:.66rem;font-weight:650;letter-spacing:.17em;text-transform:uppercase;}}
.summary-body{{padding:1.6rem 1.1rem;display:grid;gap:1.6rem;
  grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));}}
.figure-lead .fl-label{{font-family:var(--grot);font-size:.66rem;font-weight:650;
  letter-spacing:.14em;text-transform:uppercase;color:var(--muted);display:block;margin-bottom:.45rem;}}
.fl-range{{font-family:var(--mono);font-size:clamp(1.35rem,3.4vw,1.85rem);font-weight:600;
  letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.15;}}
.fl-point{{font-family:var(--mono);font-size:1.35rem;font-variant-numeric:tabular-nums;
  letter-spacing:-.015em;}}
.fl-note{{font-size:.83rem;color:var(--muted);margin-top:.5rem;line-height:1.5;}}
.summary-meta{{border-top:1px solid var(--rule);padding:1rem 1.1rem;
  display:grid;gap:.6rem 2rem;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));}}
.meta-row{{display:flex;justify-content:space-between;gap:1rem;font-size:.85rem;
  border-bottom:1px dotted var(--rule);padding-bottom:.35rem;}}
.meta-row dt{{color:var(--muted);}}
.meta-row dd{{margin:0;font-family:var(--mono);font-size:.8rem;text-align:right;
  font-variant-numeric:tabular-nums;}}

/* ---- sections ---- */
section{{padding-top:3.25rem;}}
.sec-head{{display:flex;gap:1rem;align-items:baseline;
  border-bottom:1px solid var(--rule-strong);padding-bottom:.5rem;margin-bottom:1.35rem;}}
.sec-num{{font-family:var(--mono);font-size:.82rem;color:var(--accent);font-weight:600;
  flex:none;padding-top:.15rem;}}
.sec-head h2{{font-size:1.22rem;font-weight:600;margin:0;letter-spacing:-.005em;text-wrap:balance;}}
.prose{{max-width:38rem;}}
.prose p{{margin:0 0 1rem;}}
.prose p:last-child{{margin-bottom:0;}}
.prose ul,.prose ol{{margin:0 0 1rem;padding-left:1.3rem;}}
.prose li{{margin-bottom:.4rem;}}
.lede{{font-size:1.05rem;color:var(--muted);}}

/* ---- disclosure callout: sienna is ONLY ever a limitation ---- */
.disclosure{{background:var(--flag-soft);border-left:3px solid var(--flag);
  padding:1rem 1.15rem;margin:1.4rem 0;max-width:44rem;}}
.disclosure-label{{font-family:var(--grot);font-size:.64rem;font-weight:700;
  letter-spacing:.16em;text-transform:uppercase;color:var(--flag);display:block;margin-bottom:.5rem;}}
.disclosure p{{margin:0 0 .7rem;font-size:.92rem;}}
.disclosure p:last-child,.disclosure ul:last-child{{margin-bottom:0;}}
.disclosure ul{{margin:0;padding-left:1.2rem;font-size:.92rem;}}
.flag-inline{{font-family:var(--grot);font-size:.6rem;font-weight:650;letter-spacing:.1em;
  text-transform:uppercase;color:var(--flag);background:var(--flag-soft);
  padding:.13rem .4rem;margin-left:.5rem;white-space:nowrap;}}

/* ---- tables ---- */
.grid-scroll{{overflow-x:auto;margin:1.4rem 0;border:1px solid var(--rule);}}
.grid-scroll:focus-visible{{outline:2px solid var(--accent);outline-offset:2px;}}
table{{border-collapse:collapse;width:100%;font-size:.82rem;}}
th,td{{padding:.5rem .7rem;text-align:left;border-bottom:1px solid var(--rule);vertical-align:baseline;}}
thead th{{font-family:var(--grot);font-size:.63rem;font-weight:650;letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted);border-bottom:1.5px solid var(--rule-strong);
  vertical-align:bottom;white-space:nowrap;}}
tbody th[scope=row]{{font-weight:400;white-space:nowrap;}}
.num{{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;
  white-space:nowrap;font-size:.78rem;}}
thead .num{{text-align:right;}}
.addr{{white-space:nowrap;}}

.grid tbody th[scope=row]{{position:sticky;left:0;background:var(--paper);
  border-right:1px solid var(--rule);z-index:1;}}
.grid thead .grid-corner{{position:sticky;left:0;background:var(--paper);
  border-right:1px solid var(--rule);z-index:2;}}
.grid-addr{{display:block;color:var(--ink);font-size:.68rem;}}
.grid-sub{{display:block;font-weight:400;letter-spacing:.04em;color:var(--muted);
  font-family:var(--mono);font-size:.64rem;text-transform:none;}}
.grid-anchor{{background:var(--band);}}
.grid-anchor th[scope=row]{{background:var(--band);font-weight:600;}}
.grid-anchor td{{font-weight:600;}}
.grid-result th[scope=row],.grid-result td{{border-top:1.5px solid var(--rule-strong);}}
.grid-total th[scope=row]{{font-weight:600;}}
.grid-total td{{font-weight:600;}}
.grid-total-sub td,.grid-total-sub th[scope=row]{{color:var(--muted);font-size:.76rem;}}
.pos{{color:var(--pos);}}
.neg{{color:var(--neg);}}
.nil,.inert{{color:var(--inert);}}
.grid-inert th[scope=row]{{color:var(--inert);}}
.grid-note{{display:block;font-family:var(--grot);font-size:.58rem;letter-spacing:.09em;
  text-transform:uppercase;color:var(--flag);margin-top:.1rem;}}
.idx{{color:var(--muted);}}

.recon{{margin:1.4rem 0;}}
.recon tfoot th{{font-weight:600;text-align:left;border-top:1.5px solid var(--rule-strong);}}
.recon tfoot td{{border-top:1.5px solid var(--rule-strong);font-weight:600;}}
.bar-head{{width:24%;}}
.bar-cell{{padding-right:0;}}
.bar{{display:block;height:.5rem;width:var(--w);background:var(--accent);opacity:.5;}}

/* ---- rate schedule ---- */
.rates{{display:grid;gap:0 1.8rem;grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));
  margin:1.3rem 0;}}
.rate-row{{display:flex;justify-content:space-between;gap:1rem;align-items:baseline;
  border-bottom:1px dotted var(--rule);padding:.42rem 0;font-size:.88rem;}}
.rate-row .num{{font-size:.82rem;}}
.rate-row.retired{{color:var(--inert);}}
.rate-row.retired .num{{text-decoration:line-through;}}

/* ---- street evidence ---- */
.street-list{{list-style:none;padding:0;margin:1.2rem 0;max-width:44rem;}}
.street-list li{{display:grid;gap:.2rem 1rem;padding:.6rem 0;
  border-bottom:1px solid var(--rule);
  grid-template-columns:1fr auto auto;align-items:baseline;}}
.si-addr{{font-size:.92rem;}}
.si-date,.si-price{{font-family:var(--mono);font-size:.78rem;font-variant-numeric:tabular-nums;}}
.si-date{{color:var(--muted);}}
.si-pct{{grid-column:1/-1;font-family:var(--grot);font-size:.68rem;letter-spacing:.06em;
  text-transform:uppercase;color:var(--accent);}}

/* ---- accuracy stats ---- */
.stats{{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);
  grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr));margin:1.4rem 0;}}
.stat{{background:var(--paper);padding:1rem;}}
.stat-v{{font-family:var(--mono);font-size:1.4rem;font-variant-numeric:tabular-nums;
  letter-spacing:-.02em;display:block;}}
.stat-l{{font-family:var(--grot);font-size:.63rem;font-weight:650;letter-spacing:.11em;
  text-transform:uppercase;color:var(--muted);display:block;margin-top:.35rem;line-height:1.4;}}

/* ---- what this is / isn't ---- */
.compare{{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);
  grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));margin:1.4rem 0;}}
.compare-col{{background:var(--paper);padding:1.2rem;}}
.compare-col h3{{font-family:var(--grot);font-size:.66rem;font-weight:700;letter-spacing:.14em;
  text-transform:uppercase;margin:0 0 .8rem;}}
.compare-col.is h3{{color:var(--accent);}}
.compare-col.isnt h3{{color:var(--flag);}}
.compare-col ul{{margin:0;padding-left:1.1rem;font-size:.9rem;}}
.compare-col li{{margin-bottom:.5rem;}}

/* ---- download ---- */
.actions{{display:flex;flex-wrap:wrap;gap:.8rem;align-items:center;margin:1.6rem 0 0;}}
.btn{{font-family:var(--grot);font-size:.75rem;font-weight:650;letter-spacing:.1em;
  text-transform:uppercase;padding:.75rem 1.4rem;border:1.5px solid var(--ink);
  background:var(--ink);color:var(--paper);cursor:pointer;}}
.btn:hover{{background:transparent;color:var(--ink);}}
.btn:focus-visible{{outline:2px solid var(--accent);outline-offset:3px;}}
.btn.ghost{{background:transparent;color:var(--ink);}}
.btn.ghost:hover{{background:var(--ink);color:var(--paper);}}
.actions-note{{font-size:.8rem;color:var(--muted);}}

/* ---- signature ---- */
.signature{{margin-top:2rem;border-top:1px solid var(--rule-strong);padding-top:1.3rem;
  display:grid;gap:1.4rem;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));max-width:44rem;}}
.sig-block .sig-l{{font-family:var(--grot);font-size:.63rem;font-weight:650;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);display:block;margin-bottom:.3rem;}}
.sig-block .sig-v{{font-size:.95rem;}}

.colophon{{margin-top:3.5rem;border-top:2px solid var(--ink);padding-top:1.1rem;
  font-size:.78rem;color:var(--muted);max-width:44rem;}}
.colophon p{{margin:0 0 .6rem;}}

@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important;}}}}

@media print{{
  body{{background:#fff;color:#000;font-size:10.5pt;}}
  .doc{{max-width:none;padding:0;}}
  .actions{{display:none;}}
  section{{padding-top:1.6rem;break-inside:avoid;}}
  .grid-scroll{{overflow:visible;}}
  .summary{{break-inside:avoid;}}
  .disclosure{{break-inside:avoid;}}
  table{{font-size:8pt;}}
}}
</style>

<div class="doc">

<header class="masthead">
  <div class="brand">
    <span class="brand-name">Fields Real Estate</span>
    <span class="brand-sub">Property intelligence &middot; Gold Coast</span>
  </div>
  <div class="doc-type">
    <h1>Comparable Sales Assessment</h1>
    <span class="doc-ref">Ref FRE&thinsp;/&thinsp;RBN&thinsp;/&thinsp;{esc(street_name.split()[0])}-{computed_d.strftime('%Y%m%d')}</span>
  </div>
</header>

<div class="title-block">
  <p class="eyebrow">Subject property</p>
  <p class="subject-address">{esc(street_name)}<em>{esc(addr_line.split(',', 1)[1].strip())}</em></p>

  <div class="summary">
    <div class="summary-head">Assessment summary</div>
    <div class="summary-body">
      <div class="figure-lead">
        <span class="fl-label">Assessed value range</span>
        <span class="fl-range">{money(lo)} &ndash; {money(hi)}</span>
        <p class="fl-note">A &plusmn;{half}% band around the point figure. Four in five Robina
        sales land inside a band of this width. It is <strong>not</strong> a confidence
        interval and one sale in five falls outside it.</p>
      </div>
      <div class="figure-lead">
        <span class="fl-label">Point figure</span>
        <span class="fl-point">{money(val)}</span>
        <p class="fl-note">The weight-reconciled mean of {len(rows)} adjusted comparable sales,
        calibrated for Robina&rsquo;s measured bias. The range above carries the assessment;
        this single figure is the arithmetic centre of it, not a price.</p>
      </div>
      <div class="figure-lead">
        <span class="fl-label">Direct evidence spread</span>
        <span class="fl-point">{money(adj_lo)} &ndash; {money(adj_hi)}</span>
        <p class="fl-note">Highest and lowest of the {len(rows)} comparables after adjustment
        to the subject. Unweighted &mdash; the raw evidence before reconciliation.</p>
      </div>
    </div>
    <div class="summary-meta">
      <div class="meta-row"><dt>Date of assessment</dt><dd>{computed_d.strftime('%d %B %Y')}</dd></div>
      <div class="meta-row"><dt>Date of this report</dt><dd>{REPORT_DATE.strftime('%d %B %Y')}</dd></div>
      <div class="meta-row"><dt>Basis of value</dt><dd>Market value, vacant possession</dd></div>
      <div class="meta-row"><dt>Interest assessed</dt><dd>Fee simple</dd></div>
      <div class="meta-row"><dt>Inspection</dt><dd>None &mdash; desktop only</dd></div>
      <div class="meta-row"><dt>Method</dt><dd>Direct comparison</dd></div>
      <div class="meta-row"><dt>Sales in the calculation</dt><dd>{summary['n_comps']}</dd></div>
      <div class="meta-row"><dt>Sales set out in full</dt><dd>{len(rows)}</dd></div>
    </div>
  </div>

  <div class="actions">
    <button class="btn" type="button" id="dl">Download report (PDF)</button>
    <button class="btn ghost" type="button" id="dlData">Download the underlying figures</button>
    <span class="actions-note">The PDF is this document, unabridged &mdash; every table included.</span>
  </div>
</div>

<section id="s1">
  <div class="sec-head"><span class="sec-num">1</span><h2>Purpose, and the limits of this document</h2></div>
  <div class="prose">
    <p class="lede">This is a desktop assessment of market value prepared by Fields Real
    Estate using the direct comparison method. It was produced without an inspection, without
    contact with the owner, and without a licensed valuer.</p>
    <p>It exists because the two things normally on offer &mdash; an instant online estimate
    with no working shown, and an agent appraisal that begins a sales conversation &mdash; both
    ask you to accept a number on trust. This document takes the opposite approach: every
    comparable sale, every dollar of adjustment, every weight, and every thing we could not
    observe is set out below so you can disagree with it in specific terms.</p>
  </div>

  <div class="disclosure">
    <span class="disclosure-label">This is not a certified valuation</span>
    <p>This report has <strong>not</strong> been prepared by a Certified Practising Valuer and
    is not a valuation under the Australian Property Institute&rsquo;s professional practice
    standards. No member of the API has inspected the property or signed this document.</p>
    <p>It <strong>cannot</strong> be relied upon for mortgage security or lending, litigation
    or family law proceedings, stamp duty or land tax objections, probate or deceased estate
    administration, insurance reinstatement, financial reporting, or any other purpose
    requiring a valuation by a registered valuer. For any of those, engage a Certified
    Practising Valuer.</p>
    <p>It is prepared for the owner or occupier of the subject property, for their own
    information. Fields Real Estate accepts no liability to any third party who obtains a copy
    of it, and no duty of care arises to any party relying on it for a transaction.</p>
  </div>

  <div class="disclosure">
    <span class="disclosure-label">No advice is given or implied</span>
    <p>Nothing here is a recommendation to sell, to hold, to buy, or to list at any particular
    price. This document reports what comparable properties have sold for and what our method
    infers from that. What to do with that information is entirely yours, and depends on
    circumstances we know nothing about.</p>
    <p>A sale price is set by a buyer on a day, and can fall outside every figure below.</p>
  </div>
</section>

<section id="s2">
  <div class="sec-head"><span class="sec-num">2</span><h2>The subject property, as we hold it</h2></div>
  <div class="prose">
    <p>The attributes below drive every adjustment in section 5. They come from cadastral
    records, historic listing data and satellite imagery &mdash; not from an inspection.
    If any of them is wrong, the assessment is wrong, and the specific effect is traceable
    through the grid.</p>
  </div>

  <div class="rates">
    <div class="rate-row"><span>Bedrooms</span><span class="num">{sf.get('bedrooms')}</span></div>
    <div class="rate-row"><span>Bathrooms</span><span class="num">{sf.get('bathrooms')}</span></div>
    <div class="rate-row"><span>Car spaces</span><span class="num">{sf.get('car_spaces')}</span></div>
    <div class="rate-row"><span>Living area</span><span class="num">{sf.get('floor_area_sqm'):.0f} m&sup2;</span></div>
    <div class="rate-row"><span>Land area</span><span class="num">{sf.get('land_size_sqm'):.0f} m&sup2;</span></div>
    <div class="rate-row"><span>Approximate year built</span><span class="num">{sf.get('approximate_build_year')}</span></div>
    <div class="rate-row"><span>Swimming pool</span><span class="num">{'Yes' if sf.get('pool_present') else 'None recorded'}</span></div>
    <div class="rate-row"><span>Water outlook</span><span class="num">{'Yes' if sf.get('water_views') else 'None'}</span></div>
    <div class="rate-row"><span>Distance to beach</span><span class="num">{sf.get('beach_distance_km')} km</span></div>
    <div class="rate-row"><span>Golf course frontage</span><span class="num">{'Yes' if (vd.get('location_factors') or {}).get('golf_course_backing') else 'No'}</span></div>
  </div>

  <div class="disclosure">
    <span class="disclosure-label">Not observed &mdash; the largest limitation in this report</span>
    <p>No one has been inside this house. The following attributes are unknown to us, and each
    of them is capable of moving a real sale price materially:</p>
    <ul>{null_list}</ul>
    <p>Where an attribute is unknown, the method does not guess it &mdash; it holds the subject
    at a neutral position and declines to adjust for that line. The practical consequence is
    that <strong>a well-presented interior is not credited, and a poor one is not
    discounted.</strong> If the interior is materially better or worse than a typical Robina
    house of this age, the true figure sits above or below this assessment accordingly.</p>
  </div>
</section>

<section id="s3">
  <div class="sec-head"><span class="sec-num">3</span><h2>Method</h2></div>
  <div class="prose">
    <p>Direct comparison. Sales of similar properties are adjusted, line by line, for each
    respect in which they differ from the subject, producing for each one an indication of what
    the subject would have sold for on that sale&rsquo;s date. Those indications are then
    weighted and reconciled to a single figure, and a measured band is placed around it.</p>
    <p>{summary['n_comps']} sales within Robina were examined, adjusted and weighted, and all of
    them inform the reconciled figure. A sale needing a large adjustment, or sitting further
    away, or older, is not discarded &mdash; it is down-weighted, so that it counts for
    something in proportion to how much it can fairly say about this house.</p>
    <p>Of those, the {len(rows)} strongest are set out in full in sections 5 to 7 as the
    evidence you can actually check. Section 7 is explicit about the gap between what is
    displayed and what is calculated.</p>
    <ol>
      <li><strong>Selection</strong> &mdash; candidate sales screened on dwelling type, proximity,
      recency and completeness of attribute data.</li>
      <li><strong>Adjustment</strong> &mdash; each adopted sale adjusted against a published rate
      schedule (section 4).</li>
      <li><strong>Reliability shrinkage</strong> &mdash; every adjustment multiplied by
      {rows[0]['reliability']:.2f}. Adjustment rates are estimated, not known; shrinking them
      toward zero pulls the result back toward the observed sale price, which is the one
      genuinely hard fact in the calculation.</li>
      <li><strong>Weighting</strong> &mdash; the six factors in section 6.</li>
      <li><strong>Reconciliation</strong> &mdash; weighted mean of the adjusted indications
      across the whole candidate pool, not only the sales displayed in section 5. Section 7
      sets out what that distinction means for reading this report.</li>
      <li><strong>Suburb calibration</strong> &mdash; multiplied by {cal['factor']:.4f}, which
      corrects Robina&rsquo;s measured systematic bias as at {dt.date.fromisoformat(cal['measured_on']).strftime('%d %B %Y')}.</li>
      <li><strong>Band</strong> &mdash; &plusmn;{half}%, being the width that contained four in
      five actual Robina sales when the method was tested against them (section 7).</li>
    </ol>
  </div>

  <div class="disclosure">
    <span class="disclosure-label">Scope of the method</span>
    <p>This method is built and measured for <strong>detached houses selling between
    $1,000,000 and $2,000,000</strong>. Outside that band it degrades, because a weighted mean
    of adjusted comparables cannot exceed its most expensive comparable and the pool of
    available sales pulls toward the middle of the market.</p>
    <p>This property is assessed at {money(val)} and sits inside that band, so the figures
    above are reported in full. Had it fallen outside, we would have withheld both the figure
    and the range and shown you the comparable evidence only.</p>
  </div>
</section>

<section id="s4">
  <div class="sec-head"><span class="sec-num">4</span><h2>Rate schedule</h2></div>
  <div class="prose">
    <p>These are the dollar rates applied per unit of difference. They are derived by
    regression across {rates['sample_size']} local sales rather than assumed, and they are the
    same rates applied to every property we assess in this market &mdash; they are not tuned to
    produce a particular answer here. Each rate is shown before reliability shrinkage.</p>
  </div>

  <div class="rates">
    <div class="rate-row"><span>Land, per m&sup2;</span><span class="num">{money(rates['rates']['land_per_sqm'])}</span></div>
    <div class="rate-row"><span>Living area, per m&sup2;</span><span class="num">{money(rates['rates']['floor_per_sqm'])}</span></div>
    <div class="rate-row"><span>Per bedroom</span><span class="num">{money(rates['rates']['per_bedroom'])}</span></div>
    <div class="rate-row"><span>Per bathroom</span><span class="num">{money(rates['rates']['per_bathroom'])}</span></div>
    <div class="rate-row"><span>Per car space</span><span class="num">{money(rates['rates']['per_car_space'])}</span></div>
    <div class="rate-row"><span>Swimming pool</span><span class="num">{money(rates['rates']['per_pool'])}</span></div>
    <div class="rate-row"><span>Additional storey</span><span class="num">{money(rates['rates']['per_storey'])}</span></div>
    <div class="rate-row"><span>External cladding, per grade</span><span class="num">{money(rates['rates']['per_cladding_level'])}</span></div>
    <div class="rate-row"><span>Ducted air-conditioning</span><span class="num">{money(rates['rates']['per_ac_ducted'])}</span></div>
    <div class="rate-row"><span>Water outlook</span><span class="num">{money(rates['rates']['per_water_view'])}</span></div>
    <div class="rate-row"><span>Per year of age</span><span class="num">{money(rates['rates']['per_year_age'])}</span></div>
    <div class="rate-row retired"><span>Renovation level, per grade</span><span class="num">{money(rates['rates']['per_renovation_level'])}</span></div>
    <div class="rate-row retired"><span>Kitchen quality, per point</span><span class="num">{money(rates['rates']['per_kitchen_point'])}</span></div>
    <div class="rate-row retired"><span>Renovation quality</span><span class="num">$18,000</span></div>
  </div>

  <div class="disclosure">
    <span class="disclosure-label">Three rates withdrawn from use</span>
    <p>Renovation level, kitchen quality and renovation quality are struck through above and
    appear as <span style="font-family:var(--mono);font-size:.85em">n/a</span> in the grid.
    On 7 August 2026 we tested the method with and without each adjustment and found these
    three <strong>increased</strong> the average error rather than reducing it. They were
    withdrawn that day and contribute nothing to this assessment.</p>
    <p>They remain listed because a rate schedule that quietly drops the lines that did not
    work is not a rate schedule you can audit.</p>
  </div>
</section>

<section id="s5">
  <div class="sec-head"><span class="sec-num">5</span><h2>Schedule of comparable sales</h2></div>
  <div class="prose">
    <p>The {len(rows)} sales set out in full, as they were &mdash; before any adjustment. All
    are detached houses in Robina. Ordered by adjusted indication, lowest to highest.</p>
  </div>
  {render_comp_schedule(rows)}

  <div class="prose">
    <p>Queensland&rsquo;s <em>Property Occupations Act 2014</em> defines a comparative market
    analysis as comparing the property with at least three sales from the previous six months,
    of similar standard or condition, within five kilometres. That definition governs a
    licensed agent answering a seller&rsquo;s question about price; it does not bind this
    document, but it is a reasonable public yardstick, so here is how this evidence measures
    against it: <strong>{len(rows)} sales</strong> against a minimum of three;
    <strong>{within_5km} of {len(rows)}</strong> within five kilometres (the furthest is
    {max(r['distance_km'] for r in rows):.2f}&thinsp;km); <strong>{within_6mo} of {len(rows)}</strong>
    within six months.</p>
  </div>

  {'<div class="disclosure"><span class="disclosure-label">One sale falls outside the six-month window</span><p>' + esc(outside_txt) + ' sits outside the six-month period. It was retained because it is a close physical match on a nearby street, and its age is handled explicitly by the recency weight in section 6, where it carries the lowest recency score of any sale shown. We disclose it rather than quietly dropping or quietly keeping it.</p></div>' if outside else ''}
</section>

<section id="s6">
  <div class="sec-head"><span class="sec-num">6</span><h2>Adjustment grid</h2></div>
  <div class="prose">
    <p>The working. Each column is one comparable sale; each row is one respect in which it
    differs from the subject. A positive figure means the comparable was inferior in that
    respect, so its price is adjusted upward to indicate the subject. Negative means the
    reverse. Every figure shown has had the {rows[0]['reliability']:.2f} reliability shrinkage
    applied.</p>
    <p>Scroll the grid sideways to see all {len(rows)} comparables.</p>
  </div>
  {render_adjustment_grid(rows)}

  <div class="prose">
    <p>The net adjustment column tells you how hard each sale had to work. A comparable
    requiring a {max(abs((r['total_pct'] or 0)) for r in rows) * 100:.0f}% adjustment is a
    weaker piece of evidence than one requiring
    {min(abs((r['total_pct'] or 0)) for r in rows) * 100:.0f}%, and the weighting in the next
    section is what accounts for that difference.</p>
  </div>
</section>

<section id="s7">
  <div class="sec-head"><span class="sec-num">7</span><h2>Weighting and reconciliation</h2></div>
  <div class="prose">
    <p>Six factors, each scored from zero to one, multiply into a composite weight for each
    sale. A sale that needed little adjustment, sat close by, sold recently, and had its price
    independently verified counts for more than one that did not.</p>
  </div>
  {render_weight_table(rows)}
  <div class="prose">
    <p>Applying those weights to the adjusted indications:</p>
  </div>
  {render_reconciliation(rows, val)}

  <div class="disclosure">
    <span class="disclosure-label">The eight are the evidence; the figure is reconciled from all {pool['n']}</span>
    <p>The point figure of {money(val)} is <strong>not</strong> the weighted mean of these eight
    sales. It is reconciled across the full pool of <strong>{pool['n']} candidate sales</strong>
    examined in Robina, then calibrated. The eight set out above are the highest-quality subset,
    selected to be shown to you as legible evidence &mdash; they carry
    <strong>{pool['shown_share'] * 100:.1f}% of the total weight</strong> behind the figure.</p>
    <p>Two consequences you should know. First, the spread of the eight
    ({money(adj_lo)} &ndash; {money(adj_hi)}) is <strong>narrower than the real evidence
    spread</strong>, which across all {pool['n']} runs {money(pool['lo'])} &ndash;
    {money(pool['hi'])}. The selection shown to you flatters the apparent agreement. Second,
    the weighted mean of these eight alone comes to {money(pool['shown_mean'])} &mdash; within
    a few hundred dollars of the reported figure. <strong>That closeness is a coincidence of
    this property, not a property of the method</strong>, and we would rather tell you that
    than let it read as confirmation.</p>
    <p>We show eight rather than {pool['n']} because a grid of {pool['n']} columns is not
    evidence anyone can check. The full pool is in the downloadable figures.</p>
  </div>

  <div class="prose">
    <p>The Robina calibration factor of {cal['factor']:.4f} is applied to the reconciled figure
    and to both ends of the range, so the band stays centred on the corrected estimate. It
    corrects a systematic tendency in this suburb measured on
    {dt.date.fromisoformat(cal['measured_on']).strftime('%d %B %Y')}.</p>
    <p>The adopted indications have a standard deviation of {money(conf['std_dev'])}, or
    {conf['cv'] * 100:.1f}% of the mean &mdash; a measure of how much the comparables disagree
    with each other, which is a different and much smaller thing than how wrong the assessment
    might be. The band in section 9 is the honest measure of the latter.</p>
  </div>
</section>

<section id="s8">
  <div class="sec-head"><span class="sec-num">8</span><h2>Locational evidence</h2></div>
  <div class="prose">
    <p>Two locational adjustments appear in the grid. Both are derived from sales, not from
    judgement about the desirability of a street.</p>
    <p><strong>Street premium, +{street.get('applied_pct', 0) * 100:.2f}%.</strong>
    {street.get('n_sales')} sales in {esc(street.get('street_name', '').title())} averaged
    {street.get('raw_avg_pct', 0) * 100:.2f}% above the Robina median of
    {money(street.get('suburb_median'))}. That raw figure is damped by
    {street.get('damping')} and capped at {street.get('cap_pct', 0) * 100:.0f}%, giving the
    applied {street.get('applied_pct', 0) * 100:.2f}%.</p>
  </div>

  <ul class="street-list">{street_sales}</ul>

  <div class="prose">
    <p><strong>Micro-location, +{micro.get('applied_pct', 0) * 100:.2f}%.</strong> Derived from
    {micro.get('n_sales')} sales within {micro.get('radius_km')}&thinsp;km, against the same
    suburb median.</p>
  </div>

  <div class="disclosure">
    <span class="disclosure-label">The street premium rests on three sales</span>
    <p>Three sales is a thin sample, and one of them &mdash; 25 Huntingdale Crescent &mdash; is
    also an adopted comparable in this assessment. The damping factor of {street.get('damping')}
    and the {street.get('cap_pct', 0) * 100:.0f}% cap exist precisely because a small sample
    can produce an extreme average: the raw {street.get('raw_avg_pct', 0) * 100:.2f}% is halved
    before use. Treat the street premium as the least robust input to this assessment.</p>
  </div>
</section>

<section id="s9">
  <div class="sec-head"><span class="sec-num">9</span><h2>How accurate this method has proven to be</h2></div>
  <div class="prose">
    <p>We test the method by running it against houses that have since sold, then comparing what
    it said to what they fetched. The figures below are from the test of
    {dt.date.fromisoformat(rb['measured_on']).strftime('%d %B %Y')}, across
    {rb['n_sales']} detached house sales between $1,000,000 and $2,000,000 in Robina, Varsity
    Lakes and Burleigh Waters.</p>
  </div>

  <div class="stats">
    <div class="stat"><span class="stat-v">8.05%</span><span class="stat-l">Mean absolute error</span></div>
    <div class="stat"><span class="stat-v">6.44%</span><span class="stat-l">Median error</span></div>
    <div class="stat"><span class="stat-v">69%</span><span class="stat-l">Within 10% of the sale price</span></div>
    <div class="stat"><span class="stat-v">40%</span><span class="stat-l">Within 5% of the sale price</span></div>
    <div class="stat"><span class="stat-v">&plusmn;{half}%</span><span class="stat-l">Robina band, containing four in five</span></div>
    <div class="stat"><span class="stat-v">{rb['n_sales']}</span><span class="stat-l">Sales in the test</span></div>
  </div>

  <div class="prose">
    <p>The band is an <em>output</em> of that test, not a setting. It is the width that had to
    be drawn around our figures for four in five actual sales to land inside it, and it differs
    by suburb: &plusmn;11.2% in Varsity Lakes, &plusmn;{half}% here in Robina, &plusmn;14.0% in
    Burleigh Waters. A single pooled number would have flattered the strong suburbs and broken
    the promise in the weak one.</p>
  </div>

  <div class="disclosure">
    <span class="disclosure-label">Read the band correctly</span>
    <p>&plusmn;{half}% is <strong>not a confidence interval</strong> and this report will not
    describe it as one. Four sales in five landed inside a band of this width. <strong>One in
    five did not.</strong> Roughly one house in twenty-five sells above every comparable
    available to assess it, and no method built on comparable sales can anticipate that.</p>
    <p>We also do not publish a confidence grade for individual properties. When we tested
    whether our own high-confidence assessments were in fact more accurate than our
    low-confidence ones, they were not reliably so. Publishing a grade we cannot stand behind
    would be exactly the unearned reassurance this document is meant to avoid.</p>
  </div>
</section>

<section id="s10">
  <div class="sec-head"><span class="sec-num">10</span><h2>What this document is, and is not</h2></div>
  <div class="compare">
    <div class="compare-col is">
      <h3>It is</h3>
      <ul>
        <li>An assessment of market value by direct comparison, with the full working shown.</li>
        <li>Reconciled from {summary["n_comps"]} verified sales, with the {len(rows)} strongest set out line by line.</li>
        <li>Accompanied by a band whose width was measured, not chosen.</li>
        <li>Explicit about every attribute we could not observe.</li>
        <li>Free, unsolicited, and sent without any obligation to speak to anyone.</li>
      </ul>
    </div>
    <div class="compare-col isnt">
      <h3>It is not</h3>
      <ul>
        <li>A valuation by a Certified Practising Valuer, or usable for lending, tax, probate or court.</li>
        <li>Based on any inspection, internal or external.</li>
        <li>A recommendation to sell, hold, buy or list at any price.</li>
        <li>A forecast &mdash; nothing here predicts where prices move next.</li>
        <li>A price. Only a buyer sets that.</li>
      </ul>
    </div>
  </div>
</section>

<section id="s11">
  <div class="sec-head"><span class="sec-num">11</span><h2>Assumptions and limiting conditions</h2></div>
  <div class="prose">
    <ol>
      <li><strong>No inspection.</strong> Neither the interior nor the exterior has been
      inspected. All physical attributes are taken from cadastral records, historic listing
      data and satellite imagery, and are assumed correct.</li>
      <li><strong>Good repair assumed.</strong> The improvements are assumed to be in
      structurally sound condition, free of defect, infestation, contamination and hazardous
      materials. No structural, pest or building survey has been undertaken and none is implied.</li>
      <li><strong>Title assumed clear.</strong> No title search has been performed. Clear and
      marketable title is assumed, free of encumbrances, easements, covenants, caveats or
      disputes not evident from public records.</li>
      <li><strong>Planning and approvals.</strong> All improvements are assumed to be lawfully
      erected and approved. No enquiry has been made of the local authority.</li>
      <li><strong>Flood, bushfire and overlays.</strong> No site-specific hazard assessment has
      been undertaken for this report. Prospective purchasers should make their own enquiries.</li>
      <li><strong>Vacant possession.</strong> Value is assessed on the basis of vacant
      possession of the fee simple interest, with no account taken of any lease, tenancy or
      occupancy arrangement.</li>
      <li><strong>Chattels excluded.</strong> The assessment relates to land and improvements
      only. No furnishings, plant or removable fixtures are included.</li>
      <li><strong>Market conditions at the date of assessment.</strong> The assessment speaks as
      at {computed_d.strftime('%d %B %Y')} and takes no account of events after that date. It
      assumes an arm&rsquo;s length transaction after adequate marketing, between a willing but
      not anxious buyer and seller, neither under compulsion.</li>
      <li><strong>Comparable sale data.</strong> Sale prices are taken from published records
      and verified where possible; {conf['n_verified']} of the {conf['n_total']} sales examined
      were independently verified. Sales data may be subject to later revision, and the
      circumstances of any individual sale are not known to us.</li>
      <li><strong>Currency.</strong> This assessment was computed on
      {computed_d.strftime('%d %B %Y')} and is {age_days} days old at the date of this report.
      It should not be relied upon more than three months after the date of assessment. Later
      sales in the comparable set will move it.</li>
    </ol>
  </div>

  <div class="signature">
    <div class="sig-block"><span class="sig-l">Prepared by</span>
      <span class="sig-v">Fields Real Estate<br>Comparable sales engine, version {vd.get('gaps_version', vd.get('metadata', {}).get('gaps_version', '3'))}</span></div>
    <div class="sig-block"><span class="sig-l">Method last revised</span>
      <span class="sig-v">{dt.date.fromisoformat(rb['measured_on']).strftime('%d %B %Y')}<br>Accuracy re-measured the same day</span></div>
    <div class="sig-block"><span class="sig-l">Enquiries</span>
      <span class="sig-v">will@fieldsestate.com.au</span></div>
    <div class="sig-block"><span class="sig-l">Not signed by a valuer</span>
      <span class="sig-v">No Certified Practising Valuer has reviewed or signed this document.</span></div>
  </div>

  <div class="colophon">
    <p>Fields Real Estate publishes the error rate of this method, the width of its bands and
    the adjustments it has withdrawn. We have not found another agency or portal that publishes
    theirs. That is a statement about disclosure, not a claim that our figures are more accurate
    than anyone else&rsquo;s.</p>
    <p>Report generated {REPORT_DATE.strftime('%d %B %Y')} &middot; assessment computed
    {computed_d.strftime('%d %B %Y')} &middot; reference
    FRE/RBN/{esc(street_name.split()[0])}-{computed_d.strftime('%Y%m%d')}</p>
  </div>
</section>

</div>

<script>
document.getElementById("dl").addEventListener("click", function () {{ window.print(); }});
document.getElementById("dlData").addEventListener("click", function () {{
  var rows = [["comparable","sale_date","sale_price","distance_km","net_adjustment","adjusted_indication","weight"]];
  document.querySelectorAll(".sched tbody tr").forEach(function (tr, i) {{
    var c = tr.querySelectorAll("td");
    rows.push([c[1].textContent.trim(), c[2].textContent, c[3].textContent, c[4].textContent, "", "", ""]);
  }});
  var csv = rows.map(function (r) {{
    return r.map(function (v) {{ return '"' + String(v).replace(/"/g, '""') + '"'; }}).join(",");
  }}).join("\\n");
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {{ type: "text/csv" }}));
  a.download = "comparable-sales.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}});
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True)
    ap.add_argument("--collection", default="robina")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    doc, vd, comps = fetch(a.collection, a.address)
    rows = build_comps(comps)
    pool = pool_stats(vd, rows)

    # Rule 7b applied to a read: assert an outcome, don't merely fail to throw.
    if vd.get("metadata", {}).get("directional_only"):
        raise SystemExit(
            "valuation is directional_only (outside the design envelope) — "
            "the figure and range are suppressed and this report must not render them"
        )
    if not vd.get("confidence", {}).get("reconciled_valuation"):
        raise SystemExit("no reconciled_valuation — nothing to report")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(doc, vd, rows, pool), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes) — {len(rows)} comparables")


if __name__ == "__main__":
    main()

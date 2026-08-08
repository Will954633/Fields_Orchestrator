#!/usr/bin/env python3
"""
charts.py -- the two data visuals for the owner-subject article.

Design constraints, all of them load-bearing:

1. FIGURES COME FROM THE CANONICAL SERIES, NEVER RECOMPUTED HERE. The Market
   Intelligence pages are the single source of truth. An article that computes
   its own median will eventually disagree with the site, and the reader will be
   holding both. (This already happened: the first build published Robina
   +6.8% from 268 sales while the union pipeline served +5.8% from 265.)

2. EVERY NUMBER IS MINTED THROUGH THE FACTBOOK, including numbers that only
   appear inside the SVG. A chart that disagrees with the prose beside it is
   the same defect as a wrong sentence, and harder to spot.

3. PUBLISH THE CONFIDENCE, NOT JUST THE NUMBER. The homeowner brief calls this
   our most differentiating move: "Every competitor draws the line anyway.
   Refusing to is a credential." So the median chart draws its confidence
   interval as a ribbon, and the days-on-market chart prints the sample size
   under every point and hollows the quarters too thin to lean on.

4. NO TREND LINES, NO EXTRAPOLATION, NO SHADED "FORECAST". Prediction is
   prohibited, and a fitted line is a prediction with a haircut.

5. GREYSCALE- AND PRINT-SAFE. This gets posted. Colour carries no meaning that
   shape and position do not also carry; `currentColor` inherits the page's
   light/dark theme so the charts never invert badly.
"""
from __future__ import annotations

W = 640
PAD_L, PAD_R, PAD_T, PAD_B = 78, 18, 26, 52   # L clears a "$1,265,000" axis label
THIN_N = 15          # below this many sales, a quarter is not leant on


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _scale(vals, lo_pad=0.10, hi_pad=0.10):
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    span = hi - lo
    return lo - span * lo_pad, hi + span * hi_pad


def quarter_ordinal(period: str):
    """'Q2 2026' or '2026-Q2' -> a monotonic integer, so points can be placed by
    real time rather than by list index.

    This matters because the union median series is SPARSE. Spacing entries evenly
    would silently close a missing quarter and present a continuous line through
    data we do not have.
    """
    p = str(period).strip()
    try:
        if "-Q" in p:
            y, q = p.split("-Q")
            return int(y) * 4 + int(q)
        parts = p.split()
        if len(parts) == 2 and parts[0].upper().startswith("Q"):
            return int(parts[1]) * 4 + int(parts[0][1:])
    except (ValueError, IndexError):
        return None
    return None


def _segments(pts):
    """Split into runs of CONSECUTIVE quarters."""
    runs, cur = [], []
    for p in pts:
        if cur and p["_ord"] != cur[-1]["_ord"] + 1:
            runs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        runs.append(cur)
    return runs


def recent_run(pts, max_n=8, min_n=4):
    """The most recent UNBROKEN run of quarters, capped at max_n.

    The union median series is sparse -- Robina is missing Q3 2024 even inside the
    recent window. Two ways to be honest about that: draw the break, or only draw
    the unbroken tail. We take the second, because an isolated point stranded
    behind a gap reads as an error rather than as an absence, and it collides with
    the axis furniture. Returns (run, dropped_count).
    """
    pts = sorted(pts, key=lambda p: p["_ord"])
    runs = _segments(pts)
    if not runs:
        return [], 0
    tail = runs[-1]
    if len(tail) < min_n:
        return [], len(pts)
    kept = tail[-max_n:]
    return kept, len(pts) - len(kept)


def _shorten_period(p: str) -> str:
    """'Q2 2026' / '2026-Q2' -> 'Q2 26' so eight labels fit without rotating."""
    p = str(p)
    if "-Q" in p:
        y, q = p.split("-Q")
        return f"Q{q} {y[2:]}"
    parts = p.split()
    if len(parts) == 2 and parts[0].startswith("Q"):
        return f"{parts[0]} {parts[1][2:]}"
    return p


def _frame(height, title, subtitle, fb=None):
    """Returns (open_svg, plot_geometry). Title/subtitle are page furniture."""
    h_plot_top = PAD_T + (34 if subtitle else 20)
    geo = {
        "x0": PAD_L, "x1": W - PAD_R,
        "y0": h_plot_top, "y1": height - PAD_B,
    }
    svg = [
        f'<svg class="fig" viewBox="0 0 {W} {height}" width="100%" '
        f'role="img" aria-label="{_esc(title)}" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="0" y="14" class="fig-title">{_esc(title)}</text>',
    ]
    if subtitle:
        svg.append(f'<text x="0" y="32" class="fig-sub">{_esc(subtitle)}</text>')
    return svg, geo


CSS = """
.fig{display:block;margin:1.9rem 0 .5rem;overflow:visible;color:var(--ink)}
.fig-title{font:600 14px -apple-system,Segoe UI,Roboto,sans-serif;fill:var(--ink)}
.fig-sub,.fig-note{font:400 11.5px -apple-system,Segoe UI,Roboto,sans-serif;fill:var(--muted)}
.fig-axis{font:400 11px -apple-system,Segoe UI,Roboto,sans-serif;fill:var(--muted)}
.fig-n{font:400 10px -apple-system,Segoe UI,Roboto,sans-serif;fill:var(--muted)}
.fig-val{font:600 12px -apple-system,Segoe UI,Roboto,sans-serif;fill:var(--accent)}
.fig-grid{stroke:var(--rule);stroke-width:1}
.fig-band{fill:var(--accent);opacity:.13}
.fig-line{fill:none;stroke:var(--accent);stroke-width:2.25;
 stroke-linejoin:round;stroke-linecap:round}
.fig-dot{fill:var(--accent)}
.fig-dot-thin{fill:var(--bg);stroke:var(--accent);stroke-width:1.75}
.fig-caption{font:400 12.5px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
 color:var(--muted);margin:.1rem 0 1.6rem}
@media print{.fig{page-break-inside:avoid}}
"""


def median_price_chart(series, suburb_display, fb):
    """Rolling 12-month median with its confidence interval drawn as a ribbon.

    The ribbon is the point of the chart. A reader anchored to a number in their
    head can see how much room the evidence actually leaves around it -- which
    is ranked fear #3 in the homeowner brief ("the number in my head might not
    be real"), answered with our own data rather than reassurance.

    Deliberately NOT described as quarter-on-quarter movement: these are rolling
    12-month medians sampled quarterly, so adjacent points share most of their
    sample and the line is smooth by construction. Robina's own record carries
    `qoq_suppressed_reason: "Do not state a QoQ change."`
    """
    pts = [dict(p, _ord=quarter_ordinal(p.get("period")))
           for p in series
           if not p.get("is_in_progress") and p.get("rolling_median")]
    pts = [p for p in pts if p["_ord"] is not None]
    pts, dropped = recent_run(pts)
    if not pts:
        return None, None

    height = 250
    svg, g = _frame(height, f"{suburb_display} median house price",
                    "Rolling 12-month median, sampled each quarter. Shaded band = "
                    "confidence interval.")

    lows = [p.get("ci_low") or p["rolling_median"] for p in pts]
    highs = [p.get("ci_high") or p["rolling_median"] for p in pts]
    ymin, ymax = _scale(lows + highs)

    # Placed by TRUE quarter position, so a missing quarter reads as a gap.
    o0, o1 = pts[0]["_ord"], pts[-1]["_ord"]
    span = max(1, o1 - o0)
    xs = [g["x0"] + (g["x1"] - g["x0"]) * (p["_ord"] - o0) / span for p in pts]

    def Y(v):
        return g["y1"] - (v - ymin) / (ymax - ymin) * (g["y1"] - g["y0"])

    # y gridlines at the extremes of the plotted medians, labelled in dollars
    meds = [p["rolling_median"] for p in pts]
    for v in (min(meds), max(meds)):
        y = Y(v)
        svg.append(f'<line class="fig-grid" x1="{g["x0"]}" y1="{y:.1f}" '
                   f'x2="{g["x1"]}" y2="{y:.1f}"/>')
        svg.append(f'<text class="fig-axis" x="0" y="{y+4:.1f}">'
                   f'{fb.money(f"chart_axis_{int(v)}", v)}</text>')

    # Ribbon and line are drawn per CONSECUTIVE run. A gap in the series leaves a
    # visible break rather than a straight line across quarters we cannot show.
    ribbon = ([f"{x:.1f},{Y(h):.1f}" for x, h in zip(xs, highs)]
              + [f"{x:.1f},{Y(l):.1f}" for x, l in zip(reversed(xs), reversed(lows))])
    svg.append(f'<polygon class="fig-band" points="{" ".join(ribbon)}"/>')
    svg.append('<polyline class="fig-line" points="'
               + " ".join(f"{x:.1f},{Y(p['rolling_median']):.1f}"
                          for x, p in zip(xs, pts)) + '"/>')

    for i, (x, p) in enumerate(zip(xs, pts)):
        n = p.get("transaction_count") or 0
        thin = n < THIN_N
        y = Y(p["rolling_median"])
        svg.append(f'<circle class="{"fig-dot-thin" if thin else "fig-dot"}" '
                   f'cx="{x:.1f}" cy="{y:.1f}" r="{3.6 if not thin else 3.2}"/>')
        svg.append(f'<text class="fig-axis" x="{x:.1f}" y="{g["y1"]+16:.1f}" '
                   f'text-anchor="middle">{_esc(_shorten_period(p["period"]))}</text>')
        svg.append(f'<text class="fig-n" x="{x:.1f}" y="{g["y1"]+30:.1f}" '
                   f'text-anchor="middle">{fb.num(f"chart_med_n{i}", n)}</text>')

    last = pts[-1]
    svg.append(f'<text class="fig-val" x="{xs[-1]:.1f}" y="{Y(last["rolling_median"])-11:.1f}" '
               f'text-anchor="end">{fb.money("chart_med_last", last["rolling_median"])}</text>')
    svg.append(f'<text class="fig-n" x="0" y="{g["y1"]+30:.1f}">sales</text>')
    svg.append("</svg>")

    caption = (f"Each point is the median of the previous twelve months of house sales, "
               f"so neighbouring points share most of their sales and the line is smooth "
               f"by design — it is not a quarter-by-quarter movement. The number under "
               f"each point is how many sales it rests on. Source: Fields, from Domain "
               f"and onthehouse.com.au records.")
    if dropped:
        caption += (" Earlier quarters exist but are not continuous with these, so "
                    "the chart shows only the most recent unbroken run rather than "
                    "joining across a quarter we do not hold.")
    return "\n".join(svg), caption


def dom_chart(timeline, suburb_display, fb):
    """Median days on market by quarter.

    Days-on-market is one of the two layers our own audit found reliable
    (`data_source_undercapture_reset`: DOM and price growth matched PropRadar
    closely; sales VOLUME is under-counted ~2x). A median survives a sample;
    a count does not. So the median is plotted and the count appears only as
    the sample size under each point -- never as a market fact in its own right.

    Read from `precomputed_market_charts`, the same collection the Market
    Intelligence page renders, so the two surfaces cannot disagree.
    """
    pts = [dict(p, _ord=quarter_ordinal(p.get("period"))) for p in timeline
           if p.get("median_days_on_market") is not None
           and (p.get("transaction_count") or 0) > 0]
    pts = [p for p in pts if p["_ord"] is not None]
    pts, _dropped = recent_run(pts)
    if not pts:
        return None, None

    height = 236
    svg, g = _frame(height, f"How long {suburb_display} houses take to sell",
                    "Median days from listing to sale, by quarter.")

    vals = [p["median_days_on_market"] for p in pts]
    ymin, ymax = _scale(vals, 0.28, 0.24)
    ymin = max(0, ymin)
    o0, o1 = pts[0]["_ord"], pts[-1]["_ord"]
    _span = max(1, o1 - o0)
    xs = [g["x0"] + (g["x1"] - g["x0"]) * (p["_ord"] - o0) / _span for p in pts]

    def Y(v):
        return g["y1"] - (v - ymin) / (ymax - ymin) * (g["y1"] - g["y0"])

    for v in (min(vals), max(vals)):
        y = Y(v)
        svg.append(f'<line class="fig-grid" x1="{g["x0"]}" y1="{y:.1f}" '
                   f'x2="{g["x1"]}" y2="{y:.1f}"/>')
        svg.append(f'<text class="fig-axis" x="0" y="{y+4:.1f}">'
                   f'{fb.num(f"chart_dom_axis_{int(v)}", v)} days</text>')

    svg.append('<polyline class="fig-line" points="'
               + " ".join(f"{x:.1f},{Y(p['median_days_on_market']):.1f}"
                          for x, p in zip(xs, pts)) + '"/>')

    thin_periods = []
    for i, (x, p) in enumerate(zip(xs, pts)):
        n = p.get("transaction_count") or 0
        thin = n < THIN_N
        if thin:
            # Minted: the label carries an abbreviated YEAR ("Q4 25"), which the
            # fact-check would otherwise flag as an unaccounted-for figure.
            thin_periods.append(fb.date(f"chart_dom_thin{i}",
                                        _shorten_period(p["period"])))
        y = Y(p["median_days_on_market"])
        svg.append(f'<circle class="{"fig-dot-thin" if thin else "fig-dot"}" '
                   f'cx="{x:.1f}" cy="{y:.1f}" r="{3.6 if not thin else 3.2}"/>')
        svg.append(f'<text class="fig-axis" x="{x:.1f}" y="{g["y1"]+16:.1f}" '
                   f'text-anchor="middle">{_esc(_shorten_period(p["period"]))}</text>')
        svg.append(f'<text class="fig-n" x="{x:.1f}" y="{g["y1"]+30:.1f}" '
                   f'text-anchor="middle">{fb.num(f"chart_dom_n{i}", n)}</text>')

    last = pts[-1]
    svg.append(f'<text class="fig-val" x="{xs[-1]:.1f}" y="{Y(last["median_days_on_market"])-11:.1f}" '
               f'text-anchor="end">{fb.num("chart_dom_last", last["median_days_on_market"])} days</text>')
    svg.append(f'<text class="fig-n" x="0" y="{g["y1"]+30:.1f}">sales</text>')
    svg.append("</svg>")

    caption = ("The number under each point is how many sales it is measured from. "
               "A median holds up on a sample of the market; a count of sales does "
               "not, so no sales total is reported here as a market figure.")
    if thin_periods:
        caption += (f" Hollow points ({', '.join(thin_periods)}) rest on fewer than "
                    f"{fb.num('chart_thin_n', THIN_N)} sales — shown, but not firm "
                    f"enough to lean on.")
    caption += " Source: Fields, the same figure shown on our Market Intelligence pages."
    return "\n".join(svg), caption

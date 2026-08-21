#!/usr/bin/env python3
"""Reusable house-style chart renderer for the market-update articles.

Renders PNGs into /data/blobs/article-charts/ (nginx serves them at
https://blobs.fieldsestate.com.au/article-charts/<name>.png), so article bodies
reference them by URL — no base64 (see memory: article_inline_images).

House palette drawn from the Fields brand (deep green base, copper accent, slate).
Categorical triad copper/green/slate is an orange-green-blue family — CVD-safe by
construction. Text wears ink tokens, never the series colour. Grid recessive.

Data all comes from Gold_Coast collections computed 2026-08-01; DOM uses the
days_on_market field (NOT days_on_domain — contaminated; see memory).

Run:  python3 scripts/market_article_charts.py --median   (or --all)
"""
import argparse
import os
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from shared.db import get_client

OUT = "/data/blobs/article-charts"
PUBLIC = "https://blobs.fieldsestate.com.au/article-charts"

# ---- house palette ----
INK = "#1a120e"          # primary text
MUTED = "#6b5d52"        # secondary text
GRID = "#e4dccf"         # recessive grid
SURFACE = "#ffffff"
COPPER = "#b87333"       # accent / the "headline" series
GREEN = "#2e6b4c"        # brand green
SLATE = "#40607f"        # slate blue
GOLD = "#c1913c"
CAT = [COPPER, GREEN, SLATE, GOLD]   # fixed categorical order, never cycled

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 12,
    "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": GRID, "axes.linewidth": 1.0,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "svg.fonttype": "none",
})


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=1.0, zorder=0)
    ax.tick_params(length=0)


def _save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE, pad_inches=0.25)
    plt.close(fig)
    print(f"{PUBLIC}/{name}")
    return f"{PUBLIC}/{name}"


def _qkey(p):
    """Accept 'Q1 2025' or '2025-Q1' -> sortable int."""
    p = p.strip()
    if "-Q" in p:
        y, q = p.split("-Q")
    elif p.startswith("Q"):
        q, y = p[1:].split()
    else:
        raise ValueError(f"bad period {p!r}")
    return int(y) * 4 + int(q)


def _qlabel(p):
    """Normalise to 'Q2 2026' for display."""
    p = p.strip()
    if "-Q" in p:
        y, q = p.split("-Q"); return f"Q{int(q)} {y}"
    return p


def _q_range(series, start, end):
    lo, hi = _qkey(start), _qkey(end)
    return sorted([r for r in series if lo <= _qkey(r["period"]) <= hi], key=lambda r: _qkey(r["period"]))


# ---------- MEDIAN ARTICLE ----------

def chart_robina_bedroom_index(gc):
    """Trap 1: Robina attached — all-attached vs 2-bed vs 3-bed, indexed 2024-Q2=100."""
    d = gc["unit_market_series"].find_one({"_id": "robina"})
    allser = {r["period"]: r["rolling_median"] for r in d["rolling_12m"]}
    bb = d["rolling_12m_by_bedrooms"]
    two = {r["period"]: r["rolling_median"] for r in bb["2"]}
    three = {r["period"]: r["rolling_median"] for r in bb["3"]}
    periods = [f"{y}-Q{q}" for y in (2024, 2025, 2026) for q in range(1, 5)]
    periods = [p for p in periods if p >= "2024-Q2" and p <= "2026-Q2"]

    def idx(m):
        base = m.get("2024-Q2")
        return [(m[p] / base * 100 if p in m and base else None) for p in periods]

    series = [("All attached dwellings", idx(allser), COPPER, 3.0),
              ("3-bedroom", idx(three), SLATE, 2.0),
              ("2-bedroom", idx(two), GREEN, 2.0)]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(periods)))
    for label, ys, col, lw in series:
        ax.plot(x, ys, color=col, linewidth=lw, marker="o", markersize=5,
                markerfacecolor=col, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
        # direct end label
        yend = next((v for v in reversed(ys) if v is not None), None)
        ax.annotate(f"{label}  {yend:.0f}", (x[-1], yend), xytext=(8, 0),
                    textcoords="offset points", va="center", color=col, fontsize=11, fontweight="bold")
    ax.axhline(100, color=MUTED, linewidth=0.8, linestyle=(0, (4, 4)), zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(p) for p in periods], rotation=30, ha="right", fontsize=9.5)
    ax.set_ylabel("Indexed to June 2024 = 100")
    ax.set_xlim(-0.3, len(periods) - 0.3 + 3.2)
    ax.set_title("Robina attached dwellings: the all-attached median rose faster than any size",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    end = {lab: next(v for v in reversed(ys) if v is not None) for lab, ys, _, _ in series}
    return _save(fig, "median_robina_bedroom_index.png"), end


def chart_robina_rolling_ci(gc):
    """Trap 3: Robina house rolling 12m median + CI band, quarterly medians as dots."""
    d = gc["precomputed_indexed_prices"].find_one({"_id": "robina"})
    roll = _q_range(d["rolling_12m_median_series"], "2025-Q1", "2026-Q2")
    quart = [q for q in _q_range(d["indexed_series"], "2025-Q1", "2026-Q2")]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    xr = list(range(len(roll)))
    labels = [r["period"] for r in roll]
    med = [r["rolling_median"] for r in roll]
    lo = [r.get("ci_low") or r["rolling_median"] for r in roll]
    hi = [r.get("ci_high") or r["rolling_median"] for r in roll]
    ax.fill_between(xr, lo, hi, color=GREEN, alpha=0.14, zorder=1, label="90% confidence range")
    ax.plot(xr, med, color=GREEN, linewidth=3.0, marker="o", markersize=6,
            markerfacecolor=GREEN, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3,
            label="12-month rolling median")
    # quarterly dots positioned at matching period
    idxmap = {p: i for i, p in enumerate(labels)}
    qx, qy = [], []
    for q in quart:
        if q["period"] in idxmap:
            qx.append(idxmap[q["period"]]); qy.append(q["median_price"])
    ax.scatter(qx, qy, s=70, color=COPPER, edgecolor=SURFACE, linewidth=1.2, zorder=4,
               label="single-quarter median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(xr)
    ax.set_xticklabels([p.replace("-Q", " Q") for p in labels], fontsize=10)
    ax.set_title("Robina house median: the smooth line is the trend, the dots are the noise",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="lower right", labelcolor=INK)
    return _save(fig, "median_robina_rolling_ci.png")


def build_median(gc):
    p1, end = chart_robina_bedroom_index(gc)
    p2 = chart_robina_rolling_ci(gc)
    print("\nINDEX ENDPOINTS (2026-Q2):", {k: round(v) for k, v in end.items()})


# ---------- shared computations ----------

def _rolling_3m_median(gc, suburb):
    """Month-stepped trailing 3-month house median via the live median pipeline funcs.
    Returns [(YYYY-MM, median, lo, hi)] for the last 9 anchors, dropping thin windows."""
    import importlib.util
    import random
    from datetime import datetime
    spec = importlib.util.spec_from_file_location(
        "upx", "/home/fields/Fields_Orchestrator/scripts/precompute_union_prices.py")
    upx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upx)
    from shared.db import get_client
    random.seed(42)
    client = get_client()
    counters = {}
    from collections import defaultdict
    counters = defaultdict(int)
    sales = upx.dedupe_sales(
        upx.load_domain_history(client["Gold_Coast"], suburb, counters)
        + upx.load_onthehouse(client["system_monitor"], suburb, counters))
    pts = [(datetime.strptime(d, "%Y-%m-%d"), p) for (_, d), p in sales.items()]
    end = max(d for d, _ in pts)
    y, m = end.year, end.month
    anchors = []
    for _ in range(9):
        anchors.append((y, m))
        m -= 1
        if m == 0:
            y -= 1; m = 12
    out = []
    for yy, mm in anchors[::-1]:
        sy, smo = yy, mm - 2
        while smo <= 0:
            smo += 12; sy -= 1
        start = datetime(sy, smo, 1)
        ny, nmm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
        wend = datetime(ny, nmm, 1)
        w = [p for d, p in pts if start <= d < wend]
        if len(w) < upx.MIN_N_QUARTER:
            continue
        med = int(statistics.median(w))
        lo, hi = upx.bootstrap_ci(w)
        out.append((f"{yy}-{mm:02d}", med, lo, hi, len(w)))
    return out


def _rolling_3m_dom(gc, suburb):
    """Month-stepped trailing 3-month median DOM from days_on_market (the site's field)."""
    from datetime import datetime
    rows = list(gc[suburb].find(
        {"listing_status": "sold", "classified_property_type": "House",
         "days_on_market": {"$ne": None}, "sold_date": {"$ne": None}},
        {"days_on_market": 1, "sold_date": 1}))
    pts = []
    for r in rows:
        try:
            pts.append((datetime.strptime(r["sold_date"][:10], "%Y-%m-%d"), r["days_on_market"]))
        except Exception:
            pass
    end = max(d for d, _ in pts)
    y, m = end.year, end.month
    anchors = []
    for _ in range(9):
        anchors.append((y, m)); m -= 1
        if m == 0: y -= 1; m = 12
    out = []
    for yy, mm in anchors[::-1]:
        sy, smo = yy, mm - 2
        while smo <= 0: smo += 12; sy -= 1
        start = datetime(sy, smo, 1)
        ny, nmm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
        wend = datetime(ny, nmm, 1)
        w = [v for d, v in pts if start <= d < wend]
        if len(w) < 5:
            continue
        out.append((f"{yy}-{mm:02d}", statistics.median(w), len(w)))
    return out


def _mlabel(ym):
    mm = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
          "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}
    y, m = ym.split("-")
    return f"{mm[m]} {y[2:]}"


# ---------- ROBINA ----------

def chart_robina_dom(gc):
    d = gc["precomputed_market_charts"].find_one({"_id": "robina_days_on_market"})
    tl = [t for t in d["timeline"] if _qkey(t["period"].replace("-Q", "-Q")) >= _qkey("2025-Q1")]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(tl)))
    med = [t["median_days_on_market"] for t in tl]
    ax.plot(x, med, color=COPPER, linewidth=3.0, marker="o", markersize=6,
            markerfacecolor=COPPER, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3)
    for xi, yi in zip(x, med):
        ax.annotate(f"{yi:.0f}", (xi, yi), xytext=(0, 9), textcoords="offset points",
                    ha="center", color=INK, fontsize=10, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(t["period"]) for t in tl], fontsize=10)
    ax.set_ylabel("Median days on market")
    ax.set_ylim(0, max(med) * 1.25)
    ax.set_title("Robina: houses are taking longer to sell",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, "robina_dom.png")


def _median_ci_chart(gc, suburb, title, fname, start="2025-Q1"):
    d = gc["precomputed_indexed_prices"].find_one({"_id": suburb})
    roll = _q_range(d["rolling_12m_median_series"], start, "2026-Q2")
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(roll)))
    med = [r["rolling_median"] for r in roll]
    lo = [r.get("ci_low") or r["rolling_median"] for r in roll]
    hi = [r.get("ci_high") or r["rolling_median"] for r in roll]
    ax.fill_between(x, lo, hi, color=GREEN, alpha=0.14, zorder=1, label="90% confidence range")
    ax.plot(x, med, color=GREEN, linewidth=3.0, marker="o", markersize=6,
            markerfacecolor=GREEN, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3,
            label="12-month rolling median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(r["period"]) for r in roll], fontsize=10)
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="lower right", labelcolor=INK)
    return _save(fig, fname)


def chart_bedroom_levels(gc, suburb, fname, title):
    d = gc["unit_market_series"].find_one({"_id": suburb})
    bb = d["rolling_12m_by_bedrooms"]
    periods = [f"{y}-Q{q}" for y in (2024, 2025, 2026) for q in range(1, 5)]
    periods = [p for p in periods if "2025-Q2" <= p <= "2026-Q2"]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(periods)))
    order = [("2", GREEN, "2-bedroom"), ("3", SLATE, "3-bedroom"), ("4", COPPER, "4-bedroom")]
    for bed, col, label in order:
        if bed not in bb:
            continue
        m = {r["period"]: r["rolling_median"] for r in bb[bed]}
        ys = [m.get(p) for p in periods]
        if not any(ys):
            continue
        ax.plot(x, ys, color=col, linewidth=2.4, marker="o", markersize=5,
                markerfacecolor=col, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
        yend = next((v for v in reversed(ys) if v is not None), None)
        ax.annotate(f"{label}  ${yend/1e3:.0f}k", (x[-1], yend), xytext=(8, 0),
                    textcoords="offset points", va="center", color=col, fontsize=10.5, fontweight="bold")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e3:.0f}k"))
    ax.set_xticks(x)
    ax.set_xticklabels([_qlabel(p) for p in periods], rotation=30, ha="right", fontsize=9.5)
    ax.set_xlim(-0.3, len(periods) - 0.3 + 3.4)
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


# ---------- 3-month rolling median (Varsity, BW) ----------

def chart_rolling_3m_median(gc, suburb, fname, title, drop_last=True):
    data = _rolling_3m_median(gc, suburb)
    if drop_last:
        data = data[:-1]  # exclude partial current month
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(data)))
    med = [r[1] for r in data]
    lo = [r[2] or r[1] for r in data]
    hi = [r[3] or r[1] for r in data]
    ax.fill_between(x, lo, hi, color=COPPER, alpha=0.13, zorder=1, label="90% confidence range")
    ax.plot(x, med, color=COPPER, linewidth=3.0, marker="o", markersize=6,
            markerfacecolor=COPPER, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=3,
            label="3-month rolling median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(x)
    ax.set_xticklabels([_mlabel(r[0]) for r in data], rotation=30, ha="right", fontsize=9.5)
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="best", labelcolor=INK)
    return _save(fig, fname)


# ---------- 3-month DOM, three suburbs ----------

def chart_dom_3suburb(gc, fname):
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    series = [("Robina", "robina", COPPER), ("Burleigh Waters", "burleigh_waters", SLATE),
              ("Varsity Lakes", "varsity_lakes", GREEN)]
    # align on a common set of month anchors present in all
    allmonths = None
    data = {}
    for label, sub, col in series:
        rows = _rolling_3m_dom(gc, sub)[:-1]  # drop partial
        data[sub] = rows
        ms = [r[0] for r in rows]
        allmonths = ms if allmonths is None else [m for m in allmonths if m in ms]
    for label, sub, col in series:
        rows = {r[0]: r[1] for r in data[sub]}
        ys = [rows[m] for m in allmonths]
        ax.plot(range(len(allmonths)), ys, color=col, linewidth=2.6, marker="o", markersize=5,
                markerfacecolor=col, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
        ax.annotate(f"{label}  {ys[-1]:.0f}", (len(allmonths) - 1, ys[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", color=col, fontsize=10.5, fontweight="bold")
    ax.set_xticks(range(len(allmonths)))
    ax.set_xticklabels([_mlabel(m) for m in allmonths], rotation=30, ha="right", fontsize=9.5)
    ax.set_ylabel("Median days on market")
    ax.set_xlim(-0.3, len(allmonths) - 0.3 + 4.2)
    ax.set_title("Three suburbs, three directions: median days on market",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


# ---------- Varsity value bars ----------

def chart_value_bars(gc, fname):
    subs = [("Varsity Lakes", 1400000, 398000, GREEN),
            ("Robina", 1490000, 426000, COPPER),
            ("Burleigh Waters", 1925000, 525000, SLATE)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.4))
    for ax in (a1, a2):
        _style(ax)
    labels = [s[0] for s in subs]
    x = list(range(len(subs)))
    cols = [s[3] for s in subs]
    a1.bar(x, [s[1] for s in subs], color=cols, width=0.62, zorder=3)
    for xi, s in zip(x, subs):
        a1.annotate(f"${s[1]/1e6:.2f}M", (xi, s[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=10.5, fontweight="bold")
    a1.set_title("Median house price", color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=10)
    a1.set_ylim(0, 2.2e6)
    a2.bar(x, [s[2] for s in subs], color=cols, width=0.62, zorder=3)
    for xi, s in zip(x, subs):
        a2.annotate(f"${s[2]/1e3:.0f}k", (xi, s[2]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=10.5, fontweight="bold")
    a2.set_title("Price per bedroom", color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=10)
    a2.set_ylim(0, 6.1e5)
    for ax in (a1, a2):
        ax.set_xticks(x)
        ax.set_xticklabels([l.replace(" ", "\n") for l in labels], fontsize=9.5)
        ax.set_yticks([])
        ax.grid(False)
    fig.suptitle("Varsity Lakes offers the most house for the money of the three",
                 color=INK, fontsize=13, fontweight="bold", x=0.02, ha="left", y=1.02)
    return _save(fig, fname)


# ---------- BW waterfront ----------

def chart_waterfront(gc, fname):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.4))
    for ax in (a1, a2):
        _style(ax)
    # share of house listings fronting water
    subs = [("Burleigh\nWaters", 31, SLATE), ("Robina", 13, COPPER)]
    x = [0, 1]
    a1.bar(x, [s[1] for s in subs], color=[s[2] for s in subs], width=0.6, zorder=3)
    for xi, s in zip(x, subs):
        a1.annotate(f"{s[1]}%", (xi, s[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=11, fontweight="bold")
    a1.set_xticks(x); a1.set_xticklabels([s[0] for s in subs], fontsize=10)
    a1.set_yticks([]); a1.grid(False); a1.set_ylim(0, 38)
    a1.set_title("Share of house listings on water", color=INK, fontsize=12, fontweight="bold", loc="left", pad=10)
    # asking spread: waterfront vs non-waterfront median asking
    groups = [("Waterfront", 2972500, 1625000), ("Non-waterfront", 1949000, 1495000)]
    xg = [0, 1]
    w = 0.36
    a2.bar([g - w/2 for g in xg], [groups[0][1], groups[1][1]], width=w, color=SLATE, zorder=3, label="Burleigh Waters")
    a2.bar([g + w/2 for g in xg], [groups[0][2], groups[1][2]], width=w, color=COPPER, zorder=3, label="Robina")
    a2.set_xticks(xg); a2.set_xticklabels([g[0] for g in groups], fontsize=10)
    a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.1f}M"))
    a2.set_title("Median asking price", color=INK, fontsize=12, fontweight="bold", loc="left", pad=10)
    a2.legend(frameon=False, fontsize=9.5, labelcolor=INK, loc="upper right")
    fig.suptitle("Burleigh Waters carries far more waterfront — and a bigger premium on it",
                 color=INK, fontsize=12.5, fontweight="bold", x=0.02, ha="left", y=1.02)
    return _save(fig, fname)


# ---------- BW 3m vs 12m ----------

def chart_bw_3v12(gc, fname):
    d = gc["precomputed_indexed_prices"].find_one({"_id": "burleigh_waters"})
    roll12 = _q_range(d["rolling_12m_median_series"], "2025-Q1", "2026-Q2")
    three = _rolling_3m_median(gc, "burleigh_waters")[:-1]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    # x by month index; place 12m quarterly points at their quarter-end month
    qmonth = {"Q1": "03", "Q2": "06", "Q3": "09", "Q4": "12"}
    months = [r[0] for r in three]
    mi = {m: i for i, m in enumerate(months)}
    x3 = list(range(len(three)))
    ax.plot(x3, [r[1] for r in three], color=COPPER, linewidth=2.8, marker="o", markersize=5,
            markerfacecolor=COPPER, markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3,
            label="3-month rolling median")
    # map 12m rolling to month axis
    x12, y12 = [], []
    for r in roll12:
        q, y = r["period"].split()[0] if " " in r["period"] else ("Q" + r["period"].split("-Q")[1], "")
        if "-Q" in r["period"]:
            yy, qq = r["period"].split("-Q"); key = f"{yy}-{qmonth['Q'+qq]}"
        else:
            qq, yy = r["period"][1:].split(); key = f"{yy}-{qmonth['Q'+qq]}"
        if key in mi:
            x12.append(mi[key]); y12.append(r["rolling_median"])
    ax.plot(x12, y12, color=GREEN, linewidth=3.0, marker="s", markersize=7,
            markerfacecolor=GREEN, markeredgecolor=SURFACE, markeredgewidth=1.4, zorder=4,
            label="12-month rolling median")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.set_xticks(x3)
    ax.set_xticklabels([_mlabel(m) for m in months], rotation=30, ha="right", fontsize=9.5)
    ax.set_title("Burleigh Waters: the annual figure still rising, the recent months softening",
                 color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=10, loc="lower left", labelcolor=INK)
    return _save(fig, fname)


def chart_supply(gc, fname):
    """Months of supply, three suburbs, with the 4-month balance line."""
    subs = [("Varsity Lakes", 1.77, GREEN), ("Robina", 2.18, COPPER), ("Burleigh Waters", 3.57, SLATE)]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    _style(ax)
    x = list(range(len(subs)))
    ax.bar(x, [s[1] for s in subs], color=[s[2] for s in subs], width=0.6, zorder=3)
    for xi, s in zip(x, subs):
        ax.annotate(f"{s[1]:.2f}", (xi, s[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=11, fontweight="bold")
    ax.axhline(4, color=MUTED, linewidth=1.2, linestyle=(0, (5, 4)), zorder=2)
    ax.annotate("4 months = balanced market", (len(subs) - 0.5, 4), xytext=(0, 5),
                textcoords="offset points", ha="right", color=MUTED, fontsize=10.5)
    ax.set_xticks(x)
    ax.set_xticklabels([s[0].replace(" ", "\n") for s in subs], fontsize=10.5)
    ax.set_ylabel("Months of supply")
    ax.set_ylim(0, 4.6)
    ax.set_yticks([0, 1, 2, 3, 4])
    ax.set_title("Unsold stock is not piling up: all three suburbs sit below balanced",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_capital_quarterly(fname):
    """Ranked capital-city quarterly dwelling-value change to July 2026 (Cotality)."""
    data = [("Sydney", -4.0), ("Melbourne", -3.4), ("Combined capitals", -2.5),
            ("Canberra", -1.3), ("Brisbane", -0.6), ("Perth", -0.3),
            ("Adelaide", 0.1), ("Hobart", 1.4), ("Darwin", 2.4)]
    data = sorted(data, key=lambda d: d[1])
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    ax.grid(False); ax.grid(axis="x", color=GRID, linewidth=1.0, zorder=0)
    y = list(range(len(data)))
    cols = [COPPER if v < 0 else GREEN for _, v in data]
    ax.barh(y, [v for _, v in data], color=cols, height=0.62, zorder=3)
    for yi, (lab, v) in zip(y, data):
        ha = "right" if v < 0 else "left"
        off = -6 if v < 0 else 6
        emph = lab == "Brisbane"
        ax.annotate(f"{v:+.1f}%", (v, yi), xytext=(off, 0), textcoords="offset points",
                    va="center", ha=ha, color=INK, fontsize=10.5,
                    fontweight="bold" if emph else "normal")
    ax.axvline(0, color=MUTED, linewidth=1.0, zorder=2)
    ax.set_xlim(-5.4, 3.2)
    ax.set_yticks(y)
    labels = [f"{lab}" for lab, _ in data]
    ax.set_yticklabels(labels, fontsize=10.5)
    # emphasise Brisbane tick
    for t in ax.get_yticklabels():
        if t.get_text() == "Brisbane":
            t.set_fontweight("bold"); t.set_color(INK)
    ax.set_xlabel("Change over the quarter to July 2026")
    ax.set_title("Brisbane is turning — but gently, next to Sydney and Melbourne",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_two_clocks(fname):
    """Annual vs quarterly change, Sydney/Melbourne/Brisbane — the two clocks."""
    data = [("Sydney", -2.0, -4.0), ("Melbourne", -2.8, -3.4), ("Brisbane", 14.8, -0.6)]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    _style(ax)
    x = list(range(len(data)))
    w = 0.38
    ax.bar([i - w/2 for i in x], [d[1] for d in data], width=w, color=GREEN, zorder=3, label="Past year")
    ax.bar([i + w/2 for i in x], [d[2] for d in data], width=w, color=COPPER, zorder=3, label="Past quarter")
    for i, d in enumerate(data):
        ax.annotate(f"{d[1]:+.1f}%", (i - w/2, d[1]), xytext=(0, 6 if d[1] >= 0 else -14),
                    textcoords="offset points", ha="center", color=INK, fontsize=10, fontweight="bold")
        ax.annotate(f"{d[2]:+.1f}%", (i + w/2, d[2]), xytext=(0, 6 if d[2] >= 0 else -14),
                    textcoords="offset points", ha="center", color=INK, fontsize=10, fontweight="bold")
    ax.axhline(0, color=MUTED, linewidth=1.0, zorder=2)
    ax.set_xticks(x); ax.set_xticklabels([d[0] for d in data], fontsize=11)
    ax.set_ylabel("Dwelling-value change")
    ax.set_ylim(-6, 17)
    ax.set_yticks([])
    ax.grid(False)
    ax.legend(frameon=False, fontsize=10.5, loc="upper left", labelcolor=INK)
    ax.set_title("Two clocks: Brisbane is up 14.8% over the year, down over the quarter",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_the_gap(fname):
    """The gap that matters when you move: own-home vs target-home, a year ago vs now.
    Year-ago = Q2-2025 rolling-12m median (consistent with the published YoY), NOT
    the rolling_12m_prev_median_price field, which disagrees with yoy_pct."""
    groups = [("A year ago", 1270000, 1800000), ("Now", 1400000, 1925000)]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    x = [0, 1]
    w = 0.34
    ax.bar([i - w/2 for i in x], [g[1] for g in groups], width=w, color=GREEN, zorder=3, label="A home like yours (Varsity Lakes median)")
    ax.bar([i + w/2 for i in x], [g[2] for g in groups], width=w, color=SLATE, zorder=3, label="The home you want (Burleigh Waters median)")
    for i, g in enumerate(groups):
        ax.annotate(f"${g[1]/1e6:.2f}M", (i - w/2, g[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
        ax.annotate(f"${g[2]/1e6:.3f}M", (i + w/2, g[2]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
        gap = g[2] - g[1]
        ax.annotate(f"the gap:\n${gap/1e3:.0f}k", (i, max(g[1], g[2]) * 0.52), ha="center",
                    color=COPPER, fontsize=12, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([g[0] for g in groups], fontsize=12)
    ax.set_ylim(0, 2.25e6); ax.set_yticks([]); ax.grid(False)
    ax.legend(frameon=False, fontsize=10, loc="upper left", labelcolor=INK)
    ax.set_title("Both homes rose about $130,000 — but the gap between them barely moved",
                 color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_suburb_gaps(fname):
    """The gaps BETWEEN suburbs, a year ago vs now — proof they moved differently.
    Year-ago = Q2-2025 rolling-12m median; now = Q2-2026 (consistent with published YoY)."""
    pairs = [("Varsity Lakes\n→ Robina", 138500, 90000),
             ("Robina →\nBurleigh Waters", 391500, 435000),
             ("Varsity Lakes →\nBurleigh Waters", 530000, 525000)]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    _style(ax)
    x = list(range(len(pairs)))
    w = 0.34
    ax.bar([i - w/2 for i in x], [p[1] for p in pairs], width=w, color=SLATE, zorder=3, label="Gap a year ago")
    ax.bar([i + w/2 for i in x], [p[2] for p in pairs], width=w, color=COPPER, zorder=3, label="Gap now")
    for i, p in enumerate(pairs):
        ax.annotate(f"${p[1]/1e3:.0f}k", (i - w/2, p[1]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
        ax.annotate(f"${p[2]/1e3:.0f}k", (i + w/2, p[2]), xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9.5, fontweight="bold")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1e3:.0f}k"))
    ax.set_xticks(x); ax.set_xticklabels([p[0] for p in pairs], fontsize=10)
    ax.set_ylim(0, 560000)
    ax.legend(frameon=False, fontsize=10, loc="upper left", labelcolor=INK)
    ax.set_title("The same year lifted every suburb — but moved the gaps between them differently",
                 color=INK, fontsize=12.5, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def chart_gc_industry(fname):
    """Gold Coast employment by industry — the diversified, health-led economy.
    Source: economy.id (City of Gold Coast / NIEIR), 2024/25."""
    data = [("Health care & social assistance", 16.6, True),
            ("Construction", 15.7, False),
            ("Retail trade", 9.9, False),
            ("Education & training", 8.7, False),
            ("Accommodation & food (tourism)", 8.5, "tourism"),
            ("Professional & technical", 6.4, False),
            ("Manufacturing", 6.1, False),
            ("Administrative & support", 3.7, False),
            ("Public administration & safety", 3.5, False)]
    data = data[::-1]  # largest at top
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    _style(ax)
    ax.grid(False); ax.grid(axis="x", color=GRID, linewidth=1.0, zorder=0)
    y = list(range(len(data)))
    cols = [COPPER if flag is True else (SLATE if flag == "tourism" else GREEN) for _, _, flag in data]
    ax.barh(y, [v for _, v, _ in data], color=cols, height=0.66, zorder=3)
    for yi, (lab, v, flag) in zip(y, data):
        ax.annotate(f"{v:.1f}%", (v, yi), xytext=(6, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=10,
                    fontweight="bold" if flag else "normal")
    ax.set_yticks(y); ax.set_yticklabels([d[0] for d in data], fontsize=10)
    ax.set_xlim(0, 19)
    ax.set_xlabel("Share of Gold Coast jobs")
    ax.set_title("A health-led economy, not a tourism town: Gold Coast jobs by industry",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)
    return _save(fig, fname)


def build_all(gc):
    build_median(gc)
    print("\n-- Robina --")
    chart_robina_dom(gc)
    _median_ci_chart(gc, "robina", "Robina house median: price held while the clock stretched", "robina_median_ci.png")
    chart_bedroom_levels(gc, "robina", "robina_bedroom_levels.png", "Robina units: what each size actually did")
    print("\n-- Varsity --")
    chart_value_bars(gc, "varsity_value_bars.png")
    chart_rolling_3m_median(gc, "varsity_lakes", "varsity_median_3m.png", "Varsity Lakes: a dip over summer, then a recovery")
    chart_dom_3suburb(gc, "dom_3suburb.png")
    chart_bedroom_levels(gc, "varsity_lakes", "varsity_bedroom_levels.png", "Varsity Lakes units: what each size actually did")
    print("\n-- Burleigh Waters --")
    chart_waterfront(gc, "bw_waterfront.png")
    _median_ci_chart(gc, "burleigh_waters", "Burleigh Waters house median: a steady climb that has levelled", "bw_median_12m.png", start="2024-Q3")
    chart_bw_3v12(gc, "bw_median_3v12.png")
    chart_bedroom_levels(gc, "burleigh_waters", "bw_bedroom_levels.png", "Burleigh Waters units: 2- and 3-bedroom, what each did")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--median", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    gc = get_client()["Gold_Coast"]
    if args.all:
        build_all(gc)
    elif args.median:
        build_median(gc)


if __name__ == "__main__":
    main()

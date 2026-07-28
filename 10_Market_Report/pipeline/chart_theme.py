"""
Fields Quarterly — chart theme (DESIGNER-MATCHED, 2026-07).
Matches the designer's graph assets (assets/designer_cover/• Graphs/Graph-*.svg):
  - smooth copper line + soft grey fill (Graph-2)
  - paired copper/teal rounded "pill" bars (Graph-3)
  - thin 0.5px ink gridlines, Playfair numbers, spaced Poppins labels, no spines.
Backward-compatible: keeps the names generate_charts.py already imports.
"""

import os
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

# ---------------------------------------------------------------- palette ----
# Designer's exact chart colours (from the Graph-*.svg <style> blocks)
INK     = "#343d34"   # axes, gridlines, numbers/labels (dark green-grey)
COPPER  = "#a4674c"   # primary data
TEAL    = "#a9c9bf"   # secondary data
BIRCH   = "#E7DFD4"   # paper
FILL    = "#ded6c9"   # soft area fill under lines

# Fields brand tokens (kept for anything that references them)
FIELDS_GRASS  = "#22382C"; FIELDS_BIRCH = "#E6DDD2"; FIELDS_COPPER = "#B76749"
FIELDS_SUN    = "#FEC66F"; FIELDS_SKY   = "#A0D1C9"; FIELDS_SAGE  = "#848A7F"
CHARCOAL = INK; SLATE = "#7a8a80"; LIGHT_GREY = "#b9c2b7"; GRID_GREY = "#c9d2c7"
BRAND_BLUE = INK; LIGHT_BLUE = TEAL; CREAM = BIRCH; ACCENT = COPPER

# three distinguishable, on-brand suburb colours
SUBURB_COLOURS = {
    "robina":          INK,
    "burleigh_waters": COPPER,
    "varsity_lakes":   TEAL,
}
SUBURB_LABELS = {
    "robina": "Robina", "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes", "southern_gold_coast": "Southern Gold Coast",
}

# ---------------------------------------------------------------- fonts ------
_FONTDIR = os.path.join(os.path.dirname(__file__), "quarterly", "assets", "fonts")
def _fp(name, fallback):
    p = os.path.join(_FONTDIR, name)
    if os.path.exists(p):
        try:
            fm.fontManager.addfont(p)
            return fm.FontProperties(fname=p)
        except Exception:
            pass
    return fm.FontProperties(family=fallback)
PLAY = _fp("PlayfairDisplay.ttf", "serif")   # numbers
POP  = _fp("Poppins.ttf", "sans-serif")      # labels / legend


def apply_theme():
    mpl.rcParams.update({
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
        "savefig.edgecolor": "none",
        "savefig.transparent": True,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "axes.spines.bottom": False,
        "axes.edgecolor": INK, "axes.labelcolor": INK,
        "text.color": INK, "xtick.color": INK, "ytick.color": INK,
        "legend.frameon": False,
        "font.family": "sans-serif",
        "font.sans-serif": ["Poppins", "Inter", "DejaVu Sans"],
    })


# ---------------------------------------------------------------- helpers ----
def smooth_line(ax, x, y, color, lw=4.0, fill=False, z=3, alpha=1.0):
    """Designer smooth line (Graph-2): spline-smoothed, round caps, optional fill."""
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    if len(x) >= 4:
        try:
            from scipy.interpolate import make_interp_spline
            xs = np.linspace(x.min(), x.max(), 400)
            ys = make_interp_spline(x, y, k=3)(xs)
        except Exception:
            xs, ys = x, y
    else:
        xs, ys = x, y
    if fill:
        ax.fill_between(xs, ys, ax.get_ylim()[0], color=FILL, alpha=0.55, zorder=1)
    ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="round",
            solid_joinstyle="round", zorder=z, alpha=alpha)


def vgrid(ax, xvals):
    """Thin vertical ink gridlines (0.5px)."""
    for xv in xvals:
        ax.axvline(xv, color=INK, lw=0.5, zorder=0)


def pill_bar_v(ax, xc, height, color, width_pts, base=0.0, z=3):
    """A vertical rounded-cap 'pill' bar (Graph-3 look) as a round-capped line."""
    ax.plot([xc, xc], [base, height], color=color, lw=width_pts,
            solid_capstyle="round", zorder=z)


def designer_ticks(ax, xticks=None, xlabels=None, yticks=None, ylabels=None,
                   xsize=12, ysize=14):
    """Playfair numbers, spaced Poppins labels, no spines, no tick marks."""
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    if xticks is not None:
        ax.set_xticks(xticks)
        ax.set_xticklabels(xlabels if xlabels is not None else xticks,
                           fontproperties=POP, fontsize=xsize, color=INK)
    if yticks is not None:
        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels if ylabels is not None else yticks,
                           fontproperties=PLAY, fontsize=ysize, color=INK)
    for lbl in ax.get_yticklabels():
        lbl.set_fontproperties(PLAY)
    for lbl in ax.get_xticklabels():
        lbl.set_fontproperties(POP)


# --------------------------------------------------- back-compat shims -------
# Titles/subtitles/source lines are intentionally NO-OPS: the report page
# provides its own headline + deck, and methodology lives on the "how every
# chart is made" page — so the charts stay as clean as the designer's assets.
def add_source_line(fig, text, wrap_chars=170):
    return


def add_title_block(fig, title, subtitle=None):
    return


def style_axes(ax, ylabel=None, xlabel=None):
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, colors=INK)
    for lbl in ax.get_yticklabels():
        lbl.set_fontproperties(PLAY); lbl.set_fontsize(12)
    for lbl in ax.get_xticklabels():
        lbl.set_fontproperties(POP); lbl.set_fontsize(11)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8.5, color=SLATE, fontproperties=POP)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8.5, color=SLATE, fontproperties=POP)

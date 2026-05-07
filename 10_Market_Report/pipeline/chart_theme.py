"""
Fields Quarterly — chart theme.
Single source of truth for the visual style of every chart in the report.
Per strategy/04_visual_format_spec.md.
"""

import matplotlib as mpl
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------------
# Fields official palette (per Fields Style Guide v1.0 - 2025)
# ----------------------------------------------------------------------------
FIELDS_GRASS  = "#22382C"  # Primary brand green — Pantone 5605C, RGB 34/56/44
FIELDS_BIRCH  = "#E6DDD2"  # Off-white / paper — RGB 230/221/210
FIELDS_COPPER = "#B76749"  # Accent / call-outs — Pantone 4014C, RGB 183/103/73
FIELDS_SUN    = "#FEC66F"  # Secondary — for CTAs / callouts — Pantone 1355C
FIELDS_SKY    = "#A0D1C9"  # Secondary — Pantone 7464C

# Computed mid-tone of grass on birch (50% blend) — for secondary chart lines
FIELDS_SAGE   = "#848A7F"  # 50% Fields Grass on Fields Birch background

# Utility neutrals (not in style guide but needed for charts)
CHARCOAL   = "#1A1A1A"  # body text
SLATE      = "#6B7280"  # secondary text / muted line
LIGHT_GREY = "#9CA3AF"  # axis spines, subtle dividers
GRID_GREY  = "#E5E7EB"  # gridlines

# Legacy aliases (kept so existing code continues to work)
BRAND_BLUE = FIELDS_GRASS
LIGHT_BLUE = FIELDS_SAGE
CREAM      = FIELDS_BIRCH
ACCENT     = FIELDS_COPPER

SUBURB_COLOURS = {
    "robina":          FIELDS_SAGE,    # mid-tone sage (secondary suburb)
    "burleigh_waters": FIELDS_GRASS,   # primary brand green (focus suburb)
    "varsity_lakes":   FIELDS_COPPER,  # copper accent (third distinguishable suburb)
}

SUBURB_LABELS = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
    "southern_gold_coast": "Southern Gold Coast",
}


def apply_theme():
    """Apply Fields theme to matplotlib globally for the script's lifetime."""
    mpl.rcParams.update({
        "figure.facecolor": FIELDS_BIRCH,
        "axes.facecolor": "#FFFFFF",
        "axes.edgecolor": LIGHT_GREY,
        "axes.labelcolor": CHARCOAL,
        "axes.titlesize": 12,
        "axes.titleweight": "semibold",
        "axes.titlecolor": CHARCOAL,
        "axes.labelsize": 9,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": CHARCOAL,
        "ytick.color": CHARCOAL,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "grid.color": GRID_GREY,
        "grid.linewidth": 0.4,
        "grid.alpha": 0.6,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "font.family": "serif",
        "font.serif": ["Source Serif Pro", "Tiempos Text", "Georgia", "DejaVu Serif"],
        "font.sans-serif": ["Inter", "Söhne", "Helvetica", "DejaVu Sans"],
        "savefig.facecolor": FIELDS_BIRCH,
        "savefig.edgecolor": "none",
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
    })


def add_source_line(fig, text):
    """Add a small source line at the bottom of the figure."""
    fig.text(0.02, 0.015, text, fontsize=7, color=SLATE, fontstyle="italic")


def add_title_block(fig, title, subtitle=None):
    """
    Place title (and optional subtitle) at the top of the figure using
    figure-level coordinates. Use with fig.subplots_adjust(top=0.85) so the
    chart doesn't collide with the title block.
    """
    fig.text(0.04, 0.945, title,
             fontsize=13, color=CHARCOAL, fontweight="semibold", ha="left", va="top")
    if subtitle:
        fig.text(0.04, 0.895, subtitle,
                 fontsize=8.5, color=SLATE, ha="left", va="top")


def style_axes(ax, ylabel=None, xlabel=None):
    """Apply consistent axis styling."""
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=CHARCOAL)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color=CHARCOAL)
    ax.spines["bottom"].set_color(LIGHT_GREY)
    ax.spines["left"].set_color(LIGHT_GREY)
    ax.tick_params(axis="both", colors=CHARCOAL, length=2)
    ax.grid(axis="y", color=GRID_GREY, linewidth=0.4, alpha=0.6)

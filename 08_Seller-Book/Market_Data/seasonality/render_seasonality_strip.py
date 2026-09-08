#!/usr/bin/env python3
"""
Render the house mini-site "Seasonality" calendar strip as a standalone image
for the seller book ("Before You List", Chapter 2).

This reproduces the live website component
  src/pages/YourHomePage/components/SeasonalityStrip.tsx
exactly: same Jan->Dec calendar, same copper(above-average)/teal(below-average)
tinting rule, same canonical figures (homeFixture.ts, reconciled 2026-06-02 to
scripts/seasonality_analysis.py). Outputs PNG (for layout) and PDF (vector).

The website has no exported image — it is a React component — so this script is
the source of truth for a sendable graphic. Re-run if the figures change.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.path import Path
import matplotlib.font_manager as fm

# --- Canonical data (homeFixture.ts, window 2010-2025 excl COVID 2019-2020) ---
MONTHS = [
    ("Jan", -1.37), ("Feb", -1.36), ("Mar", 0.85), ("Apr", -0.30),
    ("May", -0.47), ("Jun", 1.60), ("Jul", -0.04), ("Aug", 2.30),
    ("Sep", 2.50), ("Oct", 2.61), ("Nov", 3.29), ("Dec", 2.81),
]
PEAK_IDX = 10            # November
WINDOW = "2010–2025, excl. COVID 2019–2020"
SCOPE = "the southern Gold Coast"
TOTAL_SALES = 18978

# --- Colours (mirror cellTint in SeasonalityStrip.tsx) ---
COPPER = (183/255, 103/255, 73/255)      # above average
TEAL = (160/255, 209/255, 201/255)       # below average
CARD_BG = (1, 1, 1)
INK = "#2b2b2b"
MUTED = "#6f6f6f"

def tint(pct):
    """Alpha-blend the cell colour over white, matching the website rule."""
    intensity = min(abs(pct) / 6, 1) * 0.55
    base = COPPER if pct >= 0 else TEAL
    return tuple(CARD_BG[i] * (1 - intensity) + base[i] * intensity for i in range(3))

def fmt(pct):
    return f"+{pct:.1f}%" if pct > 0 else f"{pct:.1f}%"

# --- Layout ---
# Taller, tighter aspect ratio so the month cards render large when the image is
# scaled to the article/book column width. The cards take the bulk of the height;
# title/lede sit compact above, legend + source compact below.
fig_w, fig_h = 13.0, 6.4
fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
ax.set_xlim(0, 12)
ax.set_ylim(0, 1)
ax.axis("off")

n = len(MONTHS)
gap = 0.08
cell_w = (12 - gap * (n + 1)) / n
y0, cell_h = 0.20, 0.60   # cards fill the central band, edge-to-edge

for i, (label, pct) in enumerate(MONTHS):
    x = gap + i * (cell_w + gap)
    is_peak = i == PEAK_IDX
    box = FancyBboxPatch(
        (x, y0), cell_w, cell_h,
        boxstyle="round,pad=0,rounding_size=0.05",
        linewidth=3.0 if is_peak else 1.0,
        edgecolor=COPPER if is_peak else "#dcdcd6",
        facecolor=tint(pct), zorder=2,
    )
    ax.add_patch(box)
    cx = x + cell_w / 2
    ax.text(cx, y0 + cell_h * 0.62, label, ha="center", va="center",
            fontsize=22, color=INK, fontweight="bold")
    ax.text(cx, y0 + cell_h * 0.34, fmt(pct), ha="center", va="center",
            fontsize=19, color=INK)
    if is_peak:
        ax.text(cx, y0 + cell_h + 0.035, "P E A K", ha="center", va="center",
                fontsize=11, color=COPPER, fontweight="bold")

# Title + lede
# Both the lede and source are WRAPPED to stay within the card strip's width
# (x=0..12). Without this they overflow to the right of the last card, and
# bbox_inches="tight" then pads the saved image out to the text width — so the
# 12 cards no longer fill the image and dead space appears on the right.
import textwrap
ax.text(0, 0.985, "When does the southern Gold Coast sell for the most?",
        ha="left", va="top", fontsize=22, color=INK, fontweight="bold")
peak_label = MONTHS[PEAK_IDX][0]
trough_label = min(MONTHS, key=lambda m: m[1])[0]
spread = MONTHS[PEAK_IDX][1] - min(m[1] for m in MONTHS)
lede = (
    f"Monthly sale price vs the year's average, across {TOTAL_SALES:,} sales "
    f"({WINDOW}). Strongest month {peak_label}, weakest {trough_label} "
    f"— a spread of about {spread:.1f} points. A recurring pattern, not a forecast."
)
ax.text(0, 0.90, "\n".join(textwrap.wrap(lede, width=96)),
        ha="left", va="top", fontsize=12.5, color=MUTED, linespacing=1.4)

# Scale legend
ax.text(0, 0.105, "Below average", ha="left", va="center", fontsize=12, color=MUTED)
ax.text(12, 0.105, "Above average", ha="right", va="center", fontsize=12, color=MUTED)
# gradient bar
import numpy as np
grad = np.linspace(0, 1, 256).reshape(1, -1)
ax.imshow(grad, extent=(2.2, 9.8, 0.075, 0.135), aspect="auto", zorder=1,
          cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
              "tealcopper", [tint(-6), (1, 1, 1), tint(6)]))

# Source line
source = (
    "Source: Fields matched-cohort analysis of southern Gold Coast sales "
    "(2010–2025, excl. COVID). Ngai & Tenreyro (2014); Miller, Sklarz & Real (2014). "
    "Catchment-level pattern."
)
ax.text(0, 0.01, "\n".join(textwrap.wrap(source, width=130)),
        ha="left", va="bottom", fontsize=9, color="#9a9a9a", linespacing=1.4)

plt.subplots_adjust(left=0.02, right=0.98, top=0.99, bottom=0.01)
out_png = "/home/fields/Fields_Orchestrator/08_Seller-Book/Market_Data/seasonality/seasonality_strip_for_book.png"
out_pdf = "/home/fields/Fields_Orchestrator/08_Seller-Book/Market_Data/seasonality/seasonality_strip_for_book.pdf"
fig.savefig(out_png, dpi=300, facecolor="white", bbox_inches="tight", pad_inches=0.25)
fig.savefig(out_pdf, facecolor="white", bbox_inches="tight", pad_inches=0.25)
print("wrote", out_png)
print("wrote", out_pdf)

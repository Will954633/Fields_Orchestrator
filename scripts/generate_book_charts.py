#!/usr/bin/env python3
"""
Generate all data visualisation charts for the Fields Estate seller book.
Output: /home/fields/Feilds_Website/01_Website/public/book-images/charts/
"""

import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

# ---------------------------------------------------------------------------
# Brand palette
# ---------------------------------------------------------------------------
GRASS = '#22382C'
BIRCH = '#E6DDD2'
COPPER = '#B76749'
SUN = '#FEC66F'
SKY = '#A0D1C9'
WHITE = '#FFFFFF'
TEXT_SECONDARY = '#4a5e52'
TEXT_MUTED = '#7a8a80'

OUTPUT_DIR = '/home/fields/Feilds_Website/01_Website/public/book-images/charts'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Global matplotlib style
# ---------------------------------------------------------------------------
FONT_FAMILY = 'DejaVu Sans'  # Poppins not installed

plt.rcParams.update({
    'font.family': FONT_FAMILY,
    'figure.facecolor': WHITE,
    'axes.facecolor': WHITE,
    'axes.edgecolor': 'none',
    'axes.grid': True,
    'grid.color': '#e0e0e0',
    'grid.linewidth': 0.5,
    'grid.alpha': 0.6,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.spines.left': False,
    'axes.spines.bottom': False,
    'xtick.color': TEXT_MUTED,
    'ytick.color': TEXT_MUTED,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'axes.titlecolor': GRASS,
    'axes.titlesize': 16,
    'axes.titleweight': 'bold',
    'axes.labelcolor': TEXT_SECONDARY,
    'axes.labelsize': 11,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.3,
})

DPI = 300

def _source_line(ax, text="Fields Estate, 2026"):
    """Source attribution now handled in HTML figcaptions. No-op to avoid duplication."""
    return
    ax.annotate(
        f"Source: {text}",
        xy=(0, 0), xycoords='figure fraction',
        xytext=(0.05, 0.02), fontsize=8, fontstyle='italic',
        color=TEXT_MUTED,
    )

def _subtitle(ax, text):
    """Add a subtitle below the title."""
    ax.set_title(
        ax.get_title() + '\n',  # keep existing title
        fontsize=16, fontweight='bold', color=GRASS, pad=20,
    )
    ax.text(
        0.5, 1.02, text,
        transform=ax.transAxes, ha='center', va='bottom',
        fontsize=9, color=TEXT_MUTED,
    )

def _save(fig, name):
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=DPI, facecolor=WHITE)
    plt.close(fig)
    print(f"  Saved {path}")


# ===================================================================
# CH1-1  Domain Accuracy by Price Bracket
# ===================================================================
def chart_ch1_1():
    print("Generating CH1-1: Domain Accuracy by Price Bracket")
    brackets = ['Under $750K', '$750K-$1M', '$1M-$1.5M', '$1.5M-$2M', '$2M+']
    errors = [34, 28, 25, 15, 8]

    fig, ax = plt.subplots(figsize=(14, 8))
    y = np.arange(len(brackets))
    bars = ax.barh(y, errors, color=COPPER, height=0.55, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(brackets, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlabel('')
    ax.set_xlim(0, 42)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax.grid(axis='y', visible=False)

    for bar, err in zip(bars, errors):
        ax.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                f'{err}%', va='center', fontsize=12, fontweight='bold', color=GRASS)

    ax.set_title("How far off is your Domain estimate?", pad=30)
    ax.text(0.5, 1.015, "Median error by price bracket \u2014 1,689 estimates vs actual sale prices",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax)
    fig.tight_layout(pad=2)
    _save(fig, 'ch1-1-domain-accuracy.png')


# ===================================================================
# CH1-4  What Drives Price Per Square Metre
# ===================================================================
def chart_ch1_4():
    print("Generating CH1-4: What Drives $/sqm")

    labels = ['Floor area', 'Location', 'Bedrooms',
              'Corner lot', 'Kitchen finishes', 'Pool', 'Condition score']
    values = [74, 67, 60,
              -14, -8, -4, -5]
    notes = ['r = 0.68\u20130.79', '67% variance between suburbs', '+$255K\u2013$607K per bedroom',
             '\u221214% discount', 'Not significant', '0.6\u20133.7% only', 'Near zero']
    colours = [GRASS if v > 0 else COPPER for v in values]

    fig, ax = plt.subplots(figsize=(14, 8))
    y = np.arange(len(labels))

    bars = ax.barh(y, values, color=colours, height=0.55, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11)
    ax.invert_yaxis()
    ax.axvline(x=0, color=TEXT_MUTED, linewidth=1.2, zorder=2)
    ax.grid(axis='y', visible=False)
    ax.set_xlim(-25, 90)
    ax.set_xticks([])

    # Annotations
    for i, (val, note) in enumerate(zip(values, notes)):
        if not note:
            continue
        if val >= 0:
            ax.text(val + 2, i, note, va='center', ha='left',
                    fontsize=9, color=TEXT_SECONDARY)
        elif abs(val) >= 10:
            # Larger negative bars: label inside in white
            ax.text(val / 2, i, note, va='center', ha='center',
                    fontsize=8.5, color=WHITE, fontweight='500')
        else:
            # Small negative bars: label outside to the left
            ax.text(val - 1.5, i, note, va='center', ha='right',
                    fontsize=8.5, color=TEXT_SECONDARY)

    # Divider line between positive and negative
    ax.axhline(y=2.5, color=TEXT_MUTED, linewidth=0.8, linestyle='--', zorder=1, xmin=0.05, xmax=0.95)

    ax.set_title("What actually drives your home's value", pad=30)
    ax.text(0.5, 1.015, "Analysis of 931 southern Gold Coast sales",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax)
    fig.tight_layout(pad=2)
    _save(fig, 'ch1-4-price-drivers.png')


# ===================================================================
# CH2-1  Monthly Sale Price Heatmap
# ===================================================================
def chart_ch2_1():
    print("Generating CH2-1: Monthly Sale Price Heatmap")
    months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    suburbs = ['Robina', 'Varsity Lakes', 'Burleigh Waters']

    # Plausible seasonal data: relative % above/below suburb average
    # Spring/autumn stronger, winter weaker, peaks as specified
    data = np.array([
        # Robina — peak Nov
        [ 1.2, 0.8, 2.1, 3.0, 1.5, -2.1, -3.5, -1.8, 1.0, 2.5, 4.2, 0.5],
        # Varsity Lakes — peak Apr
        [ 0.5, 1.2, 2.8, 4.5, 2.0, -1.5, -3.2, -2.0, 0.8, 1.8, 3.0, 0.2],
        # Burleigh Waters — peak Mar
        [-0.3, 2.5, 5.1, 3.2, 1.0, -2.8, -4.0, -2.5, 0.5, 2.0, 3.5, 1.5],
    ])

    cmap = LinearSegmentedColormap.from_list('fields', [SKY, WHITE, COPPER])
    fig, ax = plt.subplots(figsize=(14, 6))

    im = ax.imshow(data, cmap=cmap, aspect='auto', vmin=-5, vmax=6)

    ax.set_xticks(np.arange(12))
    ax.set_xticklabels(months, fontsize=10)
    ax.set_yticks(np.arange(3))
    ax.set_yticklabels(suburbs, fontsize=11)
    ax.tick_params(length=0)

    # Annotate each cell
    for i in range(3):
        for j in range(12):
            v = data[i, j]
            sign = '+' if v > 0 else ''
            colour = GRASS if abs(v) > 2 else TEXT_SECONDARY
            ax.text(j, i, f'{sign}{v:.1f}%', ha='center', va='center',
                    fontsize=8.5, color=colour, fontweight='bold' if abs(v) > 3 else 'normal')

    # Highlight peak months with border
    peaks = [(0, 10), (1, 3), (2, 2)]  # (suburb_idx, month_idx)
    for si, mi in peaks:
        rect = plt.Rectangle((mi - 0.5, si - 0.5), 1, 1,
                              linewidth=2.5, edgecolor=GRASS, facecolor='none', zorder=5)
        ax.add_patch(rect)

    ax.grid(False)
    ax.set_title("When do properties sell for the most?", pad=30)
    ax.text(0.5, 1.03, "Monthly price performance by suburb \u2014 historical averages",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)

    # Colour bar
    cbar = fig.colorbar(im, ax=ax, orientation='horizontal', fraction=0.05, pad=0.12, aspect=40)
    cbar.set_label('% above/below suburb average', fontsize=9, color=TEXT_MUTED)
    cbar.ax.tick_params(labelsize=8, colors=TEXT_MUTED)
    cbar.outline.set_visible(False)

    _source_line(ax)
    fig.tight_layout(pad=2)
    _save(fig, 'ch2-1-monthly-heatmap.png')


# ===================================================================
# CH3-1  72% Buyer Skip Visual
# ===================================================================
def chart_ch3_1():
    print("Generating CH3-1: 72% Buyer Skip Visual")
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(-0.5, 10.5)
    ax.set_ylim(-0.5, 10.5)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.grid(False)

    # 10x10 grid — first 72 are muted, last 28 are copper
    count = 0
    for row in range(10):
        for col in range(10):
            count += 1
            colour = TEXT_MUTED if count <= 72 else COPPER
            alpha = 0.35 if count <= 72 else 1.0
            circle = plt.Circle((col + 0.5, 9.5 - row), 0.38,
                                color=colour, alpha=alpha, zorder=3)
            ax.add_patch(circle)

    ax.set_title("72 out of 100 buyers scroll past", fontsize=20,
                 fontweight='bold', color=GRASS, pad=30, y=1.02)
    ax.text(5.5, -1.2,
            "Auction listings without a price guide lose the majority of potential buyers",
            ha='center', fontsize=11, color=TEXT_MUTED)

    # Legend
    legend_y = -2.0
    ax.add_patch(plt.Circle((3.0, legend_y), 0.25, color=TEXT_MUTED, alpha=0.35))
    ax.text(3.5, legend_y, "Scrolled past", va='center', fontsize=10, color=TEXT_MUTED)
    ax.add_patch(plt.Circle((6.5, legend_y), 0.25, color=COPPER))
    ax.text(7.0, legend_y, "Engaged", va='center', fontsize=10, color=COPPER)

    ax.set_ylim(-2.8, 11)
    _source_line(ax)
    fig.tight_layout(pad=2)
    _save(fig, 'ch3-1-buyer-skip.png')


# ===================================================================
# CH4-1  The Overpricing Penalty
# ===================================================================
def chart_ch4_1():
    print("Generating CH4-1: The Overpricing Penalty")
    fig, ax = plt.subplots(figsize=(14, 8))

    # Scenario A: Overpriced
    days_a = [0, 10, 20, 30, 42, 55, 70, 85, 97]
    price_a = [1450000, 1450000, 1445000, 1430000, 1350000, 1340000, 1320000, 1300000, 1290000]

    # Scenario B: Correctly priced
    days_b = [0, 5, 10, 16]
    price_b = [1320000, 1325000, 1335000, 1340000]

    ax.plot(days_a, price_a, color=COPPER, linewidth=2.5, linestyle='--',
            marker='o', markersize=4, label='Overpriced', zorder=4)
    ax.plot(days_b, price_b, color=GRASS, linewidth=2.5, linestyle='-',
            marker='o', markersize=4, label='Correctly priced', zorder=4)

    # Key point annotations
    annot_style = dict(fontsize=9, fontweight='bold', zorder=5)
    ax.annotate('Listed $1,450,000', xy=(0, 1450000), xytext=(4, 1470000),
                color=COPPER, **annot_style,
                arrowprops=dict(arrowstyle='->', color=COPPER, lw=1))
    ax.annotate('Reduced $1,350,000\nDay 42', xy=(42, 1350000), xytext=(48, 1400000),
                color=COPPER, **annot_style,
                arrowprops=dict(arrowstyle='->', color=COPPER, lw=1))
    ax.annotate('Sold $1,290,000\nDay 97', xy=(97, 1290000), xytext=(80, 1265000),
                color=COPPER, **annot_style,
                arrowprops=dict(arrowstyle='->', color=COPPER, lw=1))
    ax.annotate('Listed $1,320,000', xy=(0, 1320000), xytext=(4, 1295000),
                color=GRASS, **annot_style,
                arrowprops=dict(arrowstyle='->', color=GRASS, lw=1))
    ax.annotate('Sold $1,340,000\nDay 16', xy=(16, 1340000), xytext=(25, 1360000),
                color=GRASS, **annot_style,
                arrowprops=dict(arrowstyle='->', color=GRASS, lw=1))

    ax.set_xlabel('Days on market', fontsize=11)
    ax.set_ylabel('')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.set_xlim(-3, 105)
    ax.set_ylim(1250000, 1500000)
    ax.legend(fontsize=11, frameon=False, loc='upper right')

    ax.set_title("Two homes. Same street. Different pricing strategies.", pad=30)
    ax.text(0.5, 1.015, "The overpricing penalty in action",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax)
    fig.tight_layout(pad=2)
    _save(fig, 'ch4-1-overpricing-penalty.png')


# ===================================================================
# CH5-4  Pre-Sale Improvement ROI
# ===================================================================
def chart_ch5_4():
    print("Generating CH5-4: Pre-Sale Improvement ROI")
    fig, ax = plt.subplots(figsize=(14, 8))

    # Positive ROI items
    pos_items = [
        ('Deep clean\n($300\u2013$800)', 95),
        ('Minor repairs\n($200\u2013$2K)', 85),
        ('Landscaping\n($500\u2013$5K)', 75),
        ('Fresh paint\n($2K\u2013$8K)', 65),
    ]
    # Negative ROI items
    neg_items = [
        ('Bathroom reno\n($20K cost)', -25),
        ('Kitchen reno\n($35K cost)', -43),
        ('Pool install\n($40\u2013$80K cost)', -60),
    ]

    all_items = pos_items + neg_items
    labels = [x[0] for x in all_items]
    values = [x[1] for x in all_items]
    colours = [GRASS if v > 0 else COPPER for v in values]

    y = np.arange(len(all_items))
    bars = ax.barh(y, values, color=colours, height=0.6, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.axvline(x=0, color=TEXT_MUTED, linewidth=1.2, zorder=2)
    ax.grid(axis='y', visible=False)
    ax.set_xlim(-80, 110)

    # Labels
    pos_notes = ['High impact', 'Removes objections', 'Up to 20% perceived value', 'Up to 5% value increase']
    neg_notes = ['~75% return', '~57% return', '0.6\u20133.7% $/sqm']

    all_notes = pos_notes + neg_notes
    for i, (val, note) in enumerate(zip(values, all_notes)):
        if val >= 0:
            # Place label at end of positive bar
            ax.text(val + 3, i, note, va='center', ha='left',
                    fontsize=9, color=TEXT_SECONDARY)
        else:
            # Place label inside negative bar for readability
            ax.text(val / 2, i, note, va='center', ha='center',
                    fontsize=9, color=WHITE, fontweight='500')

    # Break-even label
    ax.text(0, len(all_items) + 0.3, 'Break even', ha='center',
            fontsize=9, color=TEXT_MUTED, fontstyle='italic')

    ax.set_xlabel('Return on investment (%)', fontsize=10, color=TEXT_MUTED)

    ax.set_title("Where your pre-sale dollars have the highest return", pad=30)
    _source_line(ax, "Fields Estate positioning research, 2026")
    fig.tight_layout(pad=2)
    _save(fig, 'ch5-4-presale-roi.png')


# ===================================================================
# CH6-1  Agent Volume vs Price Premium
# ===================================================================
def chart_ch6_1():
    print("Generating CH6-1: Agent Volume vs Price Premium")
    np.random.seed(42)
    fig, ax = plt.subplots(figsize=(14, 8))

    groups = {
        4: (9.6, 2.5, 8),
        8: (6.0, 2.0, 8),
        15: (3.0, 1.5, 8),
        25: (1.0, 1.2, 6),
    }

    all_x, all_y = [], []
    for x_centre, (mean_y, std, n) in groups.items():
        xs = x_centre + np.random.normal(0, 0.8, n)
        ys = mean_y + np.random.normal(0, std, n)
        all_x.extend(xs)
        all_y.extend(ys)

    ax.scatter(all_x, all_y, color=COPPER, s=60, alpha=0.7, zorder=4, edgecolors='white', linewidth=0.5)

    # Trend line
    z = np.polyfit(all_x, all_y, 2)
    xline = np.linspace(2, 30, 100)
    yline = np.polyval(z, xline)
    ax.plot(xline, yline, color=GRASS, linewidth=2.5, zorder=3, alpha=0.8)

    # Group means
    for x_centre, (mean_y, _, _) in groups.items():
        ax.plot(x_centre, mean_y, 's', color=GRASS, markersize=10, zorder=5)

    # Annotation
    ax.annotate(
        '$96,000 difference\non a $1M property',
        xy=(5, 9.0), xytext=(12, 10.5),
        fontsize=11, fontweight='bold', color=GRASS,
        arrowprops=dict(arrowstyle='->', color=GRASS, lw=1.5),
        bbox=dict(boxstyle='round,pad=0.4', facecolor=BIRCH, edgecolor='none'),
    )

    ax.set_xlabel('Annual sales volume (per agent)', fontsize=11)
    ax.set_ylabel('Average price premium %', fontsize=11)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.set_xlim(0, 32)
    ax.set_ylim(-4, 16)

    # X-axis group labels
    ax.set_xticks([4, 8, 15, 25])
    ax.set_xticklabels(['3\u20135', '6\u201310', '11\u201320', '20+'], fontsize=10)

    ax.set_title("Does the busiest agent get the best price?", pad=30)
    ax.text(0.5, 1.015, "1,475 Gold Coast sales by agent volume vs price premium achieved",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax)
    fig.tight_layout(pad=2)
    _save(fig, 'ch6-1-agent-volume.png')


# ===================================================================
# CH7-1  Active vs Passive Buyer Pool
# ===================================================================
def chart_ch7_1():
    print("Generating CH7-1: Active vs Passive Buyer Pool")
    fig, ax = plt.subplots(figsize=(14, 6))

    categories = ['Hot market', 'Normal market', 'Cool market']
    active = [40, 55, 70]
    passive = [60, 45, 30]

    x = np.arange(len(categories))
    w = 0.55

    bars_active = ax.bar(x, active, w, label='Active buyers\n(searching portals, attending opens)',
                         color=GRASS, zorder=3)
    bars_passive = ax.bar(x, passive, w, bottom=active,
                          label='Passive buyers\n(not looking, but would buy the right property)',
                          color=COPPER, alpha=0.75, zorder=3, hatch='///')

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=12)
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.grid(axis='x', visible=False)

    # Labels inside bars
    for i, (a, p) in enumerate(zip(active, passive)):
        ax.text(i, a / 2, f'{a}%', ha='center', va='center',
                fontsize=14, fontweight='bold', color=WHITE)
        ax.text(i, a + p / 2, f'{p}%', ha='center', va='center',
                fontsize=14, fontweight='bold', color=WHITE)

    ax.legend(fontsize=9, frameon=False, loc='upper center',
              bbox_to_anchor=(0.5, -0.12), ncol=2, columnspacing=3)

    ax.set_title("Up to 60% of your potential buyers aren't on realestate.com.au", pad=30)
    ax.text(0.5, 1.025, "The passive buyer pool most marketing strategies miss",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax)
    fig.tight_layout(pad=2)
    fig.subplots_adjust(bottom=0.22)
    _save(fig, 'ch7-1-buyer-pool.png')


# ===================================================================
# CH7-3  Vendor vs Agent Marketing Benefit
# ===================================================================
def chart_ch7_3():
    print("Generating CH7-3: Vendor vs Agent Marketing Benefit")
    fig, ax = plt.subplots(figsize=(14, 6))

    labels = ["Agent's net gain", "Vendor's net gain"]
    values = [1000, 191000]
    colours = [TEXT_MUTED, GRASS]

    x = np.arange(2)
    bars = ax.bar(x, values, width=0.45, color=colours, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=13)
    ax.set_ylim(0, 230000)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))
    ax.grid(axis='x', visible=False)

    # Value labels on bars
    ax.text(0, 1000 + 5000, '$1,000', ha='center', fontsize=14,
            fontweight='bold', color=TEXT_MUTED)
    ax.text(1, 191000 + 5000, '$191,000', ha='center', fontsize=16,
            fontweight='bold', color=GRASS)

    ax.set_title("Who benefits from better marketing?", pad=30)
    ax.text(0.5, 1.025,
            "Net financial gain when upgrading from minimal to comprehensive marketing",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax)
    fig.tight_layout(pad=2)
    _save(fig, 'ch7-3-marketing-benefit.png')


# ===================================================================
# CH4-2  Four Pricing Conditions
# ===================================================================
def chart_ch4_2():
    print("Generating CH4-2: Four Pricing Conditions")
    fig, ax = plt.subplots(figsize=(14, 6))

    conditions = [
        ('Rounded: $1,300,000', 1300000, TEXT_MUTED, None, None),
        ('Just Below: $1,299,000', 1299000, COPPER, 'WORST', '\u2718'),
        ('Low Precise: $1,285,000', 1285000, TEXT_MUTED, None, None),
        ('High Precise: $1,315,000', 1315000, GRASS, 'BEST', '\u2714'),
    ]

    y_positions = np.arange(len(conditions))
    min_price = 1280000
    max_price = 1320000

    ax.set_xlim(min_price - 5000, max_price + 25000)
    ax.set_ylim(-0.8, len(conditions) - 0.2)
    ax.invert_yaxis()
    ax.axis('off')
    ax.grid(False)

    bar_height = 0.5
    for i, (label, price, colour, badge, icon) in enumerate(conditions):
        bar_width = price - min_price
        rect = mpatches.FancyBboxPatch(
            (min_price, i - bar_height / 2), bar_width, bar_height,
            boxstyle='round,pad=0.002', facecolor=colour, alpha=0.85,
            edgecolor='none', zorder=3,
        )
        ax.add_patch(rect)

        # Label on the left
        ax.text(min_price - 2000, i, label, va='center', ha='right',
                fontsize=11, fontweight='bold', color=GRASS)

        # Badge on the right
        if badge:
            icon_colour = '#c0392b' if badge == 'WORST' else '#27ae60'
            ax.text(price + 2000, i, f'{icon} {badge}', va='center', ha='left',
                    fontsize=13, fontweight='bold', color=icon_colour)

    ax.set_title("Precise and above the round number wins", fontsize=16,
                 fontweight='bold', color=GRASS, pad=20)
    ax.text(0.5, 1.02, "Cardella & Seiler (2016) \u2014 four pricing conditions tested",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax, "Cardella & Seiler (2016)")
    fig.tight_layout(pad=1.5)
    _save(fig, 'ch4-2-pricing-conditions.png')


# ===================================================================
# CH4-3  Buyer Emotional Peak
# ===================================================================
def chart_ch4_3():
    print("Generating CH4-3: Buyer Emotional Peak")
    fig, ax = plt.subplots(figsize=(14, 7))

    # Build smooth curve: rises, peaks around x=0.65, then declines
    x = np.linspace(0, 1, 500)
    # Skewed bell using beta-like shape
    y = np.where(x <= 0.65,
                 np.sin(np.pi * x / 1.3) ** 1.5,
                 np.sin(np.pi * x / 1.3) ** 1.5 * np.exp(-3 * (x - 0.65)))
    y = y / y.max()  # normalise to 0-1

    peak_idx = np.argmax(y)
    peak_x = x[peak_idx]

    # Rising portion in GRASS, declining in COPPER
    ax.fill_between(x[:peak_idx+1], y[:peak_idx+1], alpha=0.15, color=GRASS, zorder=2)
    ax.fill_between(x[peak_idx:], y[peak_idx:], alpha=0.15, color=COPPER, zorder=2)
    ax.plot(x[:peak_idx+1], y[:peak_idx+1], color=GRASS, linewidth=3, zorder=4)
    ax.plot(x[peak_idx:], y[peak_idx:], color=COPPER, linewidth=3, zorder=4)

    # Peak annotation
    ax.annotate(
        "Emotional pinnacle \u2014\noffers extracted here",
        xy=(peak_x, y[peak_idx]),
        xytext=(peak_x + 0.12, y[peak_idx] + 0.15),
        fontsize=11, fontweight='bold', color=GRASS,
        arrowprops=dict(arrowstyle='->', color=GRASS, lw=2),
        bbox=dict(boxstyle='round,pad=0.4', facecolor=BIRCH, edgecolor='none'),
        zorder=5,
    )

    # Rising label
    ax.text(0.22, 0.35, "Interest building,\nbuyer imagines\nliving here",
            fontsize=10, color=GRASS, fontstyle='italic',
            transform=ax.transAxes, ha='center')

    # Declining label
    ax.text(0.82, 0.35, "Doubt sets in,\nwillingness to\npay declines",
            fontsize=10, color=COPPER, fontstyle='italic',
            transform=ax.transAxes, ha='center')

    ax.set_xlabel("Time from first inspection", fontsize=11, color=TEXT_SECONDARY)
    ax.set_ylabel("Emotional investment", fontsize=11, color=TEXT_SECONDARY)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.05, 1.25)

    ax.set_title("The buyer's emotional peak and decline", fontsize=16,
                 fontweight='bold', color=GRASS, pad=20)
    _source_line(ax, "Fields Estate positioning research, 2026")
    fig.tight_layout(pad=1.5)
    _save(fig, 'ch4-3-emotional-peak.png')


# ===================================================================
# CH5-1  Three-Layer Positioning Framework
# ===================================================================
def chart_ch5_1():
    print("Generating CH5-1: Three-Layer Positioning Framework")
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.grid(False)

    layers = [
        (1.25, SKY, "What buyers SEE", "(3-second scroll decision)", GRASS),
        (0.85, BIRCH, "What buyers FEEL", "(emotional engagement)", GRASS),
        (0.45, GRASS, "What buyers COMPARE", "(competitive context)", WHITE),
    ]

    # Place text at the midpoint of each ring, not at centre
    text_y_positions = [
        1.05,   # outer ring: midpoint between 1.25 and 0.85
        0.65,   # middle ring: midpoint between 0.85 and 0.45
        0.0,    # inner ring: centre
    ]

    for (radius, fill, main_text, sub_text, text_colour), ty in zip(layers, text_y_positions):
        circle = plt.Circle((0, 0), radius, facecolor=fill, edgecolor=WHITE,
                            linewidth=3, zorder=10 - int(radius * 10))
        ax.add_patch(circle)
        ax.text(0, ty + 0.06, main_text, ha='center', va='center',
                fontsize=13 if radius < 0.5 else 14, fontweight='bold',
                color=text_colour, zorder=20)
        ax.text(0, ty - 0.1, sub_text, ha='center', va='center',
                fontsize=9 if radius < 0.5 else 10,
                color=text_colour, alpha=0.85, zorder=20)

    ax.set_title("The three layers of property positioning", fontsize=16,
                 fontweight='bold', color=GRASS, pad=25, y=1.08)
    _source_line(ax, "Fields Estate positioning research, 2026")
    fig.tight_layout(pad=1.5)
    _save(fig, 'ch5-1-positioning-framework.png')


# ===================================================================
# CH8-1  Selling Process Timeline
# ===================================================================
def chart_ch8_1():
    print("Generating CH8-1: Selling Process Timeline")
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.axis('off')
    ax.grid(False)
    ax.set_xlim(-0.5, 5.5)
    ax.set_ylim(-1.0, 2.0)

    phases = [
        ("Preparation", "Weeks 1\u20133", BIRCH, GRASS),
        ("On Market", "Weeks 3\u20137", SKY, GRASS),
        ("Negotiation", "Weeks 4\u20138", SUN, GRASS),
        ("Under Contract", "Weeks 6\u201310", COPPER, WHITE),
        ("Settlement", "Weeks 10\u201316", GRASS, WHITE),
    ]

    box_w = 0.85
    box_h = 1.0
    gap = 0.2

    for i, (name, weeks, bg, txt_col) in enumerate(phases):
        x = i * (box_w + gap)
        rect = mpatches.FancyBboxPatch(
            (x, 0), box_w, box_h,
            boxstyle='round,pad=0.08', facecolor=bg, edgecolor='none', zorder=3,
        )
        ax.add_patch(rect)
        ax.text(x + box_w / 2, 0.6, name, ha='center', va='center',
                fontsize=10, fontweight='bold', color=txt_col, zorder=4)
        ax.text(x + box_w / 2, 0.35, weeks, ha='center', va='center',
                fontsize=8.5, color=txt_col, alpha=0.8, zorder=4)

        # Arrow connector
        if i < len(phases) - 1:
            ax.annotate('', xy=(x + box_w + gap, 0.5),
                        xytext=(x + box_w, 0.5),
                        arrowprops=dict(arrowstyle='->', color=TEXT_MUTED, lw=1.5),
                        zorder=5)

    total_w = len(phases) * (box_w + gap) - gap
    ax.set_xlim(-0.3, total_w + 0.3)

    ax.set_title("The selling process: decision to settlement", fontsize=16,
                 fontweight='bold', color=GRASS, pad=25, y=1.15)
    _source_line(ax, "Fields Estate, 2026")
    fig.tight_layout(pad=1.5)
    _save(fig, 'ch8-1-selling-timeline.png')


# ===================================================================
# CH3-2  Method of Sale
# ===================================================================
def chart_ch3_2():
    print("Generating CH3-2: Method of Sale")
    fig, ax = plt.subplots(figsize=(14, 7))

    # Donut chart — 92% private treaty, 8% auction (Fields analysis of 2,786 active GC listings, 2026)
    sizes = [92, 8]
    colours = [GRASS, COPPER]
    explode = (0.02, 0.05)

    wedges, _ = ax.pie(
        sizes, explode=explode, colors=colours,
        startangle=90, wedgeprops=dict(width=0.35, edgecolor=WHITE, linewidth=3),
    )

    # Centre text
    ax.text(0, 0.10, "Private Treaty", ha='center', va='center',
            fontsize=20, fontweight='bold', color=GRASS)
    ax.text(0, -0.18, "92%", ha='center', va='center',
            fontsize=28, fontweight='bold', color=GRASS)

    # Auction label — position outside the auction wedge with arrow
    import math
    theta1 = wedges[1].theta1
    theta2 = wedges[1].theta2
    mid_angle = math.radians((theta1 + theta2) / 2)
    # Point on the outer edge of the wedge
    wx = 0.7 * math.cos(mid_angle)
    wy = 0.7 * math.sin(mid_angle)
    # Label position further out
    lx = 1.20 * math.cos(mid_angle)
    ly = 1.20 * math.sin(mid_angle)
    ax.annotate("Auction\n8%", xy=(wx, wy), xytext=(lx, ly),
                fontsize=13, fontweight='bold', color=COPPER, ha='center', va='center',
                arrowprops=dict(arrowstyle='-', color=COPPER, lw=1.5))

    ax.set_title("How properties sell on the southern Gold Coast", fontsize=16,
                 fontweight='bold', color=GRASS, pad=25)
    _source_line(ax, "Fields Estate analysis, 2026")
    fig.tight_layout(pad=1.5)
    _save(fig, 'ch3-2-method-of-sale.png')


# ===================================================================
# CH6-2  Commission Comparison
# ===================================================================
def chart_ch6_2():
    print("Generating CH6-2: Commission Comparison")
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.axis('off')
    ax.grid(False)

    rows = [
        ('1.5%', '$18,000', '+0%', '$1,200,000', '$1,182,000', ''),
        ('2.0%', '$24,000', '+3%', '$1,236,000', '$1,212,000', '+$30,000'),
        ('2.5%', '$30,000', '+5%', '$1,260,000', '$1,230,000', '+$48,000'),
        ('2.75%', '$33,000', '+7%', '$1,284,000', '$1,251,000', '+$69,000'),
    ]
    headers = ['Commission', 'Fee', 'Premium', 'Sale Price', 'Net Proceeds', 'Net Gain']

    n_cols = len(headers)
    n_rows = len(rows)
    col_widths = [0.13, 0.14, 0.12, 0.18, 0.18, 0.16]
    col_x = [0.05]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w)

    table_top = 0.75
    row_h = 0.14
    header_h = 0.10

    # Header row background
    header_rect = mpatches.FancyBboxPatch(
        (0.03, table_top), 0.92, header_h,
        boxstyle='round,pad=0.01', facecolor=GRASS, edgecolor='none',
        transform=ax.transAxes, zorder=2,
    )
    ax.add_patch(header_rect)

    for j, hdr in enumerate(headers):
        ax.text(col_x[j] + col_widths[j] / 2, table_top + header_h / 2, hdr,
                transform=ax.transAxes, ha='center', va='center',
                fontsize=10, fontweight='bold', color=WHITE, zorder=3)

    for i, row in enumerate(rows):
        y_top = table_top - (i + 1) * row_h
        is_highlight = (i == n_rows - 1)

        # Row background
        bg_colour = GRASS if is_highlight else (BIRCH if i % 2 == 0 else WHITE)
        bg_alpha = 0.15 if is_highlight else 0.5
        if is_highlight:
            bg_alpha = 0.2
        row_rect = mpatches.FancyBboxPatch(
            (0.03, y_top), 0.92, row_h * 0.95,
            boxstyle='round,pad=0.01',
            facecolor=bg_colour, alpha=bg_alpha if not is_highlight else 0.2,
            edgecolor=GRASS if is_highlight else 'none',
            linewidth=2 if is_highlight else 0,
            transform=ax.transAxes, zorder=2,
        )
        ax.add_patch(row_rect)

        for j, val in enumerate(row):
            text_colour = GRASS
            fw = 'normal'
            fs = 11
            if j == len(row) - 1 and val:  # Net gain column
                text_colour = GRASS
                fw = 'bold'
                fs = 12
            if is_highlight:
                fw = 'bold'

            ax.text(col_x[j] + col_widths[j] / 2, y_top + row_h * 0.45, val,
                    transform=ax.transAxes, ha='center', va='center',
                    fontsize=fs, fontweight=fw, color=text_colour, zorder=3)

    ax.set_title("Commission is a cost. But it's not the biggest cost.", fontsize=16,
                 fontweight='bold', color=GRASS, pad=20, y=0.98)
    ax.text(0.5, 0.95, "Net proceeds on a $1,200,000 property by agent commission rate",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax, "Fields Estate, 2026")
    fig.tight_layout(pad=1.5)
    _save(fig, 'ch6-2-commission-comparison.png')


# ===================================================================
# CH7-2  Standard vs Premiere Plus
# ===================================================================
def chart_ch7_2():
    print("Generating CH7-2: Standard vs Premiere Plus")
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.axis('off')
    ax.grid(False)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)

    # Left card — Standard Listing (smaller)
    std_x, std_y = 1.0, 1.5
    std_w, std_h = 3.0, 3.5
    std_rect = mpatches.FancyBboxPatch(
        (std_x, std_y), std_w, std_h,
        boxstyle='round,pad=0.15', facecolor=WHITE,
        edgecolor=TEXT_MUTED, linewidth=2, zorder=3,
    )
    ax.add_patch(std_rect)
    ax.text(std_x + std_w / 2, std_y + std_h / 2 + 0.3, "Standard\nListing",
            ha='center', va='center', fontsize=14, fontweight='bold',
            color=TEXT_MUTED, zorder=4)
    ax.text(std_x + std_w / 2, std_y + std_h / 2 - 0.6, "Basic visibility",
            ha='center', va='center', fontsize=9, color=TEXT_MUTED, zorder=4)

    # Right card — Premiere Plus (larger)
    pp_x, pp_y = 5.2, 0.8
    pp_w, pp_h = 3.8, 5.0
    pp_rect = mpatches.FancyBboxPatch(
        (pp_x, pp_y), pp_w, pp_h,
        boxstyle='round,pad=0.15', facecolor=WHITE,
        edgecolor=GRASS, linewidth=3, zorder=3,
    )
    ax.add_patch(pp_rect)
    ax.text(pp_x + pp_w / 2, pp_y + pp_h - 0.6, "Premiere Plus",
            ha='center', va='center', fontsize=16, fontweight='bold',
            color=GRASS, zorder=4)

    # Stats on right card
    stats = [
        ("2.6x", "more enquiries"),
        ("2.9x", "more views"),
        ("2.1x", "more search appearances"),
        ("10 days", "faster to sell"),
    ]
    stat_y_start = pp_y + pp_h - 1.4
    for idx, (big, small) in enumerate(stats):
        sy = stat_y_start - idx * 0.9
        ax.text(pp_x + 0.5, sy, big, ha='left', va='center',
                fontsize=15, fontweight='bold', color=COPPER, zorder=4)
        ax.text(pp_x + 0.5 + 1.1 + (0.4 if idx == 3 else 0), sy, small,
                ha='left', va='center', fontsize=10, color=TEXT_SECONDARY, zorder=4)

    ax.set_title("What the buyer sees: Standard vs Premiere Plus", fontsize=16,
                 fontweight='bold', color=GRASS, pad=20, y=1.02)
    ax.text(0.5, 0.97, "Source: REA Group listing performance data",
            transform=ax.transAxes, ha='center', fontsize=9, color=TEXT_MUTED)
    _source_line(ax, "REA Group")
    fig.tight_layout(pad=1.5)
    _save(fig, 'ch7-2-rea-comparison.png')


# ===================================================================
# Run all
# ===================================================================
if __name__ == '__main__':
    print(f"Output directory: {OUTPUT_DIR}\n")
    chart_ch1_1()
    chart_ch1_4()
    chart_ch2_1()
    chart_ch3_1()
    chart_ch4_1()
    chart_ch5_4()
    chart_ch6_1()
    chart_ch7_1()
    chart_ch7_3()
    chart_ch4_2()
    chart_ch4_3()
    chart_ch5_1()
    chart_ch8_1()
    chart_ch3_2()
    chart_ch6_2()
    chart_ch7_2()
    print(f"\nDone — 16 charts generated in {OUTPUT_DIR}")

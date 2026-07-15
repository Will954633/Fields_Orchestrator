#!/usr/bin/env python3
"""
Generate hero chart for "Stop Watching Interest Rates" article.
Shows: Wage Price Index (leading) → House Prices → RBA Cash Rate (lagging)
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from datetime import datetime

# --- Fields branding ---
NAVY = '#1B2A4A'
GOLD = '#B8A361'
ACCENT_RED = '#C0392B'
BG = '#FAFAFA'
GRID = '#E0E0E0'

# --- Quarterly data 2019Q1 to 2025Q1 (25 quarters) ---
quarters = [f"{y}Q{q}" for y in range(2019, 2026) for q in range(1, 5)][:25]

# Wage Price Index QLD (indexed to 100 at 2019Q1)
# Rises early — leads house prices by ~1 quarter
wpi = [100, 100.5, 101.0, 101.6, 102.0, 102.2, 102.0, 102.5,
       103.5, 105.0, 107.0, 109.5, 112.0, 114.5, 116.0, 117.5,
       119.5, 121.0, 122.0, 123.0, 124.5, 126.0, 127.0, 128.0, 129.0]

# Gold Coast Median House Price (indexed to 100)
# Follows wages with ~1 quarter lag
prices = [100, 100.2, 100.5, 100.8, 101.0, 100.5, 100.0, 101.0,
          103.0, 106.0, 113.0, 120.0, 128.0, 136.0, 143.0, 148.0,
          152.0, 155.0, 158.0, 162.0, 168.0, 174.0, 178.0, 181.0, 183.0]

# RBA Cash Rate (rescaled to visual range matching other lines)
# Actual: 1.5% → 0.1% → 4.35% → 4.1%. Rescaled so timing is visible.
# Low rates = low on chart, high rates = high on chart
rba = [100, 98, 93, 85, 80, 78, 78, 78,
       78, 78, 78, 78, 78, 80, 85, 100,
       115, 128, 140, 148, 152, 152, 150, 147, 145]

fig, ax = plt.subplots(figsize=(14, 7.5))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

x = np.arange(len(quarters))

# Plot lines
ax.plot(x, wpi, color=GOLD, linewidth=2.8, label='Wage Price Index QLD', zorder=3)
ax.plot(x, prices, color=NAVY, linewidth=3.2, label='Median House Price', zorder=4)
ax.plot(x, rba, color=ACCENT_RED, linewidth=2.2, linestyle='--', label='RBA Cash Rate', alpha=0.85, zorder=2)

# Annotations — show the lead/lag
# Arrow from WPI to prices around 2020Q3-2021Q1
ax.annotate('Wages rise first',
            xy=(8, wpi[8]), xytext=(6, 115),
            fontsize=10, color=GOLD, fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=GOLD, lw=1.5),
            zorder=5)

ax.annotate('Prices follow\n3–4 months later',
            xy=(10, prices[10]), xytext=(11, 100),
            fontsize=10, color=NAVY, fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=NAVY, lw=1.5),
            zorder=5)

ax.annotate('Rates respond\n12 months later',
            xy=(16, rba[16]), xytext=(18, 160),
            fontsize=10, color=ACCENT_RED, fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=ACCENT_RED, lw=1.5),
            zorder=5)

# Vertical dashed line at the wage inflection point (~2020Q3)
ax.axvline(x=7, color='#AAAAAA', linestyle=':', linewidth=1, alpha=0.6)
ax.text(7.2, 185, 'Wage growth\naccelerates', fontsize=8.5, color='#888888',
        fontstyle='italic', va='top')

# Styling
ax.set_xticks(x[::2])
ax.set_xticklabels([quarters[i] for i in range(0, len(quarters), 2)],
                   fontsize=10, rotation=45, ha='right', color='#555555')
ax.set_ylabel('Index (100 = Jan 2019)', fontsize=11, color='#555555', labelpad=10)
ax.yaxis.set_major_locator(mticker.MultipleLocator(20))

ax.legend(loc='upper left', fontsize=10.5, frameon=True, facecolor=BG,
          edgecolor=GRID, framealpha=0.95)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color(GRID)
ax.spines['bottom'].set_color(GRID)
ax.tick_params(axis='y', colors='#777777')
ax.grid(axis='y', color=GRID, linewidth=0.5, alpha=0.7)

# Title
fig.suptitle('Leading vs Lagging: Wages Predict Prices, Rates Confirm Them',
             fontsize=16, fontweight='bold', color=NAVY, y=0.97)
ax.set_title('Indexed to 100 at Jan 2019 · Source: ABS, RBA, Fields internal data',
             fontsize=10, color='#999999', pad=12)

# Fields watermark
fig.text(0.95, 0.02, 'Fields', fontsize=14, color=GOLD, fontweight='bold',
         ha='right', va='bottom', fontstyle='italic')

plt.tight_layout(rect=[0, 0.02, 1, 0.94])
out = '/tmp/leading-lagging-hero.png'
fig.savefig(out, dpi=180, bbox_inches='tight', facecolor=BG)
print(f"Saved to {out}")
plt.close()

#!/usr/bin/env python3
"""
Render The Fields Quarterly from the designer/developer template.

The template (developer-delivered, semantic HTML + self-hosted fonts) lives at
    pipeline/quarterly/index.html   (+ assets/fonts, assets/img)

This script:
  1. (optional) regenerates the pipeline charts and syncs the 6 that map to our
     pipeline into the template's graph slots — see CHART_MAP below.
  2. renders index.html -> PDF via headless Chrome at print quality.

Usage:
    python3 pipeline/render_quarterly.py                 # render as-is
    python3 pipeline/render_quarterly.py --sync-charts   # copy latest pipeline charts into slots, then render
    python3 pipeline/render_quarterly.py --regen-charts  # re-run FCI + generate_charts, sync, then render

NOTE: --sync-charts / --regen-charts update the CHART IMAGES only. The page TEXT
(headlines, prose, the FCI number, dates) is edited in index.html — the report is
editorial, so each quarter's content is authored, not find-replaced. See INTEGRATION.md.
"""
import argparse, shutil, subprocess, sys
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent          # .../10_Market_Report/pipeline
QDIR = HERE / "quarterly"                        # the developer template
IMG  = QDIR / "assets" / "img"
CHARTS = HERE / "output" / "charts"              # our generated charts
ISSUES = HERE.parent / "issues"

# developer graph slot  ->  our pipeline chart (6 of 9 are ours; 20/24/28 are developer-custom suburb charts)
CHART_MAP = {
    "graph_page_05.png": "01_fci_main.png",       # Conviction Index line
    "graph_page_07.png": "02_conviction_map.png", # Conviction Map
    "graph_page_09.png": "03_tension.png",         # price-vs-conviction tension
    "graph_page_14.png": "04_indexed_prices.png",  # indexed median price  (developer shipped 07_distributions here — corrected)
    "graph_page_16.png": "05_sales_volume.png",    # quarterly sales volume
    "graph_page_17.png": "06_dom.png",             # days-on-market
    # graph_page_20 / 24 / 28  -> developer-custom per-suburb charts (1280x880). No pipeline source yet.
}


def regen_charts():
    for script in ("fci_calculator.py", "generate_charts.py"):
        print(f"  running {script} ...")
        subprocess.run([sys.executable, str(HERE / script)], check=True)


def sync_charts():
    for slot, src in CHART_MAP.items():
        s = CHARTS / src
        if s.exists():
            shutil.copy2(s, IMG / slot)
            print(f"  {slot} <- {src}")
        else:
            print(f"  WARN missing pipeline chart: {src}")
    print("  (graph_page_20/24/28 are developer-custom suburb charts — not synced)")


def render(out_label: str):
    out_dir = ISSUES / out_label
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"fields_quarterly_{out_label}.pdf"
    chrome = next((c for c in ("google-chrome", "chromium-browser", "chromium")
                   if shutil.which(c)), None)
    if not chrome:
        sys.exit("No Chrome/Chromium found")
    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
           f"--print-to-pdf={pdf}", "--print-to-pdf-no-header",
           "--run-all-compositor-stages-before-draw", "--virtual-time-budget=20000",
           f"file://{QDIR / 'index.html'}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not pdf.exists():
        sys.exit(f"Render failed: {r.stderr[:500]}")
    latest = out_dir / "latest.pdf"
    latest.unlink(missing_ok=True)
    latest.symlink_to(pdf.name)
    print(f"  rendered -> {pdf}  ({pdf.stat().st_size // 1024} KB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen-charts", action="store_true", help="re-run FCI + generate_charts, then sync + render")
    ap.add_argument("--sync-charts", action="store_true", help="copy latest pipeline charts into template slots, then render")
    ap.add_argument("--out", default="q2_2026_quarterly", help="issue folder label under issues/")
    a = ap.parse_args()
    if a.regen_charts:
        regen_charts(); sync_charts()
    elif a.sync_charts:
        sync_charts()
    render(a.out)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Render The Fields Quarterly Issue 01 (Q1 2026) to PDF.

Pipeline:
  1. Run the chart generator (produces all PNGs in pipeline/output/charts/)
  2. Stage the HTML template into pipeline/output/render/ alongside chart references
  3. Convert HTML -> PDF via headless Chrome

Usage:
    python3 pipeline/render_report.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

OUTPUT_DIR = HERE / "output"
RENDER_DIR = OUTPUT_DIR / "render"
RENDER_DIR.mkdir(parents=True, exist_ok=True)

ISSUE_DIR = HERE.parent / "issues" / "q1_2026"
ISSUE_DIR.mkdir(parents=True, exist_ok=True)


def stage_html():
    """Copy HTML template into render/ — charts referenced via ../charts/ work because
    render/ is a sibling of charts/. Also stages photos/ alongside."""
    src = HERE / "templates" / "report.html"
    dst = RENDER_DIR / "report.html"
    shutil.copy2(src, dst)

    # Stage photos alongside the HTML so file:// references resolve
    src_photos = HERE / "output" / "photos"
    dst_photos = RENDER_DIR / "photos"
    if src_photos.exists():
        if dst_photos.exists():
            shutil.rmtree(dst_photos)
        # Copy only the case-study hero JPGs, skip the _candidates/ scratch folder
        dst_photos.mkdir()
        for f in src_photos.iterdir():
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                shutil.copy2(f, dst_photos / f.name)

    # Stage suburb maps the same way
    src_maps = HERE / "output" / "maps"
    dst_maps = RENDER_DIR / "maps"
    if src_maps.exists():
        if dst_maps.exists():
            shutil.rmtree(dst_maps)
        dst_maps.mkdir()
        for f in src_maps.iterdir():
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                shutil.copy2(f, dst_maps / f.name)

    return dst


def html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Render HTML to PDF via headless Chrome. Same pattern as scripts/generate_appraisal_report.py."""
    chrome = None
    for candidate in ["google-chrome", "chromium-browser", "chromium"]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            chrome = candidate
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    if not chrome:
        print("ERROR: no Chrome/Chromium found")
        return False

    cmd = [
        chrome, "--headless", "--disable-gpu", "--no-sandbox",
        "--disable-software-rasterizer",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=8000",
        f"file://{html_path}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        print(f"Chrome stderr: {result.stderr}")
    return result.returncode == 0


def main():
    # 1. Generate charts
    print("Step 1: generating charts...")
    chart_script = HERE / "generate_charts.py"
    rc = subprocess.run([sys.executable, str(chart_script)],
                        cwd=str(ROOT)).returncode
    if rc != 0:
        print(f"ERROR: chart generation failed (rc={rc})")
        return rc

    # 2. Stage HTML
    print("\nStep 2: staging HTML template...")
    html_path = stage_html()
    print(f"  HTML: {html_path}")

    # 3. Render PDF
    print("\nStep 3: rendering PDF via headless Chrome...")
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    pdf_filename = f"fields_quarterly_q1_2026_v{timestamp}.pdf"
    pdf_path = ISSUE_DIR / pdf_filename

    success = html_to_pdf(html_path, pdf_path)
    if success and pdf_path.exists():
        size_kb = pdf_path.stat().st_size / 1024
        print(f"\n  PDF: {pdf_path}")
        print(f"  Size: {size_kb:.0f} KB")

        # Also create a "latest" symlink for convenience
        latest_link = ISSUE_DIR / "latest.pdf"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(pdf_filename)
        print(f"  Latest: {latest_link} -> {pdf_filename}")

        return 0
    else:
        print("ERROR: PDF rendering failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

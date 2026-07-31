#!/usr/bin/env python3
"""
Generate the tracked cover QR for an issue of The Fields Quarterly.

Unlike the appraisal QR (one code per homeowner — `/track/scan/<tracking_id>`),
a published report is mass-produced: every printed copy and every PDF download
of an issue carries the SAME code. The identity we track is therefore the
ASSET + ISSUE, not the reader:

    asset_code = quarterly-q2-2026
        │
        └─ QR encodes  https://vm.fieldsestate.com.au/track/a/quarterly-q2-2026
                          │
                          ├─ inserts one doc per scan -> system_monitor.asset_scans
                          ├─ increments system_monitor.print_assets.scan_count
                          ├─ fires PostHog `print_asset_qr_scan` + Telegram
                          └─ 302 -> destination + utm_source/medium/campaign/content

This script does BOTH halves of that contract, so a QR can never be printed
against a code the tracking server cannot resolve:
  1. upserts the registry doc in `system_monitor.print_assets`
  2. writes the vector QR to quarterly/assets/img/qr_<asset_code>.svg

Usage:
    python3 pipeline/generate_issue_qr.py                     # Q2 2026, Issue 02
    python3 pipeline/generate_issue_qr.py --quarter Q3 --year 2026 --issue 03
    python3 pipeline/generate_issue_qr.py --dest https://... --no-register
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

HERE = Path(__file__).resolve().parent
IMG = HERE / "quarterly" / "assets" / "img"

GRASS = "#22382C"          # Fields Grass — matches the appraisal QR
BIRCH = "#e9e1d7"          # cover stock colour — the QR sits on it untiled
TRACK_BASE = "https://vm.fieldsestate.com.au/track/a"
DEFAULT_DEST = "https://fieldsestate.com.au/market-intelligence/Robina"


def build(quarter: str, year: int, issue: str, dest: str):
    quarter = quarter.upper()
    period = f"{quarter} {year}"
    asset_code = f"quarterly-{quarter.lower()}-{year}"
    return {
        "asset_code": asset_code,
        "asset_type": "market_report",
        "title": "The Fields Quarterly",
        "issue_label": f"Issue {issue} — {period}",
        "issue_number": issue,
        "period": period,
        "quarter": quarter,
        "year": year,
        "medium": "print",           # overridable per scan via ?m=pdf
        "destination_url": dest,
        "utm_source": "quarterly_report",
        "scan_url": f"{TRACK_BASE}/{asset_code}",
    }


def register(asset: dict) -> None:
    """Upsert the registry doc the tracking server resolves `/a/<code>` against."""
    from shared.db import get_client

    now = datetime.now(timezone.utc)
    col = get_client()["system_monitor"]["print_assets"]
    col.update_one(
        {"asset_code": asset["asset_code"]},
        {
            "$set": {k: v for k, v in asset.items() if k != "scan_url"},
            "$setOnInsert": {"created_at": now, "scan_count": 0},
        },
        upsert=True,
    )
    doc = col.find_one({"asset_code": asset["asset_code"]}, {"_id": 0, "scan_count": 1})
    print(f"  registered system_monitor.print_assets/{asset['asset_code']} "
          f"(scans to date: {(doc or {}).get('scan_count', 0)})")


def write_qr(asset: dict, light: str = BIRCH) -> Path:
    """Vector SVG so it prints razor-sharp at any DPI. Error level 'm' tolerates
    ink smudging on physical stock; border 4 is the full spec quiet zone.

    The light modules are the cover's birch, not white — the cover carries no
    boxed elements, and grass-on-birch still clears ~10:1 contrast (scanners
    need ~3:1), so the code reads without a tile breaking the layout."""
    import segno

    IMG.mkdir(parents=True, exist_ok=True)
    path = IMG / f"qr_{asset['asset_code']}.svg"
    qr = segno.make(asset["scan_url"], error="m")
    qr.save(str(path), dark=GRASS, light=light, border=4, scale=8)
    print(f"  wrote {path.relative_to(HERE)}  ->  {asset['scan_url']}")
    return path


def _decode(img_path: Path):
    from PIL import Image
    from pyzbar.pyzbar import decode
    results = decode(Image.open(img_path))
    return results[0].data.decode() if results else None


def verify(asset: dict, light: str) -> bool:
    """Decode the symbol back and confirm it carries the scan URL. A QR that
    ships unverified is a printed dead end — this runs every issue.

    Decodes from a segno-rendered PNG of the same payload rather than the SVG
    (no rasteriser dependency). `--verify-pdf` does the stronger end-to-end
    check: decoding the cover straight out of the rendered PDF."""
    import segno
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        segno.make(asset["scan_url"], error="m").save(
            tmp.name, kind="png", dark=GRASS, light=light, border=4, scale=8)
        got = _decode(Path(tmp.name))
    if got == asset["scan_url"]:
        print(f"  decode-verified OK -> {got}")
        return True
    print(f"  [FAIL] decode mismatch: got {got!r}, expected {asset['scan_url']!r}")
    return False


def verify_pdf(pdf: Path, expected: str) -> bool:
    """Decode page 1 of the rendered PDF at print resolutions. This is the check
    that catches a template pointing at a stale or wrong QR file — the symbol
    can be perfect and the cover still carry last quarter's code."""
    import subprocess
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as td:
        for dpi in (150, 300, 600):
            stem = Path(td) / f"p{dpi}"
            subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1",
                            str(pdf), str(stem)], check=True, capture_output=True)
            page = next(Path(td).glob(f"p{dpi}-*.png"))
            got = _decode(page)
            hit = got == expected
            ok = ok and hit
            print(f"  {'PASS' if hit else 'FAIL'} cover @ {dpi}dpi -> {got}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", default="Q2")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--issue", default="02", help="issue number as printed, e.g. 02")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="where the scan lands")
    ap.add_argument("--light", default=BIRCH, help="QR light-module colour (cover stock)")
    ap.add_argument("--no-register", action="store_true",
                    help="write the SVG only — do NOT touch the registry")
    ap.add_argument("--verify-pdf", metavar="PDF",
                    help="also decode the cover out of an already-rendered PDF")
    a = ap.parse_args()

    asset = build(a.quarter, a.year, a.issue, a.dest)
    print(f"The Fields Quarterly — {asset['issue_label']}")
    if not a.no_register:
        register(asset)
    else:
        print("  [skip] registry not written (--no-register)")
    write_qr(asset, light=a.light)
    ok = verify(asset, a.light)
    if a.verify_pdf:
        ok = verify_pdf(Path(a.verify_pdf), asset["scan_url"]) and ok
    print(f"  destination: {asset['destination_url']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

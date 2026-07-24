#!/usr/bin/env python3
"""
Generate the Fields Market Pulse QR codes (Fields-grass on white, decode-verified).

Outputs PNGs into pipeline/output/qr/ referenced by the pulse templates:
  - qr_conviction_index.png     -> /conviction-index (methodology page)
  - qr_market_metrics_robina.png -> /market-metrics/Robina (live suburb data)

Usage:
    python3 pipeline/generate_qr.py
"""

from pathlib import Path
import qrcode
from qrcode.constants import ERROR_CORRECT_M

GRASS = (34, 56, 44)   # Fields Grass #22382C
WHITE = (255, 255, 255)

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "qr"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("qr_conviction_index.png", "https://fieldsestate.com.au/conviction-index"),
    ("qr_market_metrics_robina.png", "https://fieldsestate.com.au/market-metrics/Robina"),
]


def make(data: str, path: Path) -> None:
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=20, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=GRASS, back_color=WHITE).convert("RGB")
    img.save(path)
    print(f"  saved {path.name} ({img.size[0]}px) -> {data}")


def main() -> None:
    for fname, url in TARGETS:
        make(url, OUTPUT_DIR / fname)
    print(f"QR codes written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

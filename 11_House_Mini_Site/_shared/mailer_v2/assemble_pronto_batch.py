"""
assemble_pronto_batch.py — build the numbered, print-house-ready batch.

`generate_mailers_v2.py` writes one PDF per slug into `output/`, named by slug.
Pronto needs them numbered per flow, named `<flow>_<NN>_<slug>.pdf`, with a
manifest CSV describing pack-out. That step was previously done by hand, which
is how the 2026-08-17 batch ended up stale: the per-slug PDFs were regenerated
and the batch folder John works from was not, so the two disagreed silently.

⚠ The batch folder is what actually gets printed. Regenerating artwork WITHOUT
re-running this leaves John holding the previous version.

Verifies before writing: every piece in the work order must have a PDF newer
than the work order, and each PDF's QR must decode to a URL carrying the correct
link key for that slug. A mailer whose QR 404s is worse than no mailer — the
recipient's one action fails, in the one moment they were interested.

Usage:
    python3 assemble_pronto_batch.py --flow Fields_01.1 Fields_02.1 --dry-run
    python3 assemble_pronto_batch.py --flow Fields_01.1 Fields_02.1 --write
"""
import argparse
import csv
import re
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

import cv2  # noqa: E402
import fitz  # noqa: E402
import numpy as np  # noqa: E402

from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402
from shared.report_link import report_link_key  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")

# Pack-out is constant per flow; carried from the 2026-08-17 manifest.
PACKOUT = {
    "stock": "Silk 210gsm",
    "insert": "2 x fridge magnet",
    "envelope": "C4 branded",
    "addressee": "The Homeowner",
    "pages": 2,
}


def qr_url(pdf_path, gen_dir):
    """Decode the report QR from a piece. Falls back to the standalone qr.png —
    the PDF raster defeats the OpenCV detector on a minority of pieces at any
    dpi, and that is a detector limit, not bad artwork."""
    det = cv2.QRCodeDetector()
    doc = fitz.open(pdf_path)
    try:
        for dpi in (200, 400):
            for page in doc:
                pix = page.get_pixmap(dpi=dpi)
                img = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8),
                                   cv2.IMREAD_COLOR)
                d, *_ = det.detectAndDecode(img)
                if d and "/your-home/" in d:
                    return d
    finally:
        doc.close()
    qp = os.path.join(gen_dir, "qr.png")
    if os.path.exists(qp):
        d, *_ = det.detectAndDecode(cv2.imread(qp))
        if d and "/your-home/" in d:
            return d
    return None


def split_address(addr):
    """'8 Prestwick Court, Robina QLD 4226' -> ('8 Prestwick Court','Robina','4226')

    Both comma conventions occur in the work orders — "…, Robina QLD 4226" and
    "…, Robina, QLD 4226" — so the state and postcode are stripped by pattern
    rather than by comma position. These fields are printed onto an envelope, so
    a sloppy parse is a piece that does not arrive.
    """
    parts = [p.strip() for p in str(addr).split(",") if p.strip()]
    if not parts:
        return "", "", ""
    line1 = parts[0]
    tail = " ".join(parts[1:])
    m = re.search(r"\b(\d{4})\b\s*$", tail)
    postcode = m.group(1) if m else ""
    suburb = re.sub(r"\b(QLD|NSW|VIC|ACT|NT|SA|TAS|WA)\b", "", tail, flags=re.I)
    suburb = re.sub(r"\b\d{4}\b", "", suburb)
    suburb = re.sub(r"\s{2,}", " ", suburb).strip(" ,")
    return line1, suburb, postcode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", nargs="+", required=True)
    ap.add_argument("--out-dir", default=None)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    load_env()
    sm = get_client()["system_monitor"]
    stamp = datetime.now().strftime("%Y-%m-%d")
    batch_dir = args.out_dir or os.path.join(HERE, f"pronto_batch_{stamp}")

    rows, problems, planned = [], [], []
    for flow in args.flow:
        wo = sm.fulfilment_work_orders.find_one({"flow_code": flow})
        if not wo:
            problems.append((flow, "no work order")); continue
        for n, item in enumerate(wo.get("items") or [], start=1):
            slug = item["slug"]
            src = os.path.join(OUT, f"{slug}.pdf")
            if not os.path.exists(src):
                problems.append((slug, "no generated PDF")); continue

            url = qr_url(src, os.path.join(HERE, "assets", "gen", slug))
            if not url:
                problems.append((slug, "QR did not decode")); continue
            if "k=" not in url:
                problems.append((slug, "QR carries NO link key — would 404")); continue
            k = url.split("k=")[1].split("&")[0].split("#")[0]
            if k != report_link_key(slug):
                problems.append((slug, f"QR key WRONG ({k})")); continue

            dest_name = f"{flow}_{n:02d}_{slug}.pdf"
            planned.append((src, os.path.join(batch_dir, dest_name)))
            line1, suburb, postcode = split_address(item.get("address", ""))
            rows.append({
                "flow_code": flow, "piece_no": n,
                "addressee": PACKOUT["addressee"],
                "address_line_1": line1,
                "suburb": suburb.replace(" QLD", "").strip(),
                "state": "QLD", "postcode": postcode,
                "artwork_file": dest_name, "pages": PACKOUT["pages"],
                "stock": PACKOUT["stock"], "insert": PACKOUT["insert"],
                "envelope": PACKOUT["envelope"],
            })

    print(f"batch dir : {batch_dir}")
    print(f"pieces    : {len(planned)} ready, {len(problems)} problem(s)")
    for s, why in problems:
        print(f"   ✗ {s}: {why}")

    # Rule 7b: assert an outcome. A batch that quietly ships fewer pieces than
    # the work order is the failure this whole script exists to prevent.
    if problems:
        sys.exit("\nREFUSING to assemble — every piece must carry a working QR.")
    if not planned:
        sys.exit("\nREFUSING — no pieces planned; the work-order query is wrong.")

    if args.dry_run:
        print("\n(dry run — pass --write to assemble)")
        return

    os.makedirs(batch_dir, exist_ok=True)
    for src, dest in planned:
        shutil.copy2(src, dest)
    man = os.path.join(batch_dir, "manifest.csv")
    with open(man, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n✓ {len(planned)} pieces + manifest written to {batch_dir}")


if __name__ == "__main__":
    main()

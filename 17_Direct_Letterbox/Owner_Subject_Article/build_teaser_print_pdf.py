#!/usr/bin/env python3
"""Bleed-native lay-up for the owner teaser -> ONE combined print PDF for Pronto.

The teaser is rendered with REAL 3 mm bleed (216 x 303 mm page; trim 210 x 297).
So unlike the mini-site lay-up (which stretches a 0.5 mm edge to fake bleed), this
places the bled artwork 1:1 onto a larger sheet and adds crop + registration marks
in the margin. Nothing is scaled. Piece n lands on pages 2n-1 / 2n (front, back).

Pronto RIP spec (John, 2026-08-20): 3 mm bleed WITH crop + registration marks; one
combined PDF, 100 pages, manifest row order; RGB (Pronto convert).

Usage:
    python3 build_teaser_print_pdf.py --batch <layup_dir> --verify
    python3 build_teaser_print_pdf.py --batch <layup_dir> --write
"""
import argparse, csv, os, sys
import cv2                      # noqa: E402
import fitz                    # noqa: E402
import numpy as np             # noqa: E402

MM = 72.0 / 25.4
TRIM_W, TRIM_H = 210 * MM, 297 * MM
BLEED = 3 * MM
MARGIN = 7 * MM                          # room beyond bleed for the marks
MEDIA_W, MEDIA_H = TRIM_W + 2 * (BLEED + MARGIN), TRIM_H + 2 * (BLEED + MARGIN)
# centred boxes
TRIM = fitz.Rect((MEDIA_W - TRIM_W) / 2, (MEDIA_H - TRIM_H) / 2,
                 (MEDIA_W + TRIM_W) / 2, (MEDIA_H + TRIM_H) / 2)
BLEEDBOX = fitz.Rect(TRIM.x0 - BLEED, TRIM.y0 - BLEED, TRIM.x1 + BLEED, TRIM.y1 + BLEED)
MARK_LEN = 4 * MM
BLACK = (0, 0, 0)


def place(page, src, pno):
    """Bled artwork (216x303) placed 1:1 onto the bleed box. No scaling."""
    page.show_pdf_page(BLEEDBOX, src, pno)


def marks(page):
    """Crop marks at the four trim corners (offset out past the bleed) + four
    mid-edge registration targets. All sit in the margin, never on the artwork."""
    g = BLEED                                    # gap: marks start at the bleed edge
    for (x, y) in ((TRIM.x0, TRIM.y0), (TRIM.x1, TRIM.y0),
                   (TRIM.x0, TRIM.y1), (TRIM.x1, TRIM.y1)):
        hx = -1 if x == TRIM.x0 else 1           # outward direction
        vy = -1 if y == TRIM.y0 else 1
        # horizontal crop mark (left/right of the corner)
        page.draw_line((x + hx * g, y), (x + hx * (g + MARK_LEN), y), color=BLACK, width=0.5)
        # vertical crop mark (above/below the corner)
        page.draw_line((x, y + vy * g), (x, y + vy * (g + MARK_LEN)), color=BLACK, width=0.5)
    # registration targets, mid-edge, in the margin
    r = 1.6 * MM
    for (cx, cy) in (((TRIM.x0 + TRIM.x1) / 2, TRIM.y0 - BLEED - MARGIN / 2),
                     ((TRIM.x0 + TRIM.x1) / 2, TRIM.y1 + BLEED + MARGIN / 2),
                     (TRIM.x0 - BLEED - MARGIN / 2, (TRIM.y0 + TRIM.y1) / 2),
                     (TRIM.x1 + BLEED + MARGIN / 2, (TRIM.y0 + TRIM.y1) / 2)):
        page.draw_circle((cx, cy), r, color=BLACK, width=0.5)
        page.draw_line((cx - r * 1.6, cy), (cx + r * 1.6, cy), color=BLACK, width=0.5)
        page.draw_line((cx, cy - r * 1.6), (cx, cy + r * 1.6), color=BLACK, width=0.5)


def qr_url(page):
    """Decode the teaser QR (bottom-right of page 2) off the laid-up page."""
    det = cv2.QRCodeDetector()
    cta = fitz.Rect(TRIM.x0 + TRIM_W * 0.5, TRIM.y0 + TRIM_H * 0.7, TRIM.x1, TRIM.y1)
    for clip in (cta, None):
        for dpi in (300, 400, 200, 600):
            pix = page.get_pixmap(dpi=dpi, clip=clip)
            img = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_COLOR)
            d, *_ = det.detectAndDecode(img)
            if d and "/off-market/" in d:
                return d
    return None


def bleed_ok(page):
    """No white hairline just outside trim: sample a 1 mm ring in the bleed and
    confirm it is not paper-white everywhere (the artwork reaches the bleed)."""
    ring = fitz.Rect(TRIM.x0 - BLEED, TRIM.y0 - BLEED, TRIM.x1 + BLEED, TRIM.y0 - 0.3 * MM)
    pix = page.get_pixmap(dpi=200, clip=ring)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
    return arr.mean() < 250          # not pure white


def slug_of(fname):
    # Fields_OT.1_07_27-lakeridge-drive-varsity-lakes.pdf -> 27-lakeridge-drive-varsity-lakes
    return fname.rsplit(".pdf", 1)[0].split("_", 3)[3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--out", default=None)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--verify", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args()

    batch = os.path.abspath(a.batch)
    rows = list(csv.DictReader(open(os.path.join(batch, "manifest.csv"))))
    if not rows:
        sys.exit("REFUSING — manifest.csv empty")
    out = a.out or os.path.join(
        batch, f"Fields_{len(rows)}pieces_{2*len(rows)}pp_bleed3mm_crops.pdf")

    doc = fitz.open()
    problems, page_index = [], []
    for row in rows:
        f = os.path.join(batch, row["artwork_file"])
        if not os.path.exists(f):
            problems.append((row["artwork_file"], "missing from batch dir")); continue
        src = fitz.open(f)
        if src.page_count != int(row["pages"]):
            problems.append((row["artwork_file"], f"{src.page_count} pages, manifest {row['pages']}"))
        for pno in range(src.page_count):
            sr = src[pno].rect
            wmm, hmm = sr.width / MM, sr.height / MM
            if abs(wmm - 216) > 1 or abs(hmm - 303) > 1:
                problems.append((row["artwork_file"], f"page {pno+1} not 216x303: {wmm:.1f}x{hmm:.1f}mm")); continue
            page = doc.new_page(width=MEDIA_W, height=MEDIA_H)
            place(page, src, pno)
            marks(page)
            page.set_trimbox(TRIM); page.set_bleedbox(BLEEDBOX)
            page_index.append((row["artwork_file"], pno + 1))
        src.close()

    expected = sum(int(r["pages"]) for r in rows)
    if doc.page_count != expected:
        problems.append(("BATCH", f"{doc.page_count} pages built, expected {expected}"))

    checked = 0
    for i, (fname, srcpage) in enumerate(page_index):
        if not bleed_ok(doc[i]):
            problems.append((fname, f"page {srcpage}: white at bleed edge"))
        if srcpage != 2:                      # QR lives on the back (page 2)
            continue
        slug = slug_of(fname)
        url = qr_url(doc[i])
        if not url:
            problems.append((fname, "QR did not decode in combined PDF")); continue
        if f"/off-market/{slug}" not in url:
            problems.append((fname, f"QR slug WRONG: {url}")); continue
        checked += 1

    print(f"batch     : {batch}")
    print(f"pieces    : {len(rows)}   pages built: {doc.page_count}   media: "
          f"{MEDIA_W/MM:.0f}x{MEDIA_H/MM:.0f}mm  trim 210x297  bleed 216x303")
    print(f"QR checked: {checked} of {len(rows)}")
    for f, why in problems:
        print(f"   x {f}: {why}")
    if problems:
        sys.exit("\nREFUSING to ship — fix the above first.")
    if checked != len(rows):
        sys.exit(f"\nREFUSING — only {checked}/{len(rows)} QRs verified.")
    if a.write:
        doc.save(out, deflate=True)
        print(f"\nWROTE {out}")
    else:
        print("\nVERIFY OK — all pages A-OK, all QRs decode. Re-run with --write.")


if __name__ == "__main__":
    main()

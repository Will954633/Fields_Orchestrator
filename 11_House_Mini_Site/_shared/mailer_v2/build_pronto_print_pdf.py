"""
build_pronto_print_pdf.py — turn an assembled batch into ONE print-ready PDF.

Pronto's RIP wants (John Thwaites, 2026-08-20):
  1. 3 mm bleed WITH crop + registration marks   (not a tagged TrimBox alone)
  2. one combined file, 100 pages, in manifest (mailing) order
  3. RGB is fine — Pronto convert to CMYK their end

`assemble_pronto_batch.py` writes one 2-page PDF per address plus manifest.csv.
This reads that manifest IN ROW ORDER and lays every page onto a larger sheet:

    media 230 x 317 mm   (10 mm all round — room for the marks)
      bleed 216 x 303 mm (trim + 3 mm)
       trim 210 x 297 mm (the artwork, placed 1:1 — never scaled)

The artwork is NOT enlarged to make bleed. Enlarging costs 3 mm of design at
every edge, and the tightest text on page 2 sits 5.6 mm off trim, which would
leave it 2.6 mm from a knife with a +/-1 mm tolerance. Instead the outermost
0.5 mm of each edge is stretched outward into the bleed. That is exact here
because every edge of this artwork is flat colour — deep-green band top, cream
field, deep-green CTA band bottom; no photo reaches an edge (checked over all
50 pieces). If the layout ever changes so that a photo or text does touch the
trim edge, this trick stops being lossless — re-render with real bleed instead.

Usage:
    python3 build_pronto_print_pdf.py --batch pronto_batch_2026-08-19 --verify
    python3 build_pronto_print_pdf.py --batch pronto_batch_2026-08-19 --write
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

import cv2  # noqa: E402
import fitz  # noqa: E402
import numpy as np  # noqa: E402

from shared.report_link import report_link_key  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

MM = 72 / 25.4
TRIM_W, TRIM_H = 210 * MM, 297 * MM
BLEED = 3 * MM
MARGIN = 10 * MM              # media edge -> trim edge
GRAB = 0.5 * MM               # source strip stretched into the bleed
INSET = 0.15 * MM             # skip the antialiased outermost sliver
MARK_GAP = BLEED              # marks start at the bleed edge, never on artwork
MARK_LEN = 5 * MM
MARK_W = 0.25                 # points — hairline
REG_R = 1.6 * MM

MEDIA_W, MEDIA_H = TRIM_W + 2 * MARGIN, TRIM_H + 2 * MARGIN
TRIM = fitz.Rect(MARGIN, MARGIN, MARGIN + TRIM_W, MARGIN + TRIM_H)
BLEEDBOX = fitz.Rect(TRIM.x0 - BLEED, TRIM.y0 - BLEED,
                     TRIM.x1 + BLEED, TRIM.y1 + BLEED)


def place(page, src, pno, srect):
    """Artwork 1:1 on trim, then each edge stretched out to fill the bleed."""
    page.show_pdf_page(TRIM, src, pno)

    sx0, sy0, sx1, sy1 = srect.x0, srect.y0, srect.x1, srect.y1
    edges = [
        # (target rect, source clip)
        (fitz.Rect(TRIM.x0 - BLEED, TRIM.y0, TRIM.x0 + INSET, TRIM.y1),
         fitz.Rect(sx0 + INSET, sy0, sx0 + INSET + GRAB, sy1)),          # left
        (fitz.Rect(TRIM.x1 - INSET, TRIM.y0, TRIM.x1 + BLEED, TRIM.y1),
         fitz.Rect(sx1 - INSET - GRAB, sy0, sx1 - INSET, sy1)),          # right
        (fitz.Rect(TRIM.x0, TRIM.y0 - BLEED, TRIM.x1, TRIM.y0 + INSET),
         fitz.Rect(sx0, sy0 + INSET, sx1, sy0 + INSET + GRAB)),          # top
        (fitz.Rect(TRIM.x0, TRIM.y1 - INSET, TRIM.x1, TRIM.y1 + BLEED),
         fitz.Rect(sx0, sy1 - INSET - GRAB, sx1, sy1 - INSET)),          # bottom
    ]
    corners = [
        (fitz.Rect(TRIM.x0 - BLEED, TRIM.y0 - BLEED, TRIM.x0 + INSET, TRIM.y0 + INSET),
         fitz.Rect(sx0 + INSET, sy0 + INSET, sx0 + INSET + GRAB, sy0 + INSET + GRAB)),
        (fitz.Rect(TRIM.x1 - INSET, TRIM.y0 - BLEED, TRIM.x1 + BLEED, TRIM.y0 + INSET),
         fitz.Rect(sx1 - INSET - GRAB, sy0 + INSET, sx1 - INSET, sy0 + INSET + GRAB)),
        (fitz.Rect(TRIM.x0 - BLEED, TRIM.y1 - INSET, TRIM.x0 + INSET, TRIM.y1 + BLEED),
         fitz.Rect(sx0 + INSET, sy1 - INSET - GRAB, sx0 + INSET + GRAB, sy1 - INSET)),
        (fitz.Rect(TRIM.x1 - INSET, TRIM.y1 - INSET, TRIM.x1 + BLEED, TRIM.y1 + BLEED),
         fitz.Rect(sx1 - INSET - GRAB, sy1 - INSET - GRAB, sx1 - INSET, sy1 - INSET)),
    ]
    for target, clip in edges + corners:
        # keep_proportion=False is the whole point: a 0.5 mm source strip has to
        # STRETCH to fill a 3 mm bleed strip. Left at the default it is scaled to
        # fit and centred, which leaves a white hairline between artwork and bleed
        # — invisible at page-view zoom, fatal on press.
        page.show_pdf_page(target, src, pno, clip=clip, keep_proportion=False)


def marks(page):
    """Crop marks at the four corners, registration targets mid-edge.

    Both sit entirely outside the bleed box, so nothing prints over artwork and
    nothing survives the trim.
    """
    sh = page.new_shape()
    k = (0, 0, 0)
    for x in (TRIM.x0, TRIM.x1):
        for y0, y1 in ((TRIM.y0 - MARK_GAP - MARK_LEN, TRIM.y0 - MARK_GAP),
                       (TRIM.y1 + MARK_GAP, TRIM.y1 + MARK_GAP + MARK_LEN)):
            sh.draw_line(fitz.Point(x, y0), fitz.Point(x, y1))
    for y in (TRIM.y0, TRIM.y1):
        for x0, x1 in ((TRIM.x0 - MARK_GAP - MARK_LEN, TRIM.x0 - MARK_GAP),
                       (TRIM.x1 + MARK_GAP, TRIM.x1 + MARK_GAP + MARK_LEN)):
            sh.draw_line(fitz.Point(x0, y), fitz.Point(x1, y))
    sh.finish(color=k, width=MARK_W)

    centres = [
        fitz.Point((TRIM.x0 + TRIM.x1) / 2, TRIM.y0 - BLEED - MARK_LEN / 2 - REG_R),
        fitz.Point((TRIM.x0 + TRIM.x1) / 2, TRIM.y1 + BLEED + MARK_LEN / 2 + REG_R),
        fitz.Point(TRIM.x0 - BLEED - MARK_LEN / 2 - REG_R, (TRIM.y0 + TRIM.y1) / 2),
        fitz.Point(TRIM.x1 + BLEED + MARK_LEN / 2 + REG_R, (TRIM.y0 + TRIM.y1) / 2),
    ]
    reg = page.new_shape()
    for c in centres:
        reg.draw_circle(c, REG_R)
        reg.draw_line(fitz.Point(c.x - REG_R * 1.5, c.y), fitz.Point(c.x + REG_R * 1.5, c.y))
        reg.draw_line(fitz.Point(c.x, c.y - REG_R * 1.5), fitz.Point(c.x, c.y + REG_R * 1.5))
    reg.finish(color=k, width=MARK_W)
    for c in centres:                       # solid half-target, the usual look
        q = page.new_shape()
        q.draw_sector(c, fitz.Point(c.x, c.y - REG_R), 90)
        q.finish(color=k, fill=k, width=0)
        q.commit()
        q = page.new_shape()
        q.draw_sector(c, fitz.Point(c.x, c.y + REG_R), 90)
        q.finish(color=k, fill=k, width=0)
        q.commit()
    sh.commit()
    reg.commit()


def bleed_gaps(page):
    """Return the edges where the bleed does not match the artwork beside it.

    The first build of this file looked right at page zoom and was wrong: the
    bleed strips were scaled to fit rather than stretched, leaving a white
    hairline just outside the trim. On a 1 mm-off cut that hairline is what
    prints. So every page is checked pixel-wise across the trim line: the colour
    2 mm OUTSIDE trim must match the colour 0.5 mm inside it.
    """
    bad = []
    probes = {
        "left":   (fitz.Rect(TRIM.x0 - 2.5 * MM, TRIM.y0, TRIM.x0 + 1.0 * MM, TRIM.y1), 1),
        "right":  (fitz.Rect(TRIM.x1 - 1.0 * MM, TRIM.y0, TRIM.x1 + 2.5 * MM, TRIM.y1), 1),
        "top":    (fitz.Rect(TRIM.x0, TRIM.y0 - 2.5 * MM, TRIM.x1, TRIM.y0 + 1.0 * MM), 0),
        "bottom": (fitz.Rect(TRIM.x0, TRIM.y1 - 1.0 * MM, TRIM.x1, TRIM.y1 + 2.5 * MM), 0),
    }
    for name, (clip, axis) in probes.items():
        pix = page.get_pixmap(dpi=150, clip=clip)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        if axis == 1:                      # strip runs top-to-bottom; compare columns
            img = img.transpose(1, 0, 2)   # -> (across-trim, along-edge, channels)
        outer, inner = (img[1], img[-2]) if name in ("left", "top") else (img[-2], img[1])
        delta = np.abs(outer.astype(int) - inner.astype(int)).max(axis=1)
        # ignore the few rows where real detail (a rule, a rounded corner) sits on
        # the trim line; a gap shows up along the whole edge, not in 2% of it
        if np.percentile(delta, 98) > 30:
            bad.append(f"{name} (p98 delta {np.percentile(delta, 98):.0f})")
    return bad


def qr_url(page):
    """Decode the report QR off a laid-up page.

    Detection is resolution-sensitive and the whole-page render defeats OpenCV on
    a minority of pieces at any single dpi — so sweep dpi, then retry on the CTA
    block alone (bottom-left of page 1), which is where the code lives. A failure
    here means "the detector gave up", never "the artwork is wrong" — but this
    script cannot tell those apart, so it refuses either way.
    """
    det = cv2.QRCodeDetector()
    cta = fitz.Rect(TRIM.x0, TRIM.y0 + TRIM_H * 0.72, TRIM.x0 + TRIM_W * 0.35, TRIM.y1)
    for clip in (None, cta):
        for dpi in (200, 300, 400, 600):
            pix = page.get_pixmap(dpi=dpi, clip=clip)
            img = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8),
                               cv2.IMREAD_COLOR)
            d, *_ = det.detectAndDecode(img)
            if d and "/your-home/" in d:
                return d
    return None


def slug_of(artwork_file):
    # Fields_01.1_07_8-prestwick-court-robina.pdf -> 8-prestwick-court-robina
    return artwork_file.rsplit(".pdf", 1)[0].split("_", 3)[3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True, help="batch dir (holds manifest.csv)")
    ap.add_argument("--out", default=None)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--verify", action="store_true", help="build in memory, check, discard")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args()

    batch = args.batch if os.path.isabs(args.batch) else os.path.join(HERE, args.batch)
    man = os.path.join(batch, "manifest.csv")
    with open(man) as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit("REFUSING — manifest.csv is empty")

    out_path = args.out or os.path.join(
        batch, f"Fields_{len(rows)}pieces_print_bleed3mm_crops.pdf")

    doc = fitz.open()
    problems, page_index = [], []
    for row in rows:
        f = os.path.join(batch, row["artwork_file"])
        if not os.path.exists(f):
            problems.append((row["artwork_file"], "missing from batch dir")); continue
        src = fitz.open(f)
        if src.page_count != int(row["pages"]):
            problems.append((row["artwork_file"],
                             f"{src.page_count} pages, manifest says {row['pages']}"))
        for pno in range(src.page_count):
            srect = src[pno].rect
            if abs(srect.width - TRIM_W) > 1 or abs(srect.height - TRIM_H) > 1:
                problems.append((row["artwork_file"], f"page {pno+1} is not A4: {srect}"))
                continue
            page = doc.new_page(width=MEDIA_W, height=MEDIA_H)
            place(page, src, pno, srect)
            marks(page)
            page.set_trimbox(TRIM)
            page.set_bleedbox(BLEEDBOX)
            page_index.append((row["artwork_file"], pno + 1))
        src.close()

    expected = sum(int(r["pages"]) for r in rows)
    if doc.page_count != expected:
        problems.append(("BATCH", f"{doc.page_count} pages built, expected {expected}"))

    # Rule 7b — the file only means anything if every QR still works after the
    # re-lay. A combined PDF that prints 100 dead codes is the failure mode.
    checked = 0
    for i, (fname, srcpage) in enumerate(page_index):
        gaps = bleed_gaps(doc[i])
        if gaps:
            problems.append((fname, f"page {srcpage}: bleed gap on {', '.join(gaps)}"))
        if srcpage != 1:
            continue
        slug = slug_of(fname)
        url = qr_url(doc[i])
        if not url:
            problems.append((fname, "QR did not decode in combined PDF")); continue
        if "k=" not in url:
            problems.append((fname, "QR carries no link key")); continue
        k = url.split("k=")[1].split("&")[0].split("#")[0]
        if k != report_link_key(slug):
            problems.append((fname, f"QR key WRONG ({k})")); continue
        checked += 1

    print(f"batch     : {batch}")
    print(f"pieces    : {len(rows)}   pages built: {doc.page_count}")
    print(f"QR checked: {checked} of {len(rows)}   bleed checked: {doc.page_count} pages")
    for f, why in problems:
        print(f"   ✗ {f}: {why}")
    if problems:
        sys.exit("\nREFUSING to ship — fix the above first.")
    if checked != len(rows):
        sys.exit(f"\nREFUSING — only {checked}/{len(rows)} QRs verified.")

    if args.verify:
        print("\n(verify only — pass --write to save)")
        return
    doc.set_metadata({"title": f"Fields mailer batch — {len(rows)} pieces, "
                               "3mm bleed, crop + registration marks",
                      "author": "Fields Real Estate"})
    doc.save(out_path, garbage=4, deflate=True)
    size = os.path.getsize(out_path) / 1e6
    print(f"\n✓ {out_path}  ({size:.1f} MB, {doc.page_count} pages)")


if __name__ == "__main__":
    main()

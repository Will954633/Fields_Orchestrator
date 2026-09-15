#!/usr/bin/env python3
"""
build_card_market_update.py — green business-card magnet, individualised.

Same lay-up as build_card_green.py (white Fields lockup on grass, white-tile QR
bottom-right) with three additions Will asked for 2026-09-15:
  * the household ADDRESS printed top-left ("25 Huntingdale Cres")
  * "My Market Update" in a handwriting font (white), sitting left-and-below the QR
  * a hand-drawn white arrow pointing up to the QR

The QR is INDIVIDUALISED: it points at the recipient's own /your-home/<slug>
(smart-routes to their /property or /off-market page — their personal market
update), carrying the mandatory `k=` link key. Verify the URL 200s before print.

Usage:
  python3 build_card_market_update.py --slug 25-huntingdale-crescent-robina
  python3 build_card_market_update.py --slug <slug> --label "27 Huntingale St"
"""
from __future__ import annotations
import argparse, os, re, subprocess, sys
import segno
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)                       # .../fridge_magnet
ORCH = "/home/fields/Fields_Orchestrator"
OUT = os.path.join(HERE, "proofs")
os.makedirs(OUT, exist_ok=True)
os.chdir(HERE)
sys.path.insert(0, ORCH)
from shared.db import get_client                      # noqa: E402

GRASS = "#22382c"
COPPER = "#b76749"
BASE = "https://fieldsestate.com.au"
UTM = "utm_source=magnet&utm_medium=fridge&utm_campaign=home_magnet_v1"
LOGO_WHITE = open(os.path.join(
    ORCH, "00_Run_Commands/Logo_Files/logo_pack/1-Grass/• SVG/2-Fields-FullName-Grass.svg"
)).read().replace("#22382c", "#ffffff")
INTER = os.path.join(PARENT, "Inter.ttf")
CAVEAT = os.path.join(HERE, "fonts", "Caveat.ttf")

# logo geometry (identical to build_card_green.py)
L_FRAC, B_FRAC = 0.05494, 0.89778
L, LOGO_Y = 74.0, 10.4
LOGO_X = (96 - L) / 2
LOGO_H = L * 89.91 / 298.46
MARGIN, TILE_PAD, MONO_GAP = 2.5, 1.6, 3.5

vis_left = LOGO_X + L_FRAC * L
vis_bot = LOGO_Y + B_FRAC * LOGO_H
TRIM_R, TRIM_B = 96 - 3, 61 - 3
tile_bottom = TRIM_B - MARGIN
tile_top = vis_bot + MONO_GAP
tile = tile_bottom - tile_top
tile_left = TRIM_R - MARGIN - tile
qr = tile - 2 * TILE_PAD

_ST = {"crescent": "Cres", "street": "St", "avenue": "Ave", "court": "Ct",
       "drive": "Dr", "road": "Rd", "close": "Cl", "circuit": "Cct",
       "place": "Pl", "parade": "Pde", "boulevard": "Bvd", "lane": "Ln",
       "terrace": "Tce", "way": "Way", "circle": "Cir", "grove": "Gr"}


def short_addr(address):
    first = address.split(",")[0].strip()
    first = re.sub(r"\s+QLD.*$", "", first).strip()
    parts = first.split()
    if parts:
        parts[-1] = _ST.get(parts[-1].lower(), parts[-1])
    return " ".join(parts)


def build(slug, label=None):
    doc = get_client()["system_monitor"]["property_reports"].find_one({"slug": slug}) or {}
    address = doc.get("address") or slug
    disp = label or short_addr(address)
    # QR opens the fridge animation, personalised to THIS home via ?slug — the
    # fridge then offers /news/<suburb>, /off-market/<slug>, and the walkthrough.
    # No link key needed: /off-market/<slug> is reachable without one, and the
    # fridge landing itself is public. (Was /your-home/<slug>?k=… before 2026-09-15.)
    url = f"{BASE}/fridge?slug={slug}&{UTM}&utm_content={slug}"

    qr_svg = os.path.join(OUT, f"card_mu_{slug}_qr.svg")
    segno.make(url, error="m").save(qr_svg, dark=GRASS, light="#ffffff", border=3)

    # "My Market Update" block: two lines, right-aligned, ending well left of the
    # tile and sitting low -> "left and down from the QR". A gap is left between
    # the text's right edge and the tile for the arrow to live in.
    mu_r_edge = tile_left - 11.0        # x of the text's right edge
    mu_right = 96 - mu_r_edge           # CSS right offset from page edge
    mu_width = 30.0
    mu_top = 40.5

    # hand-drawn arrow living in the gap: tail near the text (lower-left), head
    # pointing UP-and-right into the tile's lower-left. Coords in mm on 96x61.
    ax0, ay0 = mu_r_edge + 1.0, tile_bottom - 1.5      # tail (by the text, low)
    ax1, ay1 = mu_r_edge + 5.0, tile_bottom + 0.6      # control (bows down)
    ax2, ay2 = tile_left + 0.3, tile_bottom - 5.5      # head (into tile, higher up)
    hb1x, hb1y = ax2 - 3.0, ay2 + 0.6                  # barb pointing back-left
    hb2x, hb2y = ax2 - 0.6, ay2 + 3.1                  # barb pointing back-down
    curve_d = f"M {ax0:.2f} {ay0:.2f} Q {ax1:.2f} {ay1:.2f} {ax2:.2f} {ay2:.2f}"
    head_d = f"M {hb1x:.2f} {hb1y:.2f} L {ax2:.2f} {ay2:.2f} L {hb2x:.2f} {hb2y:.2f}"
    # dark underlay drawn slightly wider than the white stroke -> a subtle black
    # border rings the whole white arrow.
    arrow = (
        f'<svg width="96mm" height="61mm" viewBox="0 0 96 61" '
        f'style="position:absolute;left:0;top:0" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{curve_d}" fill="none" stroke="#1b1b1b" stroke-width="1.15" stroke-linecap="round"/>'
        f'<path d="{head_d}" fill="none" stroke="#1b1b1b" stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="{curve_d}" fill="none" stroke="#fff" stroke-width="0.7" stroke-linecap="round"/>'
        f'<path d="{head_d}" fill="none" stroke="#fff" stroke-width="0.7" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )

    html = f"""<style>
  @font-face {{ font-family:'Inter'; src:url('file://{INTER}'); font-weight:400; }}
  @font-face {{ font-family:'Inter'; src:url('file://{INTER}'); font-weight:700; }}
  @font-face {{ font-family:'Caveat'; src:url('file://{CAVEAT}'); }}
  @page {{ size:96mm 61mm; margin:0; }}
  html,body {{ margin:0; padding:0; }}
  .art {{ position:relative; width:96mm; height:61mm; background:{GRASS}; overflow:hidden; }}
  .addr {{ position:absolute; left:6mm; top:4.2mm; font-family:'Inter',sans-serif;
           font-weight:700; font-size:9pt; color:#fff; letter-spacing:0.01em; }}
  .logo {{ position:absolute; left:{LOGO_X}mm; top:{LOGO_Y}mm; width:{L}mm; }}
  .logo svg {{ display:block; width:100%; height:auto; }}
  .tile {{ position:absolute; left:{tile_left}mm; top:{tile_top}mm; width:{tile}mm; height:{tile}mm;
           background:#fff; border-radius:2.2mm; }}
  .qr {{ position:absolute; left:{tile_left+TILE_PAD}mm; top:{tile_top+TILE_PAD}mm; width:{qr}mm; height:{qr}mm; }}
  .mu {{ position:absolute; right:{mu_right}mm; top:{mu_top}mm; width:{mu_width}mm;
         text-align:right; font-family:'Caveat',cursive; font-weight:700;
         font-size:16pt; line-height:0.9; color:#fff; }}
  .tag {{ position:absolute; left:6mm; top:53mm; font-family:'Inter',sans-serif;
          font-weight:400; font-size:9.5pt; color:#fff; letter-spacing:-0.02em; }}
  .tag .dot {{ color:{COPPER}; font-weight:700; }}
</style>
<div class="art">
  <div class="addr">{disp}</div>
  <div class="logo">{LOGO_WHITE}</div>
  <div class="tile"></div>
  <img class="qr" src="file://{qr_svg}">
  <div class="mu">My Market<br>Update</div>
  <div class="tag">Smarter with data<span class="dot">.</span></div>
  {arrow}
</div>"""

    hf = os.path.join(OUT, f"card_mu_{slug}.html")
    open(hf, "w").write(html)
    pdf = os.path.join(OUT, f"card_mu_{slug}.pdf")
    subprocess.run(["weasyprint", hf, pdf], check=True)
    subprocess.run(["pdftoppm", "-png", "-r", "300", "-singlefile", pdf,
                    os.path.join(OUT, f"card_mu_{slug}")], check=True)
    png = os.path.join(OUT, f"card_mu_{slug}.png")
    print(f"built {png}")
    print(f"  address: {disp}")
    print(f"  QR -> {url}")
    try:
        from pyzbar.pyzbar import decode
        got = decode(Image.open(png).convert("RGB"))
        print("  QR decode:", got[0].data.decode() if got else "FAILED TO DECODE")
    except Exception as e:  # noqa: BLE001
        print("  (decode check skipped:", e, ")")
    return png


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="25-huntingdale-crescent-robina")
    ap.add_argument("--label", default=None, help="override printed address text")
    a = ap.parse_args()
    build(a.slug, a.label)

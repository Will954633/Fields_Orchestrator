#!/usr/bin/env python3
"""Refined QR business-card magnet: hero logo, tagline aligned under wordmark, QR under monogram."""
import subprocess, os, segno, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
LOGO_SVG = open("/home/fields/Fields_Orchestrator/00_Run_Commands/Logo_Files/logo_pack/1-Grass/• SVG/2-Fields-FullName-Grass.svg").read()
URL = "https://fieldsestate.com.au/fridge"   # 301 → analyse-your-home + UTM (scan attribution)

# measured logo ink bounds (fraction of logo box) — high-res measurement
L_FRAC, R_FRAC, B_FRAC = 0.05494, 0.94472, 0.89778

# geometry (mm)
L        = 74.0                      # logo width (hero)
LOGO_X   = (96 - L) / 2              # centred on 96mm artboard
LOGO_Y   = 10.4
LOGO_H   = L * 89.91 / 298.46
QR       = float(sys.argv[1]) if len(sys.argv) > 1 else 22.0
TAG_PT   = float(sys.argv[2]) if len(sys.argv) > 2 else 9.0
QR_MARGIN= float(sys.argv[3]) if len(sys.argv) > 3 else 4.0   # narrow gap from trim edge
GAP      = 2.2
TAG_BOX  = 16.0                      # centring box that keeps tagline exactly where it was

vis_left  = LOGO_X + L_FRAC * L
vis_bot   = LOGO_Y + B_FRAC * LOGO_H
row_top   = vis_bot + GAP            # tagline box top (unchanged)

TRIM_R, TRIM_B = 96 - 3, 61 - 3      # trim edges (3mm bleed)
qr_left = TRIM_R - QR_MARGIN - QR    # bottom-right corner, narrow margin
qr_top  = TRIM_B - QR_MARGIN - QR

segno.make(URL, error="m").save("qr_grass.svg", dark="#22382c", light="#ffffff", border=4)

html = f"""<style>
  @font-face {{ font-family:'Inter'; src:url('Inter.ttf'); font-weight:normal; font-style:normal; }}
  @font-face {{ font-family:'Inter'; src:url('Inter.ttf'); font-weight:bold; font-style:normal; }}
  @page {{ size:96mm 61mm; margin:0; }}
  html,body {{ margin:0; padding:0; }}
  .art {{ position:relative; width:96mm; height:61mm; background:#fff; }}
  .logo {{ position:absolute; left:{LOGO_X}mm; top:{LOGO_Y}mm; width:{L}mm; }}
  .logo svg {{ display:block; width:100%; height:auto; }}
  .tagline {{ position:absolute; left:{vis_left}mm; top:{qr_top}mm; height:{QR}mm;
              display:flex; align-items:center;   /* box == QR's vertical span -> centres align */
              font-family:'Inter',sans-serif; font-weight:400; font-size:{TAG_PT}pt;
              color:#64746b; letter-spacing:-0.02em; white-space:nowrap; }}
  .dot {{ color:#b76749; font-weight:700; }}
  .qr {{ position:absolute; left:{qr_left}mm; top:{qr_top}mm; width:{QR}mm; height:{QR}mm; display:block; }}
</style>
<div class="art">
  <div class="logo">{LOGO_SVG}</div>
  <div class="tagline">Smarter with data<span class="dot">.</span></div>
  <img class="qr" src="qr_grass.svg">
</div>"""

open("_cf.html","w").write(html)
subprocess.run(["weasyprint","_cf.html","_cardv2.pdf"],check=True)
subprocess.run(["pdftoppm","-png","-r","300","_cardv2.pdf","_cardv2"],check=True)
os.replace("_cardv2-1.png","_cardv2.png"); os.remove("_cf.html")
print(f"QR={QR}mm @ bottom-right (margin {QR_MARGIN}mm from trim)  tagline={TAG_PT}pt | qr x {qr_left:.1f}-{qr_left+QR:.1f}mm  y {qr_top:.1f}-{qr_top+QR:.1f}mm")
print("preview: _cardv2.png")

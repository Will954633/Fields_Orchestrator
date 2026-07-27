#!/usr/bin/env python3
"""Dark (grass) business-card magnet: white logo + tagline on green; white-tile QR,
   sized/placed so the tile clears the white monogram with a clean green gap."""
import subprocess, os, segno
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
LOGO_WHITE = open("/home/fields/Fields_Orchestrator/00_Run_Commands/Logo_Files/logo_pack/1-Grass/• SVG/2-Fields-FullName-Grass.svg").read().replace("#22382c", "#ffffff")
URL = "https://fieldsestate.com.au/fridge"
GRASS = "#22382c"
L_FRAC, R_FRAC, B_FRAC = 0.05494, 0.94472, 0.89778

# geometry (mm)
L, LOGO_Y = 74.0, 10.4
LOGO_X = (96 - L) / 2
LOGO_H = L * 89.91 / 298.46
MARGIN   = 2.5      # tile gap from trim edge
TILE_PAD = 1.6      # white padding around QR inside the tile
MONO_GAP = 3.5      # clear green gap between monogram bottom and tile top
TAG_PT   = 10.0

vis_left = LOGO_X + L_FRAC * L
vis_bot  = LOGO_Y + B_FRAC * LOGO_H          # logo ink bottom (monogram + wordmark)
TRIM_R, TRIM_B = 96 - 3, 61 - 3

# tile derived from constraints: bottom = margin from trim, top = gap below the logo
tile_bottom = TRIM_B - MARGIN
tile_top    = vis_bot + MONO_GAP
tile        = tile_bottom - tile_top
tile_left   = TRIM_R - MARGIN - tile
qr          = tile - 2 * TILE_PAD
cy          = tile_top + tile / 2            # tile/QR centre → tagline centres on it

segno.make(URL, error="m").save("qr_grass_ontile.svg", dark=GRASS, light="#ffffff", border=3)

html = f"""<style>
  @font-face {{ font-family:'Inter'; src:url('Inter.ttf'); font-weight:normal; font-style:normal; }}
  @font-face {{ font-family:'Inter'; src:url('Inter.ttf'); font-weight:bold; font-style:normal; }}
  @page {{ size:96mm 61mm; margin:0; }}
  html,body {{ margin:0; padding:0; }}
  .art {{ position:relative; width:96mm; height:61mm; background:{GRASS}; }}
  .logo {{ position:absolute; left:{LOGO_X}mm; top:{LOGO_Y}mm; width:{L}mm; }}
  .logo svg {{ display:block; width:100%; height:auto; }}
  .tile {{ position:absolute; left:{tile_left}mm; top:{tile_top}mm; width:{tile}mm; height:{tile}mm;
           background:#fff; border-radius:2.2mm; }}
  .qr {{ position:absolute; left:{tile_left+TILE_PAD}mm; top:{tile_top+TILE_PAD}mm; width:{qr}mm; height:{qr}mm; }}
  .tagline {{ position:absolute; left:{vis_left}mm; top:{cy-8}mm; height:16mm;
              display:flex; align-items:center;
              font-family:'Inter',sans-serif; font-weight:400; font-size:{TAG_PT}pt;
              color:#ffffff; letter-spacing:-0.02em; white-space:nowrap; }}
  .dot {{ color:#b76749; font-weight:700; }}
</style>
<div class="art">
  <div class="logo">{LOGO_WHITE}</div>
  <div class="tagline">Smarter with data<span class="dot">.</span></div>
  <div class="tile"></div>
  <img class="qr" src="qr_grass_ontile.svg">
</div>"""

open("_green.html","w").write(html)
subprocess.run(["weasyprint","_green.html","_green.pdf"],check=True)
subprocess.run(["pdftoppm","-png","-r","300","_green.pdf","_green"],check=True)
os.replace("_green-1.png","_green.png"); os.remove("_green.html")
from pyzbar.pyzbar import decode
print(f"tile={tile:.1f}mm  qr={qr:.1f}mm  tile_top={tile_top:.1f}mm  monogram_bottom={vis_bot:.1f}mm  gap={tile_top-vis_bot:.1f}mm")
print("QR decode:", decode(Image.open("_green.png").convert("RGB"))[0].data.decode())

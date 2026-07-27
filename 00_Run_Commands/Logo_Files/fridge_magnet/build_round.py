#!/usr/bin/env python3
"""Build round coin-sized (29mm) Fields magnet variants + a die-cut comparison preview."""
import subprocess, os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# --- geometry (mm) ---
TRIM_D  = 29.0          # cut diameter (~ AU 20c coin = 28.65mm)
BLEED   = 3.0
ART     = TRIM_D + 2 * BLEED   # 35mm artboard (bleed all round)
BORDER_W = 2.3          # coloured border ring width
INNER_D  = TRIM_D - 2 * BORDER_W
ICON     = 13.5

ICON_PATHS = (
    '<path d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>'
    '<path d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>'
)

def icon_svg(color):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 113.39 113.39" '
            f'fill="{color}">{ICON_PATHS}</svg>')

HTML = """<style>
  @page {{ size: {art}mm {art}mm; margin: 0; }}
  html, body {{ margin: 0; padding: 0; }}
  .art {{ position: relative; width: {art}mm; height: {art}mm; background: {border}; }}
  .face {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
           width: {inner}mm; height: {inner}mm; border-radius: 50%; background: {fill}; }}
  .icon {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
           width: {icon}mm; height: {icon}mm; }}
  .icon svg {{ display: block; width: 100%; height: 100%; }}
</style>
<div class="art">
  <div class="face"></div>
  <div class="icon">{iconsvg}</div>
</div>"""

# name, border, fill, icon-color, label
VARIANTS = [
    ("A_copper_white", "#b76749", "#ffffff", "#22382c", "A  Copper border / white"),
    ("B_copper_grass", "#b76749", "#22382c", "#e6ddd2", "B  Copper border / grass"),
    ("C_grass_white",  "#22382c", "#ffffff", "#22382c", "C  Grass border / white"),
]

PXMM = 26
tiles = []
try:
    fnt = ImageFont.truetype("Inter.ttf", 30)
except Exception:
    fnt = ImageFont.load_default()

for name, border, fill, iconc, label in VARIANTS:
    html = HTML.format(art=ART, border=border, fill=fill, inner=INNER_D,
                       icon=ICON, iconsvg=icon_svg(iconc))
    hp = f"_round_{name}.html"; open(hp, "w").write(html)
    pdf = f"Fields_RoundMagnet_29mm_{name}_PRINT.pdf"
    subprocess.run(["weasyprint", hp, pdf], check=True)
    subprocess.run(["pdftoppm", "-png", "-r", str(PXMM*25.4/1), pdf, f"_round_{name}"],
                   check=True)  # -r dpi = PXMM px/mm
    art_png = Image.open(f"_round_{name}-1.png").convert("RGBA")
    # resize to exact PXMM px/mm
    side = int(round(ART * PXMM))
    art_png = art_png.resize((side, side), Image.LANCZOS)
    # mask to the 29mm cut circle (centered)
    cut = int(round(TRIM_D * PXMM))
    off = (side - cut) // 2
    mask = Image.new("L", (cut, cut), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, cut-1, cut-1], fill=255)
    disc = art_png.crop((off, off, off+cut, off+cut))
    # tile on light background with soft shadow + label
    pad = 44; lblh = 60
    tw, th = cut + pad*2, cut + pad*2 + lblh
    tile = Image.new("RGBA", (tw, th), (244, 244, 242, 255))
    sh = Image.new("RGBA", (tw, th), (0,0,0,0))
    ImageDraw.Draw(sh).ellipse([pad+4, pad+8, pad+cut+4, pad+cut+8], fill=(0,0,0,55))
    from PIL import ImageFilter
    sh = sh.filter(ImageFilter.GaussianBlur(9))
    tile = Image.alpha_composite(tile, sh)
    tile.paste(disc, (pad, pad), mask)
    d = ImageDraw.Draw(tile)
    tb = d.textbbox((0,0), label, font=fnt)
    d.text(((tw-(tb[2]-tb[0]))//2, cut+pad+14), label, fill=(34,56,44,255), font=fnt)
    tiles.append(tile)

# stitch horizontally
gap = 24
W = sum(t.width for t in tiles) + gap*(len(tiles)+1)
H = max(t.height for t in tiles) + gap*2
canvas = Image.new("RGBA", (W, H), (255,255,255,255))
x = gap
for t in tiles:
    canvas.paste(t, (x, gap), t); x += t.width + gap
canvas.convert("RGB").save("_round_COMPARISON.png")
print("wrote _round_COMPARISON.png", canvas.size)

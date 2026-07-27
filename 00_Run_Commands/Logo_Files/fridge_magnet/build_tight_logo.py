#!/usr/bin/env python3
"""Tight-cropped Fields FullName logo (white bg + transparent), rendered from vector."""
import subprocess, os
from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
SRC = "/home/fields/Fields_Orchestrator/00_Run_Commands/Logo_Files/logo_pack/1-Grass/• SVG/2-Fields-FullName-Grass.svg"
GRASS = "#22382c"
DPI = 300
MARGIN_FRAC = 0.03          # minimal even padding = 3% of logo height

svg = open(SRC).read()
svg_grass = svg
svg_black = svg.replace(GRASS, "#000000").replace(GRASS.upper(), "#000000")

def page(inner_svg, bg):
    return (f'<style>@page{{size:260mm 90mm;margin:0}}html,body{{margin:0;padding:0}}'
            f'.wrap{{position:relative;width:260mm;height:90mm;background:{bg}}}'
            f'.p{{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:240mm}}'
            f'.p svg{{display:block;width:100%;height:auto}}</style>'
            f'<div class="wrap"><div class="p">{inner_svg}</div></div>')

def render(html, tag):
    hp = f"_tl_{tag}.html"; open(hp, "w").write(html)
    pdf = f"_tl_{tag}.pdf"
    subprocess.run(["weasyprint", hp, pdf], check=True)
    subprocess.run(["pdftoppm", "-png", "-r", str(DPI), pdf, f"_tl_{tag}"], check=True)
    return Image.open(f"_tl_{tag}-1.png").convert("RGB")

white_full = render(page(svg_grass, "#ffffff"), "white")
black_full = render(page(svg_black, "#ffffff"), "black")   # for a clean AA alpha mask

# content bounding box (from the black render vs white)
bg = Image.new("RGB", black_full.size, (255, 255, 255))
bbox = ImageChops.difference(black_full, bg).getbbox()
l, t, r, b = bbox
h = b - t
m = max(6, int(round(h * MARGIN_FRAC)))
L, T = max(0, l - m), max(0, t - m)
R, B = min(white_full.size[0], r + m), min(white_full.size[1], b + m)

# 1) tight WHITE version
white_tight = white_full.crop((L, T, R, B))
white_tight.save("Fields_Logo_FullName_tight_white.png")

# 2) tight TRANSPARENT version (grass ink + AA alpha from the black coverage map)
black_tight = black_full.crop((L, T, R, B)).convert("L")
alpha = black_tight.point(lambda v: 255 - v)              # black ink -> opaque, white -> clear
rgba = Image.new("RGBA", white_tight.size, (34, 56, 44, 0))
rgba.putalpha(alpha)
rgba.save("Fields_Logo_FullName_tight_transparent.png")

print("white  :", white_tight.size, "px  ->", round(white_tight.size[0]/DPI*25.4,1),
      "x", round(white_tight.size[1]/DPI*25.4,1), "mm @", DPI, "dpi")
print("transp :", rgba.size, "px  margin:", m, "px")

# cleanup intermediates
for f in ["_tl_white.html","_tl_black.html","_tl_white.pdf","_tl_black.pdf",
          "_tl_white-1.png","_tl_black-1.png"]:
    try: os.remove(f)
    except OSError: pass

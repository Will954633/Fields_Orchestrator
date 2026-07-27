#!/usr/bin/env python3
"""Business-card magnet with QR — two layouts (split, footer) + comparison vs blank."""
import subprocess, os, segno
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
LOGO_SVG = open("/home/fields/Fields_Orchestrator/00_Run_Commands/Logo_Files/logo_pack/1-Grass/• SVG/2-Fields-FullName-Grass.svg").read()
URL = "https://fieldsestate.com.au/analyse-your-home"
URL_TEXT = "fieldsestate.com.au"

# grass-green vector QR, ECC M, white quiet zone baked in (invisible on white card)
segno.make(URL, error="m").save("qr_grass.svg", dark="#22382c", light="#ffffff", border=4)

CSS = """<style>
  @font-face { font-family:'Inter'; src:url('Inter.ttf'); font-weight:normal; font-style:normal; }
  @font-face { font-family:'Inter'; src:url('Inter.ttf'); font-weight:bold; font-style:normal; }
  @page { size:96mm 61mm; margin:0; }
  html,body { margin:0; padding:0; }
  .art { position:relative; width:96mm; height:61mm; background:#fff; }
  .logo svg { display:block; width:100%; height:auto; }
  .tagline { font-family:'Inter',sans-serif; font-weight:400; color:#64746b;
             letter-spacing:-0.02em; white-space:nowrap; }
  .dot { color:#b76749; font-weight:700; }
  .url { font-family:'Inter',sans-serif; font-weight:500; color:#22382c; letter-spacing:0.01em; }
  .micro { font-family:'Inter',sans-serif; font-weight:400; color:#8a938c; }
  .qr { display:block; }
  /* split */
  .row { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
         width:80mm; display:flex; align-items:center; justify-content:space-between; }
  .left { width:48mm; }
  .left .logo { width:46mm; }
  .left .tagline { font-size:9.5pt; margin-top:2.6mm; }
  .right { text-align:center; }
  .right .qr { width:20mm; height:20mm; }
  .right .url { font-size:6.7pt; margin-top:1.4mm; }
  /* footer */
  .hero { position:absolute; top:18mm; left:50%; transform:translate(-50%,-50%); text-align:center; }
  .hero .logo { width:52mm; display:inline-block; }
  .hero .tagline { font-size:10pt; margin-top:3mm; }
  .foot { position:absolute; bottom:6mm; left:50%; transform:translateX(-50%);
          display:flex; align-items:center; gap:3mm; }
  .foot .qr { width:16.5mm; height:16.5mm; }
  .foot .txt { text-align:left; }
  .foot .txt .url { font-size:8pt; }
  .foot .txt .micro { font-size:6.4pt; margin-top:0.6mm; }
</style>"""

SPLIT = CSS + """
<div class="art"><div class="row">
  <div class="left">
    <div class="logo">__LOGO__</div>
    <div class="tagline">Smarter with data<span class="dot">.</span></div>
  </div>
  <div class="right">
    <img class="qr" src="qr_grass.svg">
    <div class="url">__URL__</div>
  </div>
</div></div>"""

FOOTER = CSS + """
<div class="art">
  <div class="hero">
    <div class="logo">__LOGO__</div>
    <div class="tagline">Smarter with data<span class="dot">.</span></div>
  </div>
  <div class="foot">
    <img class="qr" src="qr_grass.svg">
    <div class="txt">
      <div class="url">__URL__</div>
      <div class="micro">Scan for your home's data</div>
    </div>
  </div>
</div>"""

def render(tpl, tag):
    html = tpl.replace("__LOGO__", LOGO_SVG).replace("__URL__", URL_TEXT)
    hp=f"_cq_{tag}.html"; open(hp,"w").write(html)
    pdf=f"Fields_BusinessCard_90x55_QR_{tag}_PRINT.pdf"
    subprocess.run(["weasyprint",hp,pdf],check=True)
    subprocess.run(["pdftoppm","-png","-r","240",pdf,f"_cq_{tag}"],check=True)
    return Image.open(f"_cq_{tag}-1.png").convert("RGB")

split = render(SPLIT, "split")
footer = render(FOOTER, "footer")
blank = Image.open("Fields_BusinessCard_90x55_300dpi.png").convert("RGB")

try: fnt=ImageFont.truetype("Inter.ttf",26)
except: fnt=ImageFont.load_default()
W=max(split.width,footer.width,blank.width)
def norm(im):
    return im.resize((W,int(im.height*W/im.width)),Image.LANCZOS) if im.width!=W else im
cards=[("Current (blank)",norm(blank)),("Option 1 - Split",norm(split)),("Option 2 - Footer",norm(footer))]
lblh=54; gap=30
H=sum(c[1].height+lblh for c in cards)+gap*(len(cards)+1)
canvas=Image.new("RGB",(W+gap*2,H),(248,248,246)); d=ImageDraw.Draw(canvas)
y=gap
for label,im in cards:
    d.text((gap,y),label,fill=(34,56,44),font=fnt); y+=lblh
    canvas.paste(im,(gap,y))
    d.rectangle([gap,y,gap+im.width-1,y+im.height-1],outline=(210,210,206),width=1)
    y+=im.height+gap
canvas.save("_cq_COMPARISON.png"); print("wrote _cq_COMPARISON.png",canvas.size)

for f in ["_cq_split.html","_cq_footer.html","_cq_split-1.png","_cq_footer-1.png"]:
    try: os.remove(f)
    except OSError: pass

#!/usr/bin/env python3
"""
build_magnet.py — individualised per-address fridge magnet proofs.

New in this product (vs the generic fridge magnets in the parent folder): the
manufacturer can now print unique creative per magnet. So each magnet carries:

  * the household's OWN address, printed
  * a photo of THEIR house — either the satellite/boundary aerial or the hero
    listing photo (two creative variants, --variant)
  * TWO individualised QR codes:
      1. "Your home report" -> /your-home/<slug>?...&k=<key>  (smart-routes the
         recipient to their own /property or /off-market page; the `k` link key
         is MANDATORY — a code without it lands on a 404, see shared/report_link)
      2. "<Suburb> market news" -> /news/<suburb>             (public, no key)

Both QR targets are verified live 200 before this is meant to ship. Assets are
REUSED from the mailer_v2 run (assets/gen/<slug>/{aerial.png,hero.jpg}) — the
same per-address artwork already generated for last week's mail-out.

Usage:
  python3 build_magnet.py --slug 16-collingwood-avenue-robina --variant satellite --format 90x55
  python3 build_magnet.py --slug 16-collingwood-avenue-robina --variant hero      --format 75x75
"""
from __future__ import annotations
import argparse, os, subprocess, sys
import qrcode
from weasyprint import HTML

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
GEN = os.path.join(ORCH, "11_House_Mini_Site/_shared/mailer_v2/assets/gen")
LOGO_DIR = os.path.dirname(HERE)  # parent fridge_magnet folder holds logo + font
OUT = os.path.join(HERE, "proofs")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ORCH)

from shared.db import get_client               # noqa: E402
from shared.report_link import report_link_key  # noqa: E402

BASE = "https://fieldsestate.com.au"
GREEN = "#22382C"
COPPER = "#B76749"
GREY = "#64746B"
UTM = "utm_source=magnet&utm_medium=fridge&utm_campaign=home_magnet_v1"

# trim dimensions (mm); 3mm bleed added all round for the print artboard
FORMATS = {"90x55": (90, 55), "75x75": (75, 75)}
BLEED = 3


def make_qr(url, path):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=16, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr.make_image(fill_color=GREEN, back_color="white").save(path)


def suburb_hyphen(suburb_key):
    return (suburb_key or "").replace("_", "-")


def build(slug, variant, fmt):
    doc = get_client()["system_monitor"]["property_reports"].find_one({"slug": slug}) or {}
    address = doc.get("address") or slug
    suburb_key = doc.get("suburb_key") or ""
    suburb_name = (doc.get("suburb") or suburb_key.replace("_", " ").title())
    # split "16 Collingwood Avenue, Robina, QLD 4226" -> street line / locality line
    parts = [p.strip() for p in address.replace(" QLD", ", QLD").split(",") if p.strip()]
    street = parts[0] if parts else address
    locality = ", ".join(parts[1:]) if len(parts) > 1 else suburb_name

    key = report_link_key(slug)
    home_url = (f"{BASE}/your-home/{slug}?{UTM}&utm_content={slug}&k={key}#market")
    news_url = (f"{BASE}/news/{suburb_hyphen(suburb_key)}?{UTM}&utm_content={slug}-news")

    tag = f"{slug}__{variant}__{fmt}"
    qh = os.path.join(OUT, f"{tag}__qr_home.png")
    qn = os.path.join(OUT, f"{tag}__qr_news.png")
    make_qr(home_url, qh)
    make_qr(news_url, qn)

    img = os.path.join(GEN, slug, "aerial.png" if variant == "satellite" else "hero.jpg")
    if not os.path.exists(img):
        raise SystemExit(f"missing image for {slug} ({variant}): {img}")
    logo = os.path.join(LOGO_DIR, "Fields_Logo_FullName_tight_transparent.png")

    tw, th = FORMATS[fmt]
    aw, ah = tw + 2 * BLEED, th + 2 * BLEED  # artboard incl bleed
    square = fmt == "75x75"

    # layout differs by format: square -> image on top; landscape -> image on left
    html = _TEMPLATE.format(
        aw=aw, ah=ah, bleed=BLEED, tw=tw, th=th,
        green=GREEN, copper=COPPER, grey=GREY,
        font=os.path.join(LOGO_DIR, "Inter.ttf"),
        img=f"file://{img}", logo=f"file://{logo}",
        qh=f"file://{qh}", qn=f"file://{qn}",
        street=street, locality=locality, suburb=suburb_name,
        flex_dir="column" if square else "row",
        img_class="img-top" if square else "img-left",
        info_class="info-bottom" if square else "info-right",
    )
    hf = os.path.join(OUT, f"{tag}.html")
    with open(hf, "w") as f:
        f.write(html)
    pdf = os.path.join(OUT, f"{tag}.pdf")
    HTML(string=html, base_url=HERE).write_pdf(pdf)
    # 300dpi PNG proof
    subprocess.run(["pdftoppm", "-png", "-r", "300", "-singlefile", pdf,
                    os.path.join(OUT, tag)], check=True)
    print(f"  built {tag}.pdf + .png")
    print(f"    home QR -> {home_url}")
    print(f"    news QR -> {news_url}")
    return pdf


_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family:'Inter'; src:url('{font}'); }}
@page {{ size:{aw}mm {ah}mm; margin:0; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
html,body {{ width:{aw}mm; height:{ah}mm; font-family:'Inter',sans-serif; }}
.bleed {{ width:{aw}mm; height:{ah}mm; background:#fff; position:relative; }}
/* trim area, {bleed}mm inside the artboard */
.trim {{ position:absolute; top:{bleed}mm; left:{bleed}mm;
        width:{tw}mm; height:{th}mm; overflow:hidden;
        display:flex; flex-direction:{flex_dir}; }}
.img-left {{ width:50%; height:100%; object-fit:cover; }}
.img-top  {{ width:100%; height:52%; object-fit:cover; }}
.info-right  {{ flex:1; padding:3.4mm 3mm 3mm 3.4mm; display:flex; flex-direction:column; justify-content:center; }}
.info-bottom {{ flex:1; padding:2.6mm 3mm; display:flex; flex-direction:column; }}
.eyebrow {{ color:{copper}; font-size:5.2pt; font-weight:700; letter-spacing:1.2pt;
           text-transform:uppercase; }}
.street {{ color:{green}; font-weight:800; font-size:9pt; line-height:1.05; margin-top:1mm; }}
.locality {{ color:{grey}; font-size:6.2pt; margin-top:0.6mm; }}
.qrs {{ display:flex; gap:3mm; margin-top:auto; }}
.qrblock {{ text-align:center; }}
.qrblock img {{ width:15mm; height:15mm; display:block; }}
.qrlabel {{ color:{green}; font-size:5pt; font-weight:700; margin-top:0.6mm; line-height:1.1; }}
.foot {{ display:flex; align-items:center; gap:2mm; margin-top:1.8mm; }}
.foot img {{ height:4.4mm; }}
.tagline {{ color:{grey}; font-size:4.6pt; font-weight:600; }}
</style></head><body>
<div class="bleed"><div class="trim">
  <img class="{img_class}" src="{img}">
  <div class="{info_class}">
    <div class="eyebrow">Your home</div>
    <div class="street">{street}</div>
    <div class="locality">{locality}</div>
    <div class="qrs">
      <div class="qrblock"><img src="{qh}"><div class="qrlabel">Your home<br>report</div></div>
      <div class="qrblock"><img src="{qn}"><div class="qrlabel">{suburb}<br>market news</div></div>
    </div>
    <div class="foot"><img src="{logo}"><span class="tagline">Smarter with data.</span></div>
  </div>
</div></div>
</body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--variant", choices=["satellite", "hero"], default="satellite")
    ap.add_argument("--format", choices=list(FORMATS), default="90x55")
    a = ap.parse_args()
    build(a.slug, a.variant, a.format)

#!/usr/bin/env python3
"""Build line-thickness test variants of the A5 note card.

Generates one HTML + PDF per line thickness (mm). Each card prints its own
filename in the top-left corner so test copies are identifiable once printed.
Everything else (grass colour, 28% faintness, layout, copper F symbol) is held
constant so the print test isolates line thickness only.

Run:  python3 build_lines_variants.py
"""
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
THICKNESSES_MM = [0.35, 0.25, 0.15, 0.10, 0.05]

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Fields — Handwritten Note Card (lines {thick}mm)</title>
<style>
  @font-face{{
    font-family:"Hurme Geometric Sans 3";
    src:url("assets/fonts/HurmeGeometricSans-Bold.woff2") format("woff2");
    font-weight:700; font-style:normal;
  }}

  /* A5 landscape note card — no background fill, with faint writing lines.
     Page IS the finished card (210x148), no crop marks / no bleed. */
  @page{{ size:210mm 148mm; margin:0; }}

  :root{{
    --grass:#22382c;     /* Fields grass */
    --copper:#b76749;    /* Fields copper */
  }}

  *{{ box-sizing:border-box; margin:0; padding:0; }}
  html,body{{ background:#ffffff; }}   /* bare white paper — no colour fill */

  .card{{ position:relative; width:210mm; height:148mm; }}

  /* Copper outline icon, top-right — unchanged, printed fine at 0.35 */
  .icon-tr{{ position:absolute; top:6mm; right:6mm; width:45mm; height:45mm; }}
  .icon-tr svg{{ width:100%; height:100%; display:block; }}

  /* Faint writing lines — grass, held faint so handwriting sits on top.
     Drawn as SVG vector strokes (NOT filled divs): a filled box height of
     {thick}mm is sub-pixel and gets snapped to the raster grid differently at
     each y-position when Chrome prints to PDF, so the lines came out with
     varying apparent thickness. A vector stroke carries one declared width
     into the PDF and renders identically regardless of position. The stroke
     width is set on the <svg> element itself, in mm (1 user unit = 1mm). */
  .rules{{ position:absolute; top:0; left:0; width:210mm; height:148mm; }}
  .rules line{{ stroke:var(--grass); stroke-opacity:0.28; stroke-width:{thick}; stroke-linecap:butt; }}

  /* Filename label, top-left — identifies test prints. Removed for final art. */
  .filelabel{{
    position:absolute; top:5mm; left:18mm;
    font-family:"Hurme Geometric Sans 3","Liberation Sans",sans-serif;
    font-size:6pt; color:var(--grass); opacity:0.55; letter-spacing:.02em;
  }}

  /* Grass full-name logo, bottom-left */
  .logo-bl{{ position:absolute; left:6mm; bottom:6mm; height:14mm; }}
  .logo-bl img{{ height:100%; width:auto; display:block; }}

  /* Website + tagline, bottom-right */
  .brand-br{{
    position:absolute; right:6mm; bottom:6mm; text-align:right;
    font-family:"Hurme Geometric Sans 3","Liberation Sans",sans-serif;
    color:var(--grass); line-height:1.15;
  }}
  .brand-br .web{{ font-size:11pt; letter-spacing:.01em; }}
  .brand-br .tagline{{ font-size:11pt; margin-top:1.5mm; }}
</style>
</head>
<body>
  <div class="card">

    <div class="icon-tr">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 113.39 113.39">
        <g fill="none" stroke="#b76749" stroke-width="0.35" stroke-linejoin="round" stroke-linecap="round">
          <path d="M34.47,49.53v44.1h8.87c8.18,0,14.84-6.66,14.84-14.84v-20.39h20.39c8.18,0,14.84-6.66,14.84-14.84v-8.87h-44.1c-8.18,0-14.84,6.66-14.84,14.84"/>
          <path d="M7.83,22.86v82.51h8.87c8.18,0,14.84-6.66,14.84-14.84V31.73h58.77c8.18,0,14.84-6.65,14.84-14.84v-8.87H22.66c-8.18,0-14.84,6.66-14.84,14.84"/>
        </g>
      </svg>
    </div>

    <div class="filelabel">{label}</div>

    <!-- Writing lines as vector strokes. viewBox units are mm (1 unit = 1mm),
         so the stroke-width set in CSS is in mm and identical on every line.
         Greeting line top-left, then 8 body lines ~8.5mm apart, clear of the
         icon above and the logo below. -->
    <svg class="rules" viewBox="0 0 210 148" preserveAspectRatio="none"
         xmlns="http://www.w3.org/2000/svg" shape-rendering="geometricPrecision">
      <line x1="18" y1="30"    x2="88"  y2="30"   />
      <line x1="18" y1="60"    x2="192" y2="60"   />
      <line x1="18" y1="68.5"  x2="192" y2="68.5" />
      <line x1="18" y1="77"    x2="192" y2="77"   />
      <line x1="18" y1="85.5"  x2="192" y2="85.5" />
      <line x1="18" y1="94"    x2="192" y2="94"   />
      <line x1="18" y1="102.5" x2="192" y2="102.5"/>
      <line x1="18" y1="111"   x2="192" y2="111"  />
      <line x1="18" y1="119.5" x2="192" y2="119.5"/>
    </svg>

    <div class="logo-bl">
      <img src="assets/fields-fullname-grass.png" alt="Fields">
    </div>

    <div class="brand-br">
      <div class="web">fieldsestate.com.au</div>
      <div class="tagline">Smarter with data.</div>
    </div>

  </div>
</body>
</html>
"""


def main():
    for t in THICKNESSES_MM:
        stem = f"note_card_lines_{t:.2f}mm"
        html_path = HERE / f"{stem}.html"
        pdf_path = HERE / f"{stem}.pdf"
        label = f"Hand_Written_Notes/{stem}.pdf  ·  lines {t:.2f}mm"
        html_path.write_text(TEMPLATE.format(thick=f"{t:.2f}", label=label))
        subprocess.run([
            "google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", str(html_path),
        ], check=True, cwd=HERE,
           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"built {stem}.html + .pdf")


if __name__ == "__main__":
    main()
